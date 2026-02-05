"""搜索索引模块 - 为标题/内容提供高速搜索"""

from __future__ import annotations

import json
import atexit
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
_ASCII_PREFIX_MIN_LEN = 3
_ASCII_PREFIX_MAX_LEN = 8
_ASCII_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "with",
}


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


def _looks_like_chatgpt_conversation_json(path: Path) -> bool:
    """Fast sniffing to avoid loading huge non-conversation JSON blobs (primarily JSON arrays).

    We accept any JSON object and let the slow path (json.load + schema checks) decide whether
    it is indexable. Rejecting objects here can easily drop valid exports with alternate schemas
    (e.g. Gemini per-conversation dumps).
    """
    try:
        with open(path, "rb") as f:
            head = f.read(64 * 1024)
        if not head:
            return False

        # Find first non-whitespace byte
        first = None
        for b in head:
            if b not in b" \t\r\n":
                first = b
                break
        if first is None:
            return False

        # Many batch exports are JSON arrays; our indexer only supports per-conversation objects here.
        if first == ord(b"["):
            return False

        return first == ord(b"{")
    except Exception:
        # If sniffing fails, fall back to the old behavior (attempt to load/parse).
        return True


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
        # Prefix postings for incremental search (e.g. "dimensiona" -> "dimensional").
        # We only store a limited prefix range to keep memory bounded.
        self.token_prefix_index: Dict[str, Set[int]] = {}
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
        self._build_executor = ThreadPoolExecutor(max_workers=self._default_build_workers())
        atexit.register(self._shutdown_executor)
        # If a mutation happens while building, mark the folder dirty so we rebuild once more
        # after the in-flight build finishes (avoids stale indexes).
        self._dirty: Set[str] = set()
        # Cache per-folder query results so polling (scope=all) doesn't redo expensive work.
        self._search_cache: Dict[Tuple[str, str, int, float], List[Dict]] = {}
        self._search_cache_max = 256

    def _shutdown_executor(self) -> None:
        try:
            self._build_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            try:
                self._build_executor.shutdown(wait=False)
            except Exception:
                pass

    @staticmethod
    def _default_build_workers() -> int:
        # Index building is disk I/O + some CPU; too many threads increases contention.
        cpu = os.cpu_count() or 4
        return max(2, min(4, cpu // 2))

    def _submit_build(self, folder: str, folder_path: Path) -> None:
        try:
            self._build_executor.submit(self._build_index_safe, folder, folder_path)
        except Exception:
            t = threading.Thread(
                target=self._build_index_safe,
                args=(folder, folder_path),
                daemon=True,
            )
            t.start()

    def invalidate(self, folder: str) -> None:
        """Drop an existing index so it can be rebuilt on next search/schedule_build.

        Used after rename/delete operations where exports are mutated (file rename/unlink)
        or where an overlay file changes (Claude overrides).
        """
        folder = (folder or "").strip()
        if not folder:
            return
        with self._lock:
            self._indexes.pop(folder, None)
            self._build_errors.pop(folder, None)
            self._dirty.add(folder)
            ev = self._build_events.get(folder)
            if ev:
                ev.clear()
            try:
                keys = [k for k in self._search_cache.keys() if k and k[0] == folder]
                for k in keys:
                    self._search_cache.pop(k, None)
            except Exception:
                pass

    def invalidate_all(self) -> None:
        """Drop all cached indexes."""
        with self._lock:
            self._indexes.clear()
            self._build_errors.clear()
            self._dirty = set(self._build_events.keys())
            for ev in self._build_events.values():
                try:
                    ev.clear()
                except Exception:
                    pass
            self._search_cache.clear()

    def schedule_build(self, folder: str, folder_path: Path) -> None:
        """后台预热构建索引，不阻塞接口返回。"""
        folder = (folder or "").strip()
        if not folder:
            return

        with self._lock:
            if folder in self._building:
                # A build is already in-flight. Do not mark dirty here, otherwise polling
                # (e.g. /api/search?scope=all) can create an endless rebuild loop.
                # Mutations should call invalidate()/invalidate_all() to mark dirty explicitly.
                return
            if folder in self._indexes and folder not in self._dirty:
                return
            ev = self._build_events.get(folder)
            if not ev:
                ev = threading.Event()
                self._build_events[folder] = ev
            self._building.add(folder)
            self._dirty.discard(folder)

        self._submit_build(folder, folder_path)

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

        eff_limit = max(1, min(int(limit or 50), 200))
        cache_key = (folder, q_norm, eff_limit, float(getattr(idx, "built_at", 0.0) or 0.0))
        with self._lock:
            cached = self._search_cache.get(cache_key)
        if cached is not None:
            results = cached
        else:
            results = self._search_in_index(idx, q_norm, limit=eff_limit)
            with self._lock:
                self._search_cache[cache_key] = results
                while len(self._search_cache) > self._search_cache_max:
                    try:
                        self._search_cache.pop(next(iter(self._search_cache)))
                    except Exception:
                        break
        took_ms = int((time.perf_counter() - t0) * 1000)

        return {
            'query': q,
            'folder': folder,
            'ready': True,
            'results': results,
            'stats': {'docCount': len(idx.docs), 'tookMs': took_ms},
        }

    def _build_index_safe(self, folder: str, folder_path: Path) -> None:
        should_rebuild = False
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
                if folder in self._dirty:
                    # Another mutation happened while building; rebuild once more.
                    should_rebuild = True
                    self._dirty.discard(folder)
                    self._building.add(folder)
                    if ev:
                        ev.clear()

            if should_rebuild:
                self._submit_build(folder, folder_path)

    def _rebuild_token_indexes(self, idx: FolderSearchIndex) -> None:
        idx.token_index = {}
        idx.token_prefix_index = {}
        idx.cjk_char_index = {}

        for doc_index, doc in enumerate(idx.docs):
            blob_norm = doc.text_norm or ""

            for tok in set(_ASCII_TOKEN_RE.findall(blob_norm)):
                s = idx.token_index.get(tok)
                if s is None:
                    s = set()
                    idx.token_index[tok] = s
                s.add(doc_index)

                if len(tok) >= _ASCII_PREFIX_MIN_LEN:
                    max_len = min(_ASCII_PREFIX_MAX_LEN, len(tok))
                    for plen in range(_ASCII_PREFIX_MIN_LEN, max_len + 1):
                        p = tok[:plen]
                        ps = idx.token_prefix_index.get(p)
                        if ps is None:
                            ps = set()
                            idx.token_prefix_index[p] = ps
                        ps.add(doc_index)

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

                        # Apply persisted title overrides (stored in listing) so:
                        # - searching by the renamed title works
                        # - snippet starts with the new title instead of the old export title
                        if isinstance(conv, dict) and isinstance(title, str) and title.strip():
                            conv["title"] = title.strip()

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

            if not _looks_like_chatgpt_conversation_json(json_file):
                continue

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

                if len(tok) >= _ASCII_PREFIX_MIN_LEN:
                    max_len = min(_ASCII_PREFIX_MAX_LEN, len(tok))
                    for plen in range(_ASCII_PREFIX_MIN_LEN, max_len + 1):
                        p = tok[:plen]
                        ps = new_idx.token_prefix_index.get(p)
                        if ps is None:
                            ps = set()
                            new_idx.token_prefix_index[p] = ps
                        ps.add(doc_index)

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
        primary_tokens = [t for t in token_terms if (len(t) >= 3 and t not in _ASCII_STOPWORDS)]
        if not primary_tokens:
            primary_tokens = token_terms
        is_long_ascii_query = (len(q_norm) >= 28 and len(primary_tokens) >= 3 and not cjk_terms)

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

        if (candidates is None or not candidates) and primary_tokens:
            postings: List[Tuple[int, Set[int]]] = []
            for tok in primary_tokens:
                posting = idx.token_index.get(tok)
                if (not posting) and (len(tok) >= _ASCII_PREFIX_MIN_LEN):
                    key = tok if len(tok) <= _ASCII_PREFIX_MAX_LEN else tok[:_ASCII_PREFIX_MAX_LEN]
                    posting = idx.token_prefix_index.get(key)
                if not posting:
                    candidates = set()
                    break
                postings.append((len(posting), posting))

            if candidates is None and postings:
                postings.sort(key=lambda x: x[0])
                for _, posting in postings:
                    candidates = posting.copy() if candidates is None else (candidates & posting)
                    if not candidates:
                        break

        if candidates is None:
            candidates = set(range(len(idx.docs)))

        # 精确 substring 校验 + 简单排序
        hits: List[Tuple[int, int]] = []  # (score, doc_index)
        for di in candidates:
            doc = idx.docs[di]
            pos_phrase = -1
            if not is_long_ascii_query:
                pos_phrase = doc.text_norm.find(q_norm)
                if pos_phrase < 0:
                    continue

            score = 0
            title_norm = _normalize_query(doc.title)
            if q_norm in title_norm:
                score += 100

            pos = pos_phrase
            if is_long_ascii_query:
                if primary_tokens and all(t in title_norm for t in primary_tokens):
                    score += 80
                if pos < 0 and primary_tokens:
                    best = -1
                    for t in primary_tokens[:6]:
                        p = doc.text_norm.find(t)
                        if p >= 0 and (best < 0 or p < best):
                            best = p
                    pos = best

            # 越早出现越靠前
            if pos >= 0:
                score += max(0, 50 - min(pos, 50))
            hits.append((score, di))

        hits.sort(key=lambda x: x[0], reverse=True)

        out: List[Dict] = []
        for score, di in hits[:limit]:
            doc = idx.docs[di]
            pos = -1
            q_len = len(q_norm)
            if not is_long_ascii_query:
                pos = doc.text_norm.find(q_norm)
            if pos < 0 and is_long_ascii_query and primary_tokens:
                best = -1
                best_len = 0
                for t in primary_tokens[:6]:
                    p = doc.text_norm.find(t)
                    if p >= 0 and (best < 0 or p < best):
                        best = p
                        best_len = len(t)
                pos = best
                if best_len:
                    q_len = best_len
            snippet = _make_snippet(doc.text_view, pos, q_len)
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
