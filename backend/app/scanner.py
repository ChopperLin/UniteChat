"""文件扫描模块 - 扫描 data 目录，构建对话索引"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from config import Config

from app.external_sources import (
    ChatSource,
    ClaudeExportCache,
    GeminiActivityCache,
    detect_claude_folder,
    detect_gemini_folder,
    load_claude_export,
    load_gemini_activity,
)
from app.overrides import load_overrides

class DataFileHandler(FileSystemEventHandler):
    """文件系统事件处理器"""
    
    def __init__(self, scanner):
        self.scanner = scanner
        self.last_scan_time = 0
        self.scan_cooldown = 2  # 2秒冷却时间，避免频繁扫描
        self._last_mtime_by_path: Dict[str, float] = {}
    
    def on_any_event(self, event):
        """处理所有文件系统事件"""
        # 只关心JSON文件的变化
        if event.is_directory or not event.src_path.endswith('.json'):
            return

        # Ignore read/open/close events: those can fire frequently on Windows and would
        # cause the cache to thrash while the app is merely reading JSON files.
        if getattr(event, "event_type", None) not in {"modified", "created", "deleted", "moved"}:
            return

        # On some Windows configurations, file reads can still trigger "modified" events
        # without changing mtime (e.g. metadata/atime). Guard against that to keep the
        # conversation list cache stable.
        try:
            if getattr(event, "event_type", None) == "modified":
                p = Path(event.src_path)
                if p.exists():
                    mtime = float(p.stat().st_mtime)
                    prev = self._last_mtime_by_path.get(event.src_path)
                    self._last_mtime_by_path[event.src_path] = mtime
                    if prev is not None and abs(prev - mtime) < 1e-6:
                        return
        except Exception:
            pass
        
        current_time = time.time()
        if current_time - self.last_scan_time < self.scan_cooldown:
            return
        
        self.last_scan_time = current_time
        print(f"🔄 检测到文件变化: {event.src_path}")
        print(f"   事件类型: {event.event_type}")
        
        # 清除缓存（如果有的话）
        self.scanner.clear_cache()

class ConversationScanner:
    """对话文件扫描器（支持自动监听文件变化）"""
    
    def __init__(self):
        self.data_root = Config.DATA_ROOT_PATH
        self.current_folder = None
        self._cache = {}  # 简单的缓存
        self._special_cache: Dict[str, Dict[str, Any]] = {}
        self._observer = None
        self._start_file_watcher()
        self._file_time_cache: Dict[str, Tuple[float, Optional[float], Optional[float], float]] = {}

        # Fast header parse: exported ChatGPT JSON usually contains create_time/update_time near the top.
        self._re_update_time = re.compile(r'"update_time"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
        self._re_create_time = re.compile(r'"create_time"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
        # Gemini web export (batchexecute) stores fetch time as ISO string.
        self._re_fetched_at = re.compile(r'"fetched_at"\s*:\s*"([^"]+)"')
        # Fast scan for epoch timestamp pairs inside batchexecute_raw string.
        # Example: [1755227954,114133000]
        self._re_epoch_pair_bytes = re.compile(rb"\[(\d{9,12}),\s*(\d{1,9})\]")

    def _iso_to_epoch_seconds(self, value: Optional[str]) -> Optional[float]:
        """Parse an ISO timestamp string to epoch seconds (UTC)."""
        if not value or not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None

        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.timestamp()

    def _fast_extract_batchexecute_times(self, json_file: Path, head_bytes: bytes) -> Tuple[Optional[float], Optional[float]]:
        """Fast best-effort timestamp extraction for Gemini batchexecute exports.

        We avoid full JSON parsing for performance. The batchexecute payload contains many
        turn timestamps as `[sec, nanos]` pairs inside the serialized string.
        """
        try:
            size = int(json_file.stat().st_size)
        except Exception:
            size = 0

        # If the export doesn't contain the expected inner payload marker, it's often an
        # "access denied / fetch failure" stub. Push these to the bottom.
        # NOTE: This marker is inside a JSON string, so quotes are escaped.
        has_inner_marker = b'\\"hNvQHb\\"' in (head_bytes or b"")

        def _scan_bytes(buf: bytes) -> List[float]:
            out: List[float] = []
            for m in self._re_epoch_pair_bytes.finditer(buf or b""):
                try:
                    sec = int(m.group(1))
                    nanos = int(m.group(2))
                except Exception:
                    continue
                if not (1_000_000_000 <= sec <= 20_000_000_000):
                    continue
                if not (0 <= nanos < 1_000_000_000):
                    continue
                out.append(float(sec) + (float(nanos) / 1e9))
            return out

        # Prefer tail for update_time (latest turn often near the end)
        ts_vals: List[float] = []
        try:
            with open(json_file, "rb") as f:
                if size > 0:
                    tail = 512 * 1024
                    if size > tail:
                        f.seek(max(0, size - tail))
                    buf = f.read(tail)
                else:
                    buf = head_bytes or b""
            ts_vals = _scan_bytes(buf)
        except Exception:
            ts_vals = []

        if ts_vals:
            update_time = max(ts_vals)
            create_time = min(ts_vals) if size <= (512 * 1024) else None
            if create_time is None:
                # Try head for create_time (earliest turn)
                try:
                    with open(json_file, "rb") as f2:
                        buf2 = f2.read(256 * 1024)
                    head_vals = _scan_bytes(buf2)
                    if head_vals:
                        create_time = min(head_vals)
                except Exception:
                    create_time = None
            return update_time, create_time

        # No timestamp pairs found: likely invalid export, or a variant without timestamps.
        if not has_inner_marker:
            return 0.0, None

        return None, None

    def _detect_folder_kind(self, folder_path: Path) -> str:
        """Detect the export format for a folder.

        Returns:
            'chatgpt' | 'claude' | 'gemini'
        """
        try:
            if detect_claude_folder(folder_path):
                return 'claude'
            if detect_gemini_folder(folder_path):
                return 'gemini'
        except Exception:
            # Fallback to ChatGPT-style
            pass
        return 'chatgpt'

    def _ensure_special_loaded(self, folder_name: str, folder_path: Path) -> Optional[Dict[str, Any]]:
        """Load and cache special folders (Claude/Gemini)."""
        kind = self._detect_folder_kind(folder_path)
        if kind == 'chatgpt':
            return None

        cache_key = (folder_name or '').strip() or folder_path.name
        cached = self._special_cache.get(cache_key)

        if kind == 'claude':
            src = detect_claude_folder(folder_path)
            if not src:
                return None
            mtime = float(src.stat().st_mtime)
            if cached and cached.get('kind') == 'claude' and float(cached.get('mtime') or 0.0) == mtime:
                return cached

            claude_cache: ClaudeExportCache = load_claude_export(folder_name=cache_key, folder_path=folder_path)
            listing: Dict[str, List[Dict]] = {}
            lookup: Dict[Tuple[str, str], ChatSource] = {}
            overrides = load_overrides(folder_path).data.get("items") or {}

            # Build project categories.
            projects = list(getattr(claude_cache, 'projects', []) or [])
            projects_sorted = sorted(projects, key=lambda p: (p.name or '').lower())

            # Since this export doesn't include an explicit project_uuid on conversations,
            # we classify each conversation into exactly one project using text overlap.
            ascii_re = re.compile(r"[0-9A-Za-z]{2,}")

            def _is_cjk(ch: str) -> bool:
                return "\u4e00" <= ch <= "\u9fff"

            def _tokens(s: str) -> Tuple[set, set]:
                s = (s or "").lower()
                ascii_toks = set(ascii_re.findall(s))
                cjk = {ch for ch in s if _is_cjk(ch)}
                return ascii_toks, cjk

            project_profiles = []
            for pr in projects_sorted:
                # Use a compact profile; long prompt templates/memories can swamp scoring.
                p_text = "\n".join([
                    str(pr.name or ""),
                    str(getattr(pr, 'description', '') or ''),
                ])
                a, c = _tokens(p_text)
                project_profiles.append({
                    'uuid': pr.uuid,
                    'name': str(pr.name or 'Project').strip() or 'Project',
                    'created_at': pr.created_at,
                    'updated_at': pr.updated_at,
                    'ascii': a,
                    'cjk': c,
                })

            if not project_profiles:
                # Fallback: keep everything under a single bucket.
                project_profiles = [{'uuid': '', 'name': 'Claude', 'ascii': set(), 'cjk': set()}]

            # Ensure every project exists as a category, and pin “（项目设定）” as the first entry.
            for p in project_profiles:
                proj_name = p.get('name') or 'Claude'
                proj_uuid = p.get('uuid') or ''
                cat = f"项目/{proj_name}".strip()
                pid = f"project__{proj_uuid or proj_name}"
                sort_time = p.get('updated_at') or p.get('created_at') or 0.0

                listing.setdefault(cat, []).append({
                    'id': pid,
                    'title': f"（项目设定）{proj_name}",
                    'category': cat,
                    'project_uuid': proj_uuid,
                    'project_name': proj_name,
                    'update_time': p.get('updated_at'),
                    'create_time': p.get('created_at'),
                    'can_edit': False,
                    '_sort_time': sort_time,
                    '_pinned': 1,
                })
                lookup[(cat, pid)] = ChatSource(
                    kind='claude_project',
                    folder=cache_key,
                    category=cat,
                    chat_id=pid,
                    file_path=src,
                    extra={'project_uuid': proj_uuid, 'project_name': proj_name},
                )

            def _first_user_snippet(conv_raw: Dict[str, Any]) -> str:
                msgs = conv_raw.get('chat_messages')
                if not isinstance(msgs, list):
                    return ''
                for m in msgs:
                    if not isinstance(m, dict):
                        continue
                    sender = (m.get('sender') or '').strip().lower()
                    if sender not in {'human', 'user'}:
                        continue
                    t = m.get('text')
                    if isinstance(t, str) and t.strip():
                        return re.sub(r"\s+", " ", t).strip()[:80]
                    cl = m.get('content')
                    if isinstance(cl, list):
                        for part in cl:
                            if isinstance(part, dict) and isinstance(part.get('text'), str) and part.get('text').strip():
                                return re.sub(r"\s+", " ", part.get('text')).strip()[:80]
                return ''

            def _conv_text(conv_raw: Dict[str, Any]) -> str:
                # Only use title+summary for project assignment to avoid content-based skew.
                out = []
                name = conv_raw.get('name')
                summary = conv_raw.get('summary')
                if isinstance(name, str) and name.strip():
                    out.append(name)
                if isinstance(summary, str) and summary.strip():
                    out.append(summary)
                return "\n".join(out)

            def _score(conv_ascii: set, conv_cjk: set, p: Dict[str, Any]) -> float:
                # Normalize overlap so large project profiles don't dominate.
                a_i = len(conv_ascii & p['ascii'])
                a_u = len(conv_ascii | p['ascii'])
                c_i = len(conv_cjk & p['cjk'])
                c_u = len(conv_cjk | p['cjk'])

                a_sim = (a_i / a_u) if a_u else 0.0
                c_sim = (c_i / c_u) if c_u else 0.0
                return 4.0 * a_sim + 1.0 * c_sim

            for rec in claude_cache.conversations:
                conv_raw = rec.raw

                # Hide empty/contentless conversations (common export artifacts)
                msgs = conv_raw.get('chat_messages')
                if not isinstance(msgs, list) or not msgs:
                    continue
                has_any_text = False
                for m in msgs:
                    if not isinstance(m, dict):
                        continue
                    t = m.get('text')
                    if isinstance(t, str) and t.strip():
                        has_any_text = True
                        break
                    cl = m.get('content')
                    if isinstance(cl, list):
                        for part in cl:
                            if isinstance(part, dict) and isinstance(part.get('text'), str) and part.get('text').strip():
                                has_any_text = True
                                break
                    if has_any_text:
                        break
                if not has_any_text:
                    continue

                sort_time = rec.updated_at or rec.created_at or 0.0
                conv_text = _conv_text(conv_raw)
                conv_ascii, conv_cjk = _tokens(conv_text)
                conv_low = conv_text.lower()

                best = None
                best_score = -1.0
                for p in project_profiles:
                    sc = _score(conv_ascii, conv_cjk, p)
                    pname = (p.get('name') or '').strip().lower()
                    if len(pname) >= 3 and pname in conv_low:
                        sc += 100.0
                    if sc > best_score:
                        best_score = sc
                        best = p

                proj_name = (best or {}).get('name') or 'Claude'
                proj_uuid = (best or {}).get('uuid') or ''
                cat = f"项目/{proj_name}".strip()

                title = str(rec.name or '').strip()
                if not title or title.lower() == 'untitled':
                    title = _first_user_snippet(conv_raw) or 'Untitled'

                ov = overrides.get(f"claude:{rec.uuid}")
                if isinstance(ov, dict) and ov.get("deleted") is True:
                    continue
                if isinstance(ov, dict):
                    t2 = ov.get("title")
                    if isinstance(t2, str) and t2.strip():
                        title = t2.strip()

                listing.setdefault(cat, []).append({
                    'id': rec.uuid,
                    'title': title,
                    'category': cat,
                    'project_uuid': proj_uuid,
                    'project_name': proj_name,
                    'update_time': rec.updated_at,
                    'create_time': rec.created_at,
                    'can_edit': True,
                    '_sort_time': sort_time,
                })
                lookup[(cat, rec.uuid)] = ChatSource(
                    kind='claude',
                    folder=cache_key,
                    category=cat,
                    chat_id=rec.uuid,
                    file_path=src,
                    extra={'uuid': rec.uuid, 'project_uuid': proj_uuid, 'project_name': proj_name},
                )

            # Sort items within each category.
            for cat, items in list(listing.items()):
                items.sort(key=lambda x: (x.get('_pinned') or 0, x.get('_sort_time') or 0.0, x.get('title') or ''), reverse=True)
                for it in items:
                    it.pop('_sort_time', None)
                    it.pop('_pinned', None)

            cached = {
                'kind': 'claude',
                'mtime': claude_cache.mtime,
                'src': src,
                'claude_cache': claude_cache,
                'listing': listing,
                'lookup': lookup,
            }
            self._special_cache[cache_key] = cached
            return cached

        if kind == 'gemini':
            src = detect_gemini_folder(folder_path)
            if not src:
                return None
            mtime = float(src.stat().st_mtime)
            if cached and cached.get('kind') == 'gemini' and float(cached.get('mtime') or 0.0) == mtime:
                return cached

            gemini_cache: GeminiActivityCache = load_gemini_activity(folder_name=cache_key, folder_path=folder_path)
            items = []
            lookup: Dict[Tuple[str, str], ChatSource] = {}

            for rec in gemini_cache.records:
                sort_time = rec.updated_at or rec.created_at or 0.0
                items.append({
                    'id': rec.chat_id,
                    'title': rec.title,
                    'category': '全部',
                    'update_time': rec.updated_at,
                    'create_time': rec.created_at,
                    'can_edit': False,
                    '_sort_time': sort_time,
                })
                lookup[('全部', rec.chat_id)] = ChatSource(
                    kind='gemini',
                    folder=cache_key,
                    category='全部',
                    chat_id=rec.chat_id,
                    file_path=src,
                    extra={'chat_id': rec.chat_id},
                )

            items.sort(key=lambda x: (x.get('_sort_time') or 0.0, x.get('title') or ''), reverse=True)
            for it in items:
                it.pop('_sort_time', None)

            cached = {
                'kind': 'gemini',
                'mtime': gemini_cache.mtime,
                'src': src,
                'gemini_cache': gemini_cache,
                'listing': {'全部': items},
                'lookup': lookup,
            }
            self._special_cache[cache_key] = cached
            return cached

        return None
    
    def _start_file_watcher(self):
        """启动文件监听"""
        if not self.data_root.exists():
            print(f"⚠️  数据目录不存在，跳过文件监听: {self.data_root}")
            return
        
        try:
            event_handler = DataFileHandler(self)
            self._observer = Observer()
            self._observer.schedule(event_handler, str(self.data_root), recursive=True)
            self._observer.start()
            print(f"👁️  文件监听已启动: {self.data_root}")
        except Exception as e:
            print(f"⚠️  文件监听启动失败: {e}")
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._special_cache.clear()
        print("🗑️  缓存已清除")
    
    def stop_watcher(self):
        """停止文件监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            print("👁️  文件监听已停止")
    
    def get_available_folders(self) -> List[str]:
        """
        获取所有可用的聊天记录文件夹
        
        Returns:
            文件夹名称列表
        """
        if not self.data_root.exists():
            return []
        
        folders = []
        for item in self.data_root.iterdir():
            if item.is_dir():
                folders.append(item.name)
        
        return sorted(folders)
    
    def set_folder(self, folder_name: str) -> bool:
        """
        设置当前使用的文件夹
        
        Args:
            folder_name: 文件夹名称
            
        Returns:
            是否设置成功
        """
        folder_path = self.data_root / folder_name
        if folder_path.exists() and folder_path.is_dir():
            self.current_folder = folder_name
            return True
        return False
    
    def scan_all_conversations(self, folder_name: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        递归扫描所有对话文件，按分类组织（支持多级目录）
        
        Args:
            folder_name: 指定的文件夹名称，如果为None则使用current_folder
        
        Returns:
            {
                'AI': [{'id': 'xxx', 'title': 'xxx'}, ...],
                'AI/Models': [...],
                'CS/Python': [...],
                ...
            }
        """
        # 检查缓存
        cache_key = folder_name or self.current_folder or 'default'
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = {}
        
        # 确定要使用的文件夹
        if folder_name:
            data_dir = self.data_root / folder_name
        elif self.current_folder:
            data_dir = self.data_root / self.current_folder
        else:
            # 如果没有指定，使用第一个可用的文件夹
            folders = self.get_available_folders()
            if not folders:
                return result
            data_dir = self.data_root / folders[0]
            self.current_folder = folders[0]
        
        if not data_dir.exists():
            return result

        # Special folders: Claude export / Gemini takeout
        special = self._ensure_special_loaded(folder_name=(folder_name or self.current_folder or ''), folder_path=data_dir)
        if special and isinstance(special.get('listing'), dict):
            listing = special.get('listing')
            self._cache[cache_key] = listing
            return listing
        
        # 递归扫描所有JSON文件，构建分类索引
        self._scan_recursive(data_dir, data_dir, result)
        
        # 如果没有找到任何分类，可能所有文件都在根目录
        if not result:
            conversations = self._scan_category(data_dir)
            if conversations:
                result['全部'] = conversations
        
        # 缓存结果
        self._cache[cache_key] = result
        
        return result

    def resolve_chat_source(self, chat_id: str, category: str, folder_name: Optional[str] = None) -> ChatSource:
        """Resolve a chat request to a concrete source.

        This keeps the frontend contract unchanged (chat_id + category + folder),
        while allowing container formats like Claude/Gemini.
        """
        # Determine folder
        if folder_name:
            folder_to_use = folder_name
        elif self.current_folder:
            folder_to_use = self.current_folder
        else:
            raise FileNotFoundError("No folder selected")

        folder_path = self.data_root / folder_to_use
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_to_use}")

        kind = self._detect_folder_kind(folder_path)
        if kind != 'chatgpt':
            special = self._ensure_special_loaded(folder_name=folder_to_use, folder_path=folder_path) or {}
            lookup = special.get('lookup') or {}
            src = lookup.get((category, chat_id))
            if src:
                return src
            raise FileNotFoundError(f"Chat not found: {chat_id} in {category}")

        # Default: ChatGPT per-file JSON
        file_path = self.find_chat_file(chat_id, category, folder_to_use)
        return ChatSource(
            kind='chatgpt_file',
            folder=folder_to_use,
            category=category,
            chat_id=chat_id,
            file_path=file_path,
            extra={},
        )

    def get_special_folder_cache(self, folder_name: str) -> Optional[Dict[str, Any]]:
        """Return the loaded special-folder cache for a folder (Claude/Gemini), if any."""
        folder_name = (folder_name or '').strip()
        if not folder_name:
            return None
        folder_path = self.data_root / folder_name
        if not folder_path.exists():
            return None
        return self._ensure_special_loaded(folder_name=folder_name, folder_path=folder_path)
    
    def _scan_recursive(self, current_path: Path, root_path: Path, result: Dict[str, List[Dict]]):
        """
        递归扫描目录，收集所有JSON文件
        
        Args:
            current_path: 当前扫描的目录
            root_path: 根目录（用于计算相对路径）
            result: 结果字典，会被修改
        """
        # 收集当前目录的所有JSON文件
        json_files = list(current_path.glob("*.json"))
        
        if json_files:
            # 计算分类名称（相对路径）
            if current_path == root_path:
                # 根目录的文件，暂不添加，等最后统一处理
                pass
            else:
                relative_path = current_path.relative_to(root_path)
                category_name = str(relative_path).replace('\\', '/')
                
                conversations = []
                for json_file in json_files:
                    title, conv_id = self._parse_filename(json_file.stem)
                    update_time, create_time, sort_time = self._get_conversation_times(json_file)
                    conversations.append({
                        'id': conv_id,
                        'title': title,
                        'category': category_name,  # 保存完整路径，用于查找文件
                        'update_time': update_time,
                        'create_time': create_time,
                        'can_edit': True,
                        '_sort_time': sort_time,
                    })

                # ChatGPT web sorts by conversation time (most recently updated first)
                conversations.sort(key=lambda x: (x.get('_sort_time') or 0.0, x.get('title') or ''), reverse=True)
                for c in conversations:
                    c.pop('_sort_time', None)
                result[category_name] = conversations
        
        # 递归扫描子目录
        for item in current_path.iterdir():
            if item.is_dir():
                self._scan_recursive(item, root_path, result)
    
    def _scan_category(self, category_path: Path) -> List[Dict]:
        """
        扫描单个目录（非递归，仅当前层级）
        
        Args:
            category_path: 目录路径
            
        Returns:
            [{'id': 'xxx', 'title': 'xxx', 'category': '全部'}, ...]
        """
        conversations = []
        
        # 遍历该目录下的所有 JSON 文件（不递归）
        for json_file in category_path.glob("*.json"):
            title, conv_id = self._parse_filename(json_file.stem)
            update_time, create_time, sort_time = self._get_conversation_times(json_file)
            conversations.append({
                'id': conv_id,
                'title': title,
                'category': '全部',
                'update_time': update_time,
                'create_time': create_time,
                'can_edit': True,
                '_sort_time': sort_time,
            })
        
        # 按对话时间排序（最近优先）
        conversations.sort(key=lambda x: (x.get('_sort_time') or 0.0, x.get('title') or ''), reverse=True)
        for c in conversations:
            c.pop('_sort_time', None)
        
        return conversations

    def _get_conversation_times(self, json_file: Path) -> Tuple[Optional[float], Optional[float], float]:
        """Try to read update_time/create_time from JSON header quickly.

        Returns:
            (update_time, create_time, sort_time)
        """
        update_time = None
        create_time = None

        try:
            st = json_file.stat()
            mtime = float(st.st_mtime)
            cached = self._file_time_cache.get(str(json_file))
            if cached and abs(cached[0] - mtime) < 1e-6:
                return cached[1], cached[2], cached[3]
        except Exception:
            mtime = None

        try:
            # Read a limited prefix; exported files place title/create_time/update_time near the top.
            with open(json_file, 'rb') as f:
                head = f.read(64 * 1024)
            text = head.decode('utf-8', errors='ignore')

            m_upd = self._re_update_time.search(text)
            if m_upd:
                try:
                    update_time = float(m_upd.group(1))
                except Exception:
                    update_time = None

            m_cre = self._re_create_time.search(text)
            if m_cre:
                try:
                    create_time = float(m_cre.group(1))
                except Exception:
                    create_time = None

            # Gemini batchexecute exports typically don't include numeric create/update_time.
            # Prefer extracting actual turn timestamps; fall back to fetched_at (ISO string).
            if update_time is None and create_time is None and '"batchexecute_raw"' in text:
                upd, cre = self._fast_extract_batchexecute_times(json_file, head)
                update_time = upd if isinstance(upd, (int, float)) else None
                create_time = cre if isinstance(cre, (int, float)) else None

                if update_time is None and create_time is None:
                    m_fetched = self._re_fetched_at.search(text)
                    if m_fetched:
                        ts = self._iso_to_epoch_seconds(m_fetched.group(1))
                        if ts:
                            update_time = ts
        except Exception:
            update_time = None
            create_time = None

        # Prefer JSON times; fallback to filesystem mtime (seconds).
        # NOTE: update_time can be 0.0 as a sentinel to push invalid exports to the bottom,
        # so we must not use truthiness checks here.
        if update_time is not None:
            sort_time = float(update_time)
        elif create_time is not None:
            sort_time = float(create_time)
        else:
            sort_time = 0.0
            try:
                sort_time = float(json_file.stat().st_mtime)
            except Exception:
                sort_time = 0.0

        try:
            if mtime is None:
                mtime = float(json_file.stat().st_mtime)
            self._file_time_cache[str(json_file)] = (float(mtime), update_time, create_time, float(sort_time))
        except Exception:
            pass

        return update_time, create_time, sort_time
    
    def _parse_filename(self, stem: str) -> tuple:
        """
        从文件名提取标题和ID
        
        文件名格式: Transformer工作原理解释_ee80e43e5561
        
        Args:
            stem: 文件名（不含扩展名）
            
        Returns:
            (title, id)
        """
        parts = stem.rsplit('_', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return stem, stem
    
    def find_chat_file(self, chat_id: str, category: str, folder_name: Optional[str] = None) -> Path:
        """
        根据 chat_id 和分类找到对应的 JSON 文件（支持多级目录）
        
        Args:
            chat_id: 对话ID
            category: 分类名称（支持路径如 "AI/Models" 或 "全部"）
            folder_name: 文件夹名称，如果为None则使用current_folder
            
        Returns:
            文件路径
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        # 确定要使用的文件夹
        if folder_name:
            data_dir = self.data_root / folder_name
        elif self.current_folder:
            data_dir = self.data_root / self.current_folder
        else:
            raise FileNotFoundError("No folder selected")
        
        # 确定搜索目录
        if category == '全部':
            # 在根目录查找
            search_dir = data_dir
        else:
            # 支持多级路径，将 '/' 转换为系统路径分隔符
            search_dir = data_dir / category.replace('/', '\\')
        
        if not search_dir.exists():
            raise FileNotFoundError(f"Category not found: {category}")
        
        # 查找匹配的文件
        for json_file in search_dir.glob(f"*_{chat_id}.json"):
            return json_file
        
        raise FileNotFoundError(f"Chat file not found: {chat_id} in {category}")


# 创建全局扫描器实例
scanner = ConversationScanner()
