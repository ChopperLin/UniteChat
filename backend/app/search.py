"""搜索索引模块 - 为标题/内容提供高速搜索"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.scanner import scanner
from app.normalize import (
    extract_search_text_from_normalized,
    normalize_claude_conversation,
    normalize_claude_project,
    normalize_gemini_activity,
)
from app.gemini_batchexecute import is_gemini_batchexecute_export, extract_gemini_batchexecute_text


_ASCII_TOKEN_RE = re.compile(r"[0-9A-Za-z]{2,}")


def _is_cjk(ch: str) -> bool:
    # 常用汉字区（覆盖大多数中文）
    return "\u4e00" <= ch <= "\u9fff"


def _normalize_space(s: str) -> str:
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)


def _normalize_query(q: str) -> str:
    return _normalize_space(q).lower()


def _parse_filename(stem: str) -> Tuple[str, str]:
    parts = stem.rsplit('_', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return stem, stem


def _extract_search_text(json_data: Dict) -> str:
    """从导出的对话 JSON 中提取可搜索的纯文本。"""
    out: List[str] = []

    # Gemini per-conversation export (batchexecute wrapper)
    if is_gemini_batchexecute_export(json_data):
        return extract_gemini_batchexecute_text(json_data)

    title = json_data.get('title')
    if isinstance(title, str) and title.strip():
        out.append(title.strip())

    mapping = json_data.get('mapping', {})
    if not isinstance(mapping, dict):
        return "\n".join(out)

    for node in mapping.values():
        if not isinstance(node, dict):
            continue
        message = node.get('message')
        if not isinstance(message, dict):
            continue

        content = message.get('content', {})
        if not isinstance(content, dict):
            continue

        # 最常见：content.parts
        parts = content.get('parts')
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, str) and p:
                    out.append(p)

        # 一些类型：content.text / content.content
        for k in ('text', 'content'):
            v = content.get(k)
            if isinstance(v, str) and v:
                out.append(v)

        # thoughts: [{content, summary, ...}, ...]
        if content.get('content_type') == 'thoughts':
            thoughts = content.get('thoughts')
            if isinstance(thoughts, list):
                for t in thoughts:
                    if not isinstance(t, dict):
                        continue
                    for k in ('content', 'summary'):
                        v = t.get(k)
                        if isinstance(v, str) and v:
                            out.append(v)

    return "\n".join(out)


@dataclass(frozen=True)
class SearchDoc:
    chat_id: str
    category: str
    title: str
    file_path: str
    text_norm: str
    text_view: str


class FolderSearchIndex:
    def __init__(self, folder: str, folder_path: Path):
        self.folder = folder
        self.folder_path = folder_path
        self.docs: List[SearchDoc] = []
        self.token_index: Dict[str, Set[int]] = {}
        self.cjk_char_index: Dict[str, Set[int]] = {}
        self.built_at = 0.0


class ConversationSearcher:
    """按 folder 构建/缓存索引，提供高速搜索。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._indexes: Dict[str, FolderSearchIndex] = {}
        self._build_events: Dict[str, threading.Event] = {}
        self._build_errors: Dict[str, str] = {}
        self._building: Set[str] = set()

    def schedule_build(self, folder: str, folder_path: Path) -> None:
        """后台预热构建索引，不阻塞接口返回。"""
        folder = (folder or "").strip()
        if not folder:
            return

        with self._lock:
            if folder in self._indexes or folder in self._building:
                return
            ev = self._build_events.get(folder)
            if not ev:
                ev = threading.Event()
                self._build_events[folder] = ev
            self._building.add(folder)

        t = threading.Thread(
            target=self._build_index_safe,
            args=(folder, folder_path),
            daemon=True,
        )
        t.start()

    def ensure_index(self, folder: str, folder_path: Path, timeout_sec: float = 0.0) -> FolderSearchIndex:
        """确保索引存在。timeout_sec>0 时会等待后台构建完成。"""
        folder = (folder or "").strip()
        if not folder:
            raise ValueError("folder is required")

        with self._lock:
            idx = self._indexes.get(folder)
            if idx:
                return idx
            ev = self._build_events.get(folder)
            if not ev:
                ev = threading.Event()
                self._build_events[folder] = ev

            # 如果没在构建，就同步构建（保证搜索不出错）
            if folder not in self._building:
                self._building.add(folder)
                self._build_index_safe(folder, folder_path)
                idx = self._indexes.get(folder)
                if not idx:
                    raise RuntimeError(self._build_errors.get(folder) or "index build failed")
                return idx

        if timeout_sec > 0:
            ev.wait(timeout=timeout_sec)

        with self._lock:
            idx = self._indexes.get(folder)
            if idx:
                return idx
            err = self._build_errors.get(folder)
            if err:
                raise RuntimeError(err)
            raise RuntimeError("index is still building")

    def search(self, folder: str, folder_path: Path, q: str, limit: int = 50) -> Dict:
        q_norm = _normalize_query(q)
        if not q_norm:
            return {
                'query': q,
                'folder': folder,
                'ready': True,
                'results': [],
                'stats': {'docCount': 0, 'tookMs': 0},
            }

        t0 = time.perf_counter()
        try:
            # 给后台预热一点时间；如果仍在构建则返回 ready=false 让前端轮询
            idx = self.ensure_index(folder, folder_path, timeout_sec=0.25)
        except RuntimeError as e:
            msg = str(e).lower()
            if 'still building' in msg:
                took_ms = int((time.perf_counter() - t0) * 1000)
                return {
                    'query': q,
                    'folder': folder,
                    'ready': False,
                    'results': [],
                    'stats': {'docCount': 0, 'tookMs': took_ms},
                }
            raise

        results = self._search_in_index(idx, q_norm, limit=max(1, min(int(limit or 50), 200)))
        took_ms = int((time.perf_counter() - t0) * 1000)

        return {
            'query': q,
            'folder': folder,
            'ready': True,
            'results': results,
            'stats': {'docCount': len(idx.docs), 'tookMs': took_ms},
        }

    def _build_index_safe(self, folder: str, folder_path: Path) -> None:
        try:
            self._build_index(folder, folder_path)
        except Exception as e:
            with self._lock:
                self._build_errors[folder] = str(e)
        finally:
            with self._lock:
                self._building.discard(folder)
                ev = self._build_events.get(folder)
                if ev:
                    ev.set()

    def _rebuild_token_indexes(self, idx: FolderSearchIndex) -> None:
        idx.token_index = {}
        idx.cjk_char_index = {}

        for doc_index, doc in enumerate(idx.docs):
            blob_norm = doc.text_norm or ""

            for tok in set(_ASCII_TOKEN_RE.findall(blob_norm)):
                s = idx.token_index.get(tok)
                if s is None:
                    s = set()
                    idx.token_index[tok] = s
                s.add(doc_index)

            cjk_chars = {ch for ch in blob_norm if _is_cjk(ch)}
            for ch in cjk_chars:
                s = idx.cjk_char_index.get(ch)
                if s is None:
                    s = set()
                    idx.cjk_char_index[ch] = s
                s.add(doc_index)

    def _build_index(self, folder: str, folder_path: Path) -> None:
        if not folder_path.exists() or not folder_path.is_dir():
            raise FileNotFoundError(f"folder not found: {folder}")

        new_idx = FolderSearchIndex(folder=folder, folder_path=folder_path)

        # Special folders (Claude/Gemini) are container formats, not one-conversation-per-file.
        # Ensure scanner has had a chance to detect/load special caches even if search is called first.
        try:
            scanner.scan_all_conversations(folder)
        except Exception:
            pass
        special = scanner.get_special_folder_cache(folder)
        if special and isinstance(special.get('kind'), str):
            kind = special.get('kind')
            listing = special.get('listing') or {}

            if kind == 'claude':
                claude_cache = special.get('claude_cache')
                by_uuid = getattr(claude_cache, 'by_uuid', {}) if claude_cache else {}
                by_project_uuid = getattr(claude_cache, 'by_project_uuid', {}) if claude_cache else {}
                for category, items in (listing or {}).items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        chat_id = (it or {}).get('id')
                        title = (it or {}).get('title') or ''
                        if not chat_id:
                            continue

                        if isinstance(chat_id, str) and chat_id.startswith('project__'):
                            pid = chat_id[len('project__'):]
                            pr = by_project_uuid.get(pid)
                            if not pr:
                                continue
                            conv = normalize_claude_project(pr.raw, memory=getattr(pr, 'memory', '') or '')
                        else:
                            if chat_id not in by_uuid:
                                continue
                            rec = by_uuid.get(chat_id)
                            conv = normalize_claude_conversation(rec.raw)

                        blob = extract_search_text_from_normalized(conv)
                        blob_view = _normalize_space(blob)
                        blob_norm = blob_view.lower()
                        new_idx.docs.append(SearchDoc(
                            chat_id=str(chat_id),
                            category=str(category),
                            title=str(title),
                            file_path=str(special.get('src') or ''),
                            text_norm=blob_norm,
                            text_view=blob_view,
                        ))

                self._rebuild_token_indexes(new_idx)
                with self._lock:
                    new_idx.built_at = time.time()
                    self._indexes[folder] = new_idx
                return

            if kind == 'gemini':
                gemini_cache = special.get('gemini_cache')
                by_id = getattr(gemini_cache, 'by_id', {}) if gemini_cache else {}
                for category, items in (listing or {}).items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        chat_id = (it or {}).get('id')
                        title = (it or {}).get('title') or ''
                        if not chat_id or chat_id not in by_id:
                            continue
                        rec = by_id.get(chat_id)
                        conv = normalize_gemini_activity(rec, folder=folder)
                        blob = extract_search_text_from_normalized(conv)
                        blob_view = _normalize_space(blob)
                        blob_norm = blob_view.lower()
                        new_idx.docs.append(SearchDoc(
                            chat_id=str(chat_id),
                            category=str(category),
                            title=str(title),
                            file_path=str(special.get('src') or ''),
                            text_norm=blob_norm,
                            text_view=blob_view,
                        ))

                self._rebuild_token_indexes(new_idx)
                with self._lock:
                    new_idx.built_at = time.time()
                    self._indexes[folder] = new_idx
                return

        # 递归遍历目录，支持多级分类
        for json_file in folder_path.rglob("*.json"):
            if not json_file.is_file():
                continue

            relative_dir = json_file.parent.relative_to(folder_path)
            if str(relative_dir) in (".", ""):
                category = "全部"
            else:
                category = str(relative_dir).replace("\\", "/")

            title_from_name, chat_id = _parse_filename(json_file.stem)

            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                # 跳过坏文件，保证整体索引不失败
                continue

            # Only index ChatGPT-style conversation objects.
            if not isinstance(data, dict):
                continue

            body_text = _extract_search_text(data)
            blob = f"{title_from_name}\n{body_text}"
            blob_view = _normalize_space(blob)
            blob_norm = blob_view.lower()

            doc_index = len(new_idx.docs)
            new_idx.docs.append(
                SearchDoc(
                    chat_id=chat_id,
                    category=category,
                    title=title_from_name,
                    file_path=str(json_file),
                    text_norm=blob_norm,
                    text_view=blob_view,
                )
            )

            # token 索引（英文/数字）
            for tok in set(_ASCII_TOKEN_RE.findall(blob_norm)):
                s = new_idx.token_index.get(tok)
                if s is None:
                    s = set()
                    new_idx.token_index[tok] = s
                s.add(doc_index)

            # CJK 字符索引（中文）
            # 用 unique 字符，避免重复添加
            cjk_chars = {ch for ch in blob_norm if _is_cjk(ch)}
            for ch in cjk_chars:
                s = new_idx.cjk_char_index.get(ch)
                if s is None:
                    s = set()
                    new_idx.cjk_char_index[ch] = s
                s.add(doc_index)

        new_idx.built_at = time.time()

        with self._lock:
            self._indexes[folder] = new_idx
            self._build_errors.pop(folder, None)

    def _search_in_index(self, idx: FolderSearchIndex, q_norm: str, limit: int) -> List[Dict]:
        # 候选集合：优先用 CJK 字符交集，否则用 token
        cjk_terms = [ch for ch in q_norm if _is_cjk(ch)]
        cjk_terms = list(dict.fromkeys(cjk_terms))  # 去重保序

        token_terms = [t for t in _ASCII_TOKEN_RE.findall(q_norm)]
        token_terms = list(dict.fromkeys(token_terms))

        candidates: Optional[Set[int]] = None

        if cjk_terms:
            # 只取前 N 个字符做交集，避免 query 过长导致交集过小/过慢
            for ch in cjk_terms[:8]:
                posting = idx.cjk_char_index.get(ch)
                if not posting:
                    candidates = set()
                    break
                candidates = posting.copy() if candidates is None else (candidates & posting)
                if not candidates:
                    break

        if (candidates is None or not candidates) and token_terms:
            for tok in token_terms:
                posting = idx.token_index.get(tok)
                if not posting:
                    candidates = set()
                    break
                candidates = posting.copy() if candidates is None else (candidates & posting)
                if not candidates:
                    break

        if candidates is None:
            candidates = set(range(len(idx.docs)))

        # 精确 substring 校验 + 简单排序
        hits: List[Tuple[int, int]] = []  # (score, doc_index)
        for di in candidates:
            doc = idx.docs[di]
            if q_norm not in doc.text_norm:
                continue

            score = 0
            title_norm = _normalize_query(doc.title)
            if q_norm in title_norm:
                score += 100
            # 越早出现越靠前
            pos = doc.text_norm.find(q_norm)
            if pos >= 0:
                score += max(0, 50 - min(pos, 50))
            hits.append((score, di))

        hits.sort(key=lambda x: x[0], reverse=True)

        out: List[Dict] = []
        for score, di in hits[:limit]:
            doc = idx.docs[di]
            pos = doc.text_norm.find(q_norm)
            snippet = _make_snippet(doc.text_view, pos, len(q_norm))
            out.append({
                'id': doc.chat_id,
                'category': doc.category,
                'title': doc.title,
                'snippet': snippet,
                'score': score,
            })

        return out


def _make_snippet(text_view: str, pos: int, q_len: int, radius: int = 60) -> str:
    if pos < 0:
        return ""
    start = max(0, pos - radius)
    end = min(len(text_view), pos + q_len + radius)
    snippet = text_view[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text_view):
        snippet = snippet + "…"
    return snippet


# 全局搜索器实例
searcher = ConversationSearcher()
