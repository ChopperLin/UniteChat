"""External export formats (Claude / Gemini) loaders.

This project originally supported ChatGPT exported JSON files (one conversation per JSON).
Claude and Geminis use very different structures:
- Claude: a single large conversations.json containing many conversations.
- Gemini (Google Takeout): MyActivity.html (or MyActivity.json) under Takeout/.../Gemini Apps/.

This module provides:
- Folder format detection
- Efficient(ish) loading with mtime-based caching support
- Minimal normalization helpers (timestamps, html->markdown-ish)

The goal is to keep the frontend unchanged by normalizing these sources into the same
"{title, messages, meta}" shape used by the existing API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import hashlib
import html as _html
import json
import re


_ANSI_NARROW_NBSP = "\u202f"


def _iso_to_epoch_seconds(value: Optional[str]) -> Optional[float]:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None

    # Common cases: 2025-10-15T10:01:51.267292Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.timestamp()


def _parse_takeout_ts_to_epoch_seconds(value: str) -> Optional[float]:
    """Parse timestamps like: 'Jan 31, 2026, 6:15:01 AM PST'.

    Takeout sometimes uses U+202F as a narrow no-break space before AM/PM.
    """
    if not value or not isinstance(value, str):
        return None

    s = value.strip().replace(_ANSI_NARROW_NBSP, " ")
    # Normalize spaces
    s = re.sub(r"\s+", " ", s)

    # English style: Jan 31, 2026, 6:15:01 AM PST
    m = re.match(
        r"^(?P<mon>[A-Za-z]{3}) (?P<day>\d{1,2}), (?P<year>\d{4}), (?P<h>\d{1,2}):(?P<mi>\d{2}):(?P<se>\d{2}) (?P<ampm>AM|PM) (?P<tz>[A-Za-z]{2,4})$",
        s,
    )
    if not m:
        # Chinese style: 2026年1月10日 06:01:02 PST
        m2 = re.match(
            r"^(?P<year>\d{4})年(?P<mon>\d{1,2})月(?P<day>\d{1,2})日\s*(?:(?P<cn_ampm>上午|下午)\s*)?(?P<h>\d{1,2}):(?P<mi>\d{2}):(?P<se>\d{2})\s*(?P<tz>[A-Za-z]{2,4})$",
            s,
        )
        if not m2:
            return None

        hour = int(m2.group("h"))
        cn_ampm = (m2.group("cn_ampm") or "").strip()
        if cn_ampm == "下午" and hour != 12:
            hour += 12
        if cn_ampm == "上午" and hour == 12:
            hour = 0

        tz = (m2.group("tz") or "").upper()
        tz_offsets = {
            "UTC": 0,
            "GMT": 0,
            "PST": -8,
            "PDT": -7,
            "CST": 8,   # China Standard Time
            "CCT": 8,
        }
        offset_hours = tz_offsets.get(tz, 0)
        tzinfo = timezone(timedelta(hours=offset_hours))

        try:
            dt = datetime(
                int(m2.group("year")),
                int(m2.group("mon")),
                int(m2.group("day")),
                hour,
                int(m2.group("mi")),
                int(m2.group("se")),
                tzinfo=tzinfo,
            )
            return dt.timestamp()
        except Exception:
            return None

    month_map = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }
    mon = month_map.get(m.group("mon"))
    if not mon:
        return None

    hour = int(m.group("h"))
    ampm = m.group("ampm")
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0

    tz = m.group("tz").upper()
    tz_offsets = {
        "UTC": 0,
        "GMT": 0,
        "PST": -8,
        "PDT": -7,
        "CST": 8,   # China Standard Time
        "CCT": 8,
    }
    offset_hours = tz_offsets.get(tz)
    if offset_hours is None:
        # Unknown timezone; fall back to naive local time interpretation.
        offset_hours = 0

    tzinfo = timezone(timedelta(hours=offset_hours))

    try:
        dt = datetime(
            int(m.group("year")),
            mon,
            int(m.group("day")),
            hour,
            int(m.group("mi")),
            int(m.group("se")),
            tzinfo=tzinfo,
        )
        return dt.timestamp()
    except Exception:
        return None


def _strip_tags_keep_basic_md(html_text: str) -> str:
    """Best-effort HTML -> Markdown-ish plain text.

    - Converts a subset of tags (<p>, <br>, <h*>, <li>, <pre><code>) to readable markdown.
    - Drops the rest.

    This is intentionally conservative to keep the frontend unchanged (react-markdown).
    """
    if not html_text:
        return ""

    s = str(html_text)
    s = _html.unescape(s)

    # Normalize newlines early
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # Fenced code blocks: protect them from later whitespace collapsing.
    code_blocks: List[str] = []

    def _code_block(m: re.Match) -> str:
        body = m.group(1) or ""
        # Remove remaining tags inside code
        body = re.sub(r"<[^>]+>", "", body)
        body = _html.unescape(body)
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        body = body.strip("\n")
        fenced = f"\n```\n{body}\n```\n"
        idx = len(code_blocks)
        code_blocks.append(fenced)
        return f"\n@@@CODEBLOCK{idx}@@@\n"

    s = re.sub(r"<pre>\s*<code>(.*?)</code>\s*</pre>", _code_block, s, flags=re.IGNORECASE | re.DOTALL)

    # Inline formatting
    s = re.sub(r"<\s*strong\s*>", "**", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*strong\s*>", "**", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*em\s*>", "_", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*em\s*>", "_", s, flags=re.IGNORECASE)

    # Headings
    for level in range(1, 7):
        s = re.sub(rf"<\s*h{level}[^>]*>", f"\n\n{'#' * min(level, 4)} ", s, flags=re.IGNORECASE)
        s = re.sub(rf"<\s*/\s*h{level}\s*>", "\n\n", s, flags=re.IGNORECASE)

    # Paragraphs + line breaks
    s = re.sub(r"<\s*p[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*p\s*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)

    # Lists
    s = re.sub(r"<\s*li[^>]*>", "\n- ", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*li\s*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*ol\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*ul\s*>", "\n", s, flags=re.IGNORECASE)

    # Links: keep as markdown
    s = re.sub(r"<\s*a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", lambda m: f"[{re.sub(r'<[^>]+>', '', m.group(2) or '').strip() or m.group(1)}]({m.group(1)})", s, flags=re.IGNORECASE | re.DOTALL)

    # Inline code (best-effort): <code>...</code>
    s = re.sub(r"<\s*code[^>]*>", "`", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*code\s*>", "`", s, flags=re.IGNORECASE)

    # Drop remaining tags
    s = re.sub(r"<[^>]+>", "", s)

    # Cleanup whitespace (outside fenced code blocks)
    s = s.replace("\u00a0", " ")
    s = s.replace(_ANSI_NARROW_NBSP, " ")
    # Collapse excessive spaces/tabs, but keep indentation at line starts intact.
    s = re.sub(r"(?m)(?<!^)[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    # Fix common list rendering artifacts: empty bullet followed by a code span.
    s = re.sub(r"\n-\s*\n\s*`", "\n- `", s)
    s = re.sub(r"\n-\s*\n\s*\*\*", "\n- **", s)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        s = s.replace(f"@@@CODEBLOCK{i}@@@", block)

    return s.strip()


@dataclass
class ChatSource:
    kind: str  # 'chatgpt_file' | 'claude' | 'gemini'
    folder: str
    category: str
    chat_id: str
    file_path: Path
    extra: Dict[str, Any]


@dataclass
class ClaudeConversationRecord:
    uuid: str
    name: str
    created_at: Optional[float]
    updated_at: Optional[float]
    raw: Dict[str, Any]


@dataclass
class ClaudeExportCache:
    mtime: float
    conversations: List[ClaudeConversationRecord]
    by_uuid: Dict[str, ClaudeConversationRecord]
    projects: List['ClaudeProjectRecord']
    by_project_uuid: Dict[str, 'ClaudeProjectRecord']


@dataclass
class ClaudeProjectRecord:
    uuid: str
    name: str
    description: str
    prompt_template: str
    created_at: Optional[float]
    updated_at: Optional[float]
    memory: str
    raw: Dict[str, Any]


def detect_claude_folder(folder_path: Path) -> Optional[Path]:
    p = folder_path / "conversations.json"
    if p.exists() and p.is_file():
        return p
    return None


def load_claude_export(folder_name: str, folder_path: Path) -> ClaudeExportCache:
    conversations_path = detect_claude_folder(folder_path)
    if not conversations_path:
        raise FileNotFoundError("conversations.json not found")

    mtime = float(conversations_path.stat().st_mtime)

    with open(conversations_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations: List[ClaudeConversationRecord] = []
    by_uuid: Dict[str, ClaudeConversationRecord] = {}

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            uuid = str(item.get("uuid") or "").strip()
            if not uuid:
                continue
            name = str(item.get("name") or item.get("title") or "Untitled").strip() or "Untitled"
            created_at = _iso_to_epoch_seconds(item.get("created_at"))
            updated_at = _iso_to_epoch_seconds(item.get("updated_at"))
            rec = ClaudeConversationRecord(
                uuid=uuid,
                name=name,
                created_at=created_at,
                updated_at=updated_at,
                raw=item,
            )
            conversations.append(rec)
            by_uuid[uuid] = rec

    # Projects are exported separately; they don't include a reliable conversation linkage.
    projects: List[ClaudeProjectRecord] = []
    by_project_uuid: Dict[str, ClaudeProjectRecord] = {}
    project_memories: Dict[str, str] = {}
    memories_path = folder_path / "memories.json"
    if memories_path.exists() and memories_path.is_file():
        try:
            with open(memories_path, "r", encoding="utf-8") as f:
                mem_data = json.load(f)
            if isinstance(mem_data, list) and mem_data:
                pm = mem_data[0].get("project_memories")
                if isinstance(pm, dict):
                    for k, v in pm.items():
                        if isinstance(k, str) and isinstance(v, str):
                            project_memories[k] = v
        except Exception:
            project_memories = {}

    projects_path = folder_path / "projects.json"
    if projects_path.exists() and projects_path.is_file():
        try:
            with open(projects_path, "r", encoding="utf-8") as f:
                proj_data = json.load(f)
            if isinstance(proj_data, list):
                for item in proj_data:
                    if not isinstance(item, dict):
                        continue
                    uuid = str(item.get("uuid") or "").strip()
                    if not uuid:
                        continue
                    name = str(item.get("name") or "Untitled").strip() or "Untitled"
                    description = str(item.get("description") or "").strip()
                    prompt_template = str(item.get("prompt_template") or "").strip()
                    created_at = _iso_to_epoch_seconds(item.get("created_at"))
                    updated_at = _iso_to_epoch_seconds(item.get("updated_at"))
                    memory = str(project_memories.get(uuid) or "").strip()
                    rec = ClaudeProjectRecord(
                        uuid=uuid,
                        name=name,
                        description=description,
                        prompt_template=prompt_template,
                        created_at=created_at,
                        updated_at=updated_at,
                        memory=memory,
                        raw=item,
                    )
                    projects.append(rec)
                    by_project_uuid[uuid] = rec
        except Exception:
            projects = []
            by_project_uuid = {}

    return ClaudeExportCache(
        mtime=mtime,
        conversations=conversations,
        by_uuid=by_uuid,
        projects=projects,
        by_project_uuid=by_project_uuid,
    )


@dataclass
class GeminiTurn:
    ts: Optional[float]
    prompt: str
    response_md: str
    attachments: List[str]  # relative paths from the folder root
    thread_key: str = ""  # best-effort: stable id if Takeout includes an app/share URL


@dataclass
class GeminiConversationRecord:
    chat_id: str
    title: str
    created_at: Optional[float]
    updated_at: Optional[float]
    turns: List[GeminiTurn]


@dataclass
class GeminiActivityCache:
    mtime: float
    activity_file: Path
    records: List[GeminiConversationRecord]
    by_id: Dict[str, GeminiConversationRecord]


def find_gemini_activity_file(folder_path: Path) -> Optional[Path]:
    # Try common canonical paths first
    candidates = [
        folder_path / "Takeout" / "My Activity" / "Gemini Apps" / "MyActivity.html",
        folder_path / "Takeout" / "My Activity" / "Gemini Apps" / "MyActivity.json",
        folder_path / "Takeout" / "Access Log Activity" / "My Activity" / "Gemini Apps" / "MyActivity.html",
        folder_path / "Takeout" / "Access Log Activity" / "My Activity" / "Gemini Apps" / "MyActivity.json",
        folder_path / "Takeout" / "我的活动" / "Gemini Apps" / "MyActivity.html",
        folder_path / "Takeout" / "我的活动" / "Gemini Apps" / "MyActivity.json",
        folder_path / "Takeout" / "我的活动" / "Gemini Apps" / "我的活动记录.html",
        folder_path / "Takeout" / "我的活动" / "Gemini Apps" / "我的活动记录.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p

    # Fallback: find activity file under Gemini Apps directory.
    takeout_root = folder_path / "Takeout"
    if not (takeout_root.exists() and takeout_root.is_dir()):
        return None

    # Prefer known filenames, but allow localized variants.
    preferred_names = {
        "myactivity.html",
        "myactivity.json",
        "我的活动记录.html",
        "我的活动记录.json",
    }

    gemini_dirs: List[Path] = []
    try:
        gemini_dirs = [p for p in takeout_root.rglob("Gemini Apps") if p.is_dir()]
    except Exception:
        gemini_dirs = []

    hits: List[Path] = []
    for gd in gemini_dirs:
        # 1) direct preferred names
        for name in preferred_names:
            p = gd / name
            if p.exists() and p.is_file():
                hits.append(p)
        # 2) any html/json in the folder
        hits.extend([p for p in gd.glob("*.html") if p.is_file()])
        hits.extend([p for p in gd.glob("*.json") if p.is_file()])

    if not hits:
        # Last fallback: search by old name in whole Takeout
        for ext in ("MyActivity.html", "MyActivity.json"):
            hits.extend(list(takeout_root.rglob(ext)))
        if not hits:
            return None

    def _score(p: Path) -> int:
        parts = [str(x).lower() for x in p.parts]
        score = 0
        if "gemini apps" in " ".join(parts):
            score += 10
        if "my activity" in " ".join(parts) or "我的活动" in "".join(parts):
            score += 3
        if p.name.lower() in preferred_names:
            score += 5
        if p.name.lower().endswith(".json"):
            score += 1  # json is slightly easier to parse, if present
        return score

    hits.sort(key=_score, reverse=True)
    return hits[0]


def detect_gemini_folder(folder_path: Path) -> Optional[Path]:
    return find_gemini_activity_file(folder_path)


_OUTER_CELL_SPLIT = '<div class="outer-cell'


def _sha1_id(seed: str) -> str:
    h = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()
    return h[:12]


def _extract_first_content_cell(chunk: str) -> str:
    # The first content-cell contains prompt + attachments + timestamp + response.
    marker = 'mdl-typography--body-1">'
    start = chunk.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    rest = chunk[start:]
    end = rest.find('</div><div class="content-cell')
    if end < 0:
        end = rest.find("</div></div></div>")
    if end < 0:
        return rest
    return rest[:end]


def _extract_title(chunk: str) -> str:
    m = re.search(r'mdl-typography--title\">(.*?)<br', chunk, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return "Gemini Apps"
    title = _strip_tags_keep_basic_md(m.group(1) or "")
    return title.strip() or "Gemini Apps"


def _extract_attachments(chunk: str, folder_path: Path, activity_file: Path) -> List[str]:
    attachments: List[str] = []

    # <a href="file"> labels
    for m in re.finditer(r'<a\s+href="([^"]+)"', chunk, flags=re.IGNORECASE):
        href = (m.group(1) or "").strip()
        if not href or href.startswith("http"):
            continue
        # Keep only local files
        attachments.append(href)

    # <img src="file">
    for m in re.finditer(r'<img\s+src="([^"]+)"', chunk, flags=re.IGNORECASE):
        src = (m.group(1) or "").strip()
        if not src or src.startswith("http"):
            continue
        attachments.append(src)

    # Normalize to folder-relative paths
    base_dir = activity_file.parent
    rel_base = base_dir.relative_to(folder_path)
    out: List[str] = []
    seen = set()
    for name in attachments:
        # Some names may be like "image_xxx" without extension; keep as-is.
        rel = (rel_base / name).as_posix()
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _extract_thread_key(chunk: str) -> str:
    """Best-effort thread id.

    Some Takeout variants may include a link back to the Gemini conversation (app/share).
    Many MyActivity.html exports do NOT include such ids; in that case we return "".
    """
    s = chunk or ""
    # Common patterns seen in the wild (not guaranteed to exist).
    patterns = [
        r"https?://gemini\.google\.com/(?:u/\d+/)?app/([A-Za-z0-9_-]{6,})",
        r"https?://gemini\.google\.com/(?:u/\d+/)?share/([A-Za-z0-9_-]{6,})",
        r"https?://g\.co/gemini/share/([A-Za-z0-9_-]{6,})",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m:
            return (m.group(0) or "").strip()
    return ""


def _extract_prompt(cell_html: str) -> str:
    # Most entries start with "Prompted <text><br>"
    s = cell_html.replace("\u00a0", " ").replace(_ANSI_NARROW_NBSP, " ")
    s = s.replace("&nbsp;", " ")

    # Prefer: substring between 'Prompted' and the first <br> (or timestamp marker if <br> is missing).
    m = re.search(r"Prompted\s*(.*)", s, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""

    after = m.group(1) or ""
    ts_label = _extract_timestamp_label(s) or ""
    end = -1
    if ts_label:
        end = after.find(ts_label)
    if end < 0:
        br = after.find("<br")
        end = br if br >= 0 else len(after)

    prompt_html = after[:end]
    prompt = _strip_tags_keep_basic_md(prompt_html)

    # Drop attachment-related suffix that sometimes appears inline.
    prompt = re.split(r"\bAttached\b|附加了|已附加|附件", prompt, maxsplit=1)[0]
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt


def _extract_timestamp_label(cell_html: str) -> Optional[str]:
    s = cell_html.replace(_ANSI_NARROW_NBSP, " ")
    # Examples:
    # - Jan 31, 2026, 6:15:01 AM PST<br>
    # - 2026年1月10日 06:01:02 PST<br>
    m = re.search(
        r"([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\s*[A-Za-z]{2,4})<br",
        s,
    )
    if not m:
        m = re.search(
            r"(\d{4}年\d{1,2}月\d{1,2}日\s*(?:上午|下午)?\s*\d{1,2}:\d{2}:\d{2}\s*[A-Za-z]{2,4})<br",
            s,
        )
    if not m:
        return None
    return (m.group(1) or "").strip()


def _extract_response_md(cell_html: str) -> str:
    def _cleanup(md: str) -> str:
        s = (md or "").lstrip()
        if not s:
            return ""

        # If we failed to slice out the prompt/timestamp region, remove common activity-log artifacts.
        # Examples:
        #   Prompted ...
        #   Jan 21, 2026, 7:07:34 AM PST
        #   2026年1月10日 06:01:02 PST
        s = re.sub(r"^Prompted\s+.*?(\n|$)", "", s, flags=re.IGNORECASE)

        # Remove attachment boilerplate that should be handled by attachment extraction.
        s = re.sub(r"^Attached\s+\d+\s+file(?:s)?\.?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^附加了\s*\d+\s*个文件\s*\.?\s*", "", s, flags=re.IGNORECASE)
        # Drop leading bullet links that point to local attachment files.
        s = re.sub(r"^(?:-\s*\[[^\]]+\]\([^)]*\)\s*)+", "", s, flags=re.IGNORECASE)
        s = re.sub(
            r"^([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\s*[A-Za-z]{2,4})(\n|$)",
            "",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"^(\d{4}年\d{1,2}月\d{1,2}日\s*(?:上午|下午)?\s*\d{1,2}:\d{2}:\d{2}\s*[A-Za-z]{2,4})(\n|$)",
            "",
            s,
            flags=re.IGNORECASE,
        )

        # Sometimes the timestamp gets embedded after attachments; drop any leading occurrence.
        s = re.sub(
            r"^\s*([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\s*[A-Za-z]{2,4})\s*",
            "",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"^\s*(\d{4}年\d{1,2}月\d{1,2}日\s*(?:上午|下午)?\s*\d{1,2}:\d{2}:\d{2}\s*[A-Za-z]{2,4})\s*",
            "",
            s,
            flags=re.IGNORECASE,
        )
        return s.strip()

    label = _extract_timestamp_label(cell_html)
    if not label:
        # No timestamp marker; strip whole cell then cleanup.
        return _cleanup(_strip_tags_keep_basic_md(cell_html))

    idx = cell_html.find(label)
    if idx < 0:
        return _cleanup(_strip_tags_keep_basic_md(cell_html))

    # Find the <br> right after the timestamp
    br_idx = cell_html.find("<br", idx)
    if br_idx < 0:
        return ""

    body = cell_html[br_idx:]
    return _cleanup(_strip_tags_keep_basic_md(body))


def load_gemini_activity(folder_name: str, folder_path: Path) -> GeminiActivityCache:
    activity_file = find_gemini_activity_file(folder_path)
    if not activity_file:
        raise FileNotFoundError("Gemini MyActivity file not found")

    mtime = float(activity_file.stat().st_mtime)

    if activity_file.suffix.lower() == ".json":
        # Not implemented yet; HTML exists in this workspace.
        raise NotImplementedError("MyActivity.json parsing is not implemented")

    text = activity_file.read_text("utf-8", errors="ignore")

    # Split into entries
    parts = text.split(_OUTER_CELL_SPLIT)
    if len(parts) <= 1:
        return GeminiActivityCache(mtime=mtime, activity_file=activity_file, records=[], by_id={})

    turns: List[GeminiTurn] = []
    for part in parts[1:]:
        chunk = _OUTER_CELL_SPLIT + part
        title = _extract_title(chunk)
        cell = _extract_first_content_cell(chunk)
        if not cell:
            continue

        prompt = _extract_prompt(cell)
        ts_label = _extract_timestamp_label(cell) or ""
        ts = _parse_takeout_ts_to_epoch_seconds(ts_label) if ts_label else None
        response_md = _extract_response_md(cell)
        attachments = _extract_attachments(chunk, folder_path=folder_path, activity_file=activity_file)

        # Filter out feedback-only activity entries.
        cell_text = _strip_tags_keep_basic_md(cell)
        if re.search(r"^\s*Gave feedback\s*:\s*", cell_text, flags=re.IGNORECASE):
            continue
        if re.search(r"^\s*提供了反馈\s*[:：]", cell_text, flags=re.IGNORECASE):
            continue

        # Skip empty records that would create blank "Gemini Apps" chats.
        if not (prompt.strip() or response_md.strip() or attachments):
            continue

        thread_key = _extract_thread_key(chunk)

        turns.append(GeminiTurn(
            ts=ts,
            prompt=prompt.strip(),
            response_md=response_md.strip(),
            attachments=attachments,
            thread_key=thread_key,
        ))

    def _tokenize_topic(s: str) -> set:
        if not isinstance(s, str):
            return set()
        s = s.lower().strip()
        if not s:
            return set()
        words = re.findall(r"[a-z0-9]{2,}", s)
        cjk = re.findall(r"[\u4e00-\u9fff]", s)
        toks = set(words)
        # Use only CJK bigrams; single characters are too noisy and cause over-merging.
        if cjk and len(cjk) >= 2:
            for i in range(len(cjk) - 1):
                toks.add(cjk[i] + cjk[i + 1])
        return toks

    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        u = a | b
        if not u:
            return 0.0
        return len(a & b) / len(u)

    def _group_turns_by_session(all_turns: List[GeminiTurn]) -> List[List[GeminiTurn]]:
        # Heuristic sessionization for Takeout HTML which lacks stable thread IDs.
        # Goal: strongly reduce over-splitting while limiting obvious cross-topic merges.
        turns_sorted = sorted(all_turns, key=lambda x: (1 if x.ts is None else 0, float(x.ts or 0.0)))
        groups: List[List[GeminiTurn]] = []

        MAX_GAP = 2 * 60 * 60        # always split if gap > 2 hours
        MID_GAP = 25 * 60            # if gap > 25 min, require some topic similarity
        SHORT_GAP = 5 * 60           # if gap > 5 min, allow hard split on low similarity
        SIM_THRESH = 0.08            # loose threshold
        HARD_SIM = 0.02              # very low similarity => likely new topic
        WINDOW = 4                   # keep only a few recent turns as the "topic"

        cur: List[GeminiTurn] = []
        recent_tok: List[set] = []
        topic: set = set()
        last_ts: Optional[float] = None
        last_turn_tok: set = set()

        for t in turns_sorted:
            # Prefer prompt for topic; response text is often long and generic.
            t_text = (t.prompt or "").strip() or (t.response_md or "").strip()
            t_tok = _tokenize_topic(t_text)

            if not cur:
                cur = [t]
                recent_tok = [set(t_tok)]
                topic = set(t_tok)
                last_ts = t.ts
                last_turn_tok = set(t_tok)
                continue

            gap = None
            if last_ts is not None and t.ts is not None:
                gap = float(t.ts) - float(last_ts)

            sim_topic = _jaccard(topic, t_tok) if t_tok else 0.0
            sim_last = _jaccard(last_turn_tok, t_tok) if t_tok else 0.0

            start_new = False
            if gap is not None and gap > MAX_GAP:
                start_new = True
            elif gap is not None and gap > MID_GAP and sim_topic < SIM_THRESH:
                start_new = True
            elif gap is not None and gap > SHORT_GAP and sim_last < HARD_SIM and sim_topic < SIM_THRESH:
                # Fast topic jump: split even if within the same hour.
                start_new = True

            if start_new:
                groups.append(cur)
                cur = [t]
                recent_tok = [set(t_tok)]
                topic = set(t_tok)
                last_turn_tok = set(t_tok)
            else:
                cur.append(t)
                recent_tok.append(set(t_tok))
                if len(recent_tok) > WINDOW:
                    recent_tok = recent_tok[-WINDOW:]
                topic = set()
                for ss in recent_tok:
                    topic |= ss
                last_turn_tok = set(t_tok)

            if t.ts is not None:
                last_ts = t.ts

        if cur:
            groups.append(cur)
        return groups

    # Grouping strategy:
    # - If Takeout provides a stable thread key (conversation URL), group by it (accurate).
    # - Otherwise, sessionize by time gap + topic similarity to avoid severe over-splitting.
    groups: List[List[GeminiTurn]] = []
    keyed: Dict[str, List[GeminiTurn]] = {}
    has_any_key = any(bool(t.thread_key) for t in turns)
    if has_any_key:
        for t in turns:
            k = t.thread_key or _sha1_id(f"fallback|{t.ts or ''}|{t.prompt}|{t.response_md}")
            keyed.setdefault(k, []).append(t)
        # Keep stable order by earliest timestamp.
        groups = list(keyed.values())
        groups.sort(key=lambda g: min([x.ts for x in g if x.ts is not None] or [0.0]))
    else:
        groups = _group_turns_by_session(turns)

    records: List[GeminiConversationRecord] = []
    by_id: Dict[str, GeminiConversationRecord] = {}

    for g in groups:
        ts_list = [x.ts for x in g if x.ts is not None]
        created_at = min(ts_list) if ts_list else None
        updated_at = max(ts_list) if ts_list else None
        first_prompt = next((x.prompt for x in g if x.prompt.strip()), "")
        first_prompt_norm = re.sub(r"\s+", " ", str(first_prompt or "")).strip()
        conv_title = (first_prompt_norm[:60] if first_prompt_norm else "Gemini Apps").strip() or "Gemini Apps"

        thread_key = next((x.thread_key for x in g if x.thread_key), "")
        if thread_key:
            chat_id = _sha1_id(f"{activity_file.as_posix()}|{thread_key}")
        else:
            seed = f"{activity_file.as_posix()}|{created_at or ''}|{updated_at or ''}|{first_prompt_norm}"
            chat_id = _sha1_id(seed)

        rec = GeminiConversationRecord(
            chat_id=chat_id,
            title=conv_title,
            created_at=created_at,
            updated_at=updated_at,
            turns=g,
        )
        records.append(rec)
        by_id[chat_id] = rec

    return GeminiActivityCache(mtime=mtime, activity_file=activity_file, records=records, by_id=by_id)
