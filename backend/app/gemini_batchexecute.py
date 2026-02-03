"""Gemini web export (batchexecute) parser.

Your `data/gemini_export_*/*.json` files appear to embed the raw Google `batchexecute`
response in `batchexecute_raw`.

We convert that nested array format into the same normalized API shape used by the
frontend:
{
  "title": str,
  "messages": [{"role": "user"|"assistant", "content": str, "ts": float?, ...}],
  "meta": {...}
}

This module is intentionally best-effort and schema-tolerant: Google can change the
wire format, and exports may omit thinking/citations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# Bump this when changing parsing behavior; exposed by /api/health?verbose=1.
PARSER_VERSION = "2026-02-03-10"


_BATCHEXECUTE_PREFIX = ")]}'"


def _iso_to_epoch_seconds(value: Optional[str]) -> Optional[float]:
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


def is_gemini_batchexecute_export(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("batchexecute_raw"), str) and (
        isinstance(data.get("conversation_id"), str) or isinstance(data.get("fetched_at"), str)
    )


def _strip_xssi_prefix(raw: str) -> str:
    s = raw or ""
    if s.startswith(_BATCHEXECUTE_PREFIX):
        nl = s.find("\n")
        s = s[nl + 1 :] if nl >= 0 else ""
    return s


_FRAME_MARKER_RE = re.compile(r"\n\d+\n\[\[")


def _extract_first_outer_json(raw: str) -> Optional[List[Any]]:
    """Extract the first JSON array part from a batchexecute response.

    batchexecute payloads often contain multiple length-framed chunks:
      <len>\n<json>\n<len>\n<json>...

    The first JSON chunk contains the actual conversation payload; later chunks
    are auxiliary telemetry. We locate the boundary by searching for the next
    framing marker, rather than trusting byte/char lengths.
    """

    s = _strip_xssi_prefix(raw)

    # Skip leading whitespace
    i = 0
    while i < len(s) and s[i].isspace():
        i += 1

    # Skip optional length header line
    j = i
    while j < len(s) and s[j].isdigit():
        j += 1
    if j > i:
        if j < len(s) and s[j] == "\r":
            j += 1
        if j < len(s) and s[j] == "\n":
            j += 1

    rest = s[j:]
    if not rest:
        return None

    m = _FRAME_MARKER_RE.search(rest)
    chunk = rest[: m.start()] if m else rest

    try:
        outer = json.loads(chunk)
    except Exception:
        return None

    if isinstance(outer, list):
        return outer
    return None


def _safe_str(x: Any) -> str:
    return x if isinstance(x, str) else ""


_ID_LIKE_RE = re.compile(r"^(?:c|r|rc)_[A-Za-z0-9_-]{6,}$")
_BASE64ISH_RE = re.compile(r"^[A-Za-z0-9+/=_-]{80,}$")


def _iter_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
        return
    if isinstance(obj, list):
        for it in obj:
            yield from _iter_strings(it)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
        return


def _pick_best_text(candidates: Sequence[str]) -> str:
    best = ""
    best_score = -1

    for s in candidates:
        if not isinstance(s, str):
            continue
        t = s.strip("\r\n ")
        if not t:
            continue
        if _ID_LIKE_RE.match(t):
            continue
        if _BASE64ISH_RE.match(t):
            continue

        # Heuristic scoring: prefer longer, multi-line, markdown-ish content.
        score = len(t)
        if "\n" in t:
            score += 80
        if "```" in t:
            score += 120
        if "#" in t or "*" in t or "- " in t:
            score += 20

        # De-prioritize URL-only strings.
        if score < 200 and (t.startswith("http://") or t.startswith("https://")):
            score -= 100

        if score > best_score:
            best_score = score
            best = t

    return best


# NOTE: Keep "thinking" detection conservative.
# Deep Research-style reports can mention the word "thinking" in normal prose; only treat
# it as thinking when it's clearly used as a label/header or an explicit <think> tag.
_THINKING_XML_RE = re.compile(r"</?think>", re.IGNORECASE)
_THINKING_HINT_EN_LABEL_RE = re.compile(r"(?:^|\n)\s*(?:thinking|thoughts?)\s*[:：]", re.IGNORECASE)
_THINKING_HINT_EN_HEADER_RE = re.compile(r"(?:^|\n)\s*#+\s*(?:thinking|thoughts?)\s*(?:$|\n)", re.IGNORECASE)

# Chinese hints are only treated as thinking when they are clearly used as a label/header
# (e.g., "思考:" or "# 思考"). Avoid matching common prose usage such as "归纳推理".
_THINKING_HINT_ZH_LABEL_RE = re.compile(
    r"(?:^|\n)\s*(?:思考过程|推理过程|思考)\s*[:：]",
    re.IGNORECASE,
)

_THINKING_HINT_ZH_HEADER_RE = re.compile(
    r"(?:^|\n)\s*#+\s*(?:思考过程|推理过程|思考)\s*(?:$|\n)",
    re.IGNORECASE,
)


_THINKING_STYLE_RE = re.compile(
    r"\b("
    r"investigating|analyzing|examining|unpacking|pinpointing|tracing|isolating|"
    r"verifying|assessing|understanding|reframing|refining|constructing|formulating|"
    r"diagnosing|evaluating|dissecting|connecting the dots|unveiling"
    r")\b",
    re.IGNORECASE,
)


_THINKING_NARRATION_RE = re.compile(
    r"\b(i\s*(?:am|'m)\s*(?:now|currently|about\s+to|going\s+to)\b|my\s+(?:focus|plan|strategy|goal)\b)",
    re.IGNORECASE,
)


def _thinking_score(text: str) -> int:
    t = (text or "").strip()
    if not t:
        return 0

    score = 0
    has_hint = (
        _THINKING_XML_RE.search(t) is not None
        or _THINKING_HINT_EN_LABEL_RE.search(t) is not None
        or _THINKING_HINT_EN_HEADER_RE.search(t) is not None
        or _THINKING_HINT_ZH_LABEL_RE.search(t) is not None
        or _THINKING_HINT_ZH_HEADER_RE.search(t) is not None
    )
    has_style = _THINKING_STYLE_RE.search(t) is not None
    has_narration = _THINKING_NARRATION_RE.search(t) is not None

    # Avoid misclassifying structured final answers. Style verbs (e.g. "understanding")
    # often appear in normal prose, so only count them when paired with explicit hint
    # or first-person narration.
    if not (has_hint or has_narration):
        return 0

    if has_hint:
        score += 80
    if has_style and (has_hint or has_narration):
        score += 40
    if has_narration:
        score += 60

    # Mild structure bonus (tie-breaker only).
    if t.startswith("**"):
        score += 10
    score += min(30, t.count("**") * 2)
    score += min(20, t.count("\n\n") * 1)

    return score


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for s in items:
        if not s:
            continue
        key = s.strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


_FENCED_CODEBLOCK_RE = re.compile(r"(^```[\s\S]*?^```\s*$)", re.MULTILINE)


def _normalize_math_delimiters(md: str) -> str:
    r"""Best-effort math normalization for react-markdown + remark-math.

    - Converts LaTeX-style delimiters \(...\), \[...\] into $...$ / $$...$$
    - Normalizes single-line $$...$$ into a stable multi-line display block

    This is intentionally conservative and skips fenced code blocks.
    """

    if not isinstance(md, str) or not md.strip():
        return md or ""

    parts: List[Tuple[bool, str]] = []
    last = 0
    for m in _FENCED_CODEBLOCK_RE.finditer(md):
        if m.start() > last:
            parts.append((False, md[last : m.start()]))
        parts.append((True, m.group(0)))
        last = m.end()
    if last < len(md):
        parts.append((False, md[last:]))

    _SINGLE_LINE_DISPLAY_RE = re.compile(r"(?m)^([ \t]*)\$\$([^\n]*?)\$\$[ \t]*$")

    def _normalize_segment(s: str) -> str:
        if not s:
            return s

        # 1) Common LaTeX bracket delimiters.
        # These are safe to convert because they are unambiguous markers.
        s = s.replace("\\[", "$$").replace("\\]", "$$")
        s = s.replace("\\(", "$").replace("\\)", "$")

        # 2) Normalize single-line $$...$$ into a stable display-math block.
        # IMPORTANT: only touch lines where both delimiters are present on the same line.
        # Avoid regexes that can span across multiple $$ markers; that can corrupt inline $...$.
        def _normalize_single_line_display(m: re.Match) -> str:
            indent = m.group(1) or ""
            inner = (m.group(2) or "").strip()
            if not inner:
                return m.group(0)
            # Preserve indentation so display blocks inside lists stay inside the list.
            # Avoid inserting unindented blank lines; that can terminate lists and corrupt layout.
            return f"{indent}$$\n{indent}{inner}\n{indent}$$"

        s = _SINGLE_LINE_DISPLAY_RE.sub(_normalize_single_line_display, s)

        # 3) Keep output tidy; do not aggressively rewrite inline $...$.
        s = re.sub(r"\n{4,}", "\n\n\n", s)
        return s

    out = "".join(seg if is_code else _normalize_segment(seg) for is_code, seg in parts)
    return out


_GOOGLE_IMG_HOST_RE = re.compile(r"https?://(?:lh3\.)?googleusercontent\.com/", re.IGNORECASE)
_MIME_IMAGE_RE = re.compile(r"\bimage/(?:png|jpe?g|gif|webp|bmp|tiff?)\b", re.IGNORECASE)


def _turn_likely_has_image(turn: Any) -> bool:
    for s in _iter_strings(turn):
        t = (s or "").strip()
        if not t:
            continue
        if _MIME_IMAGE_RE.search(t) is not None:
            return True
        if _GOOGLE_IMG_HOST_RE.search(t) is not None:
            return True
    return False


def _extract_prompt_from_turn(turn: Any) -> str:
    """Best-effort prompt extraction.

    Observed pattern:
      turn[2][0] == ["prompt text", ...]
    """
    if not isinstance(turn, list) or len(turn) < 3:
        return ""

    slot = turn[2]
    if isinstance(slot, list) and slot:
        first = slot[0]
        if isinstance(first, list) and first and all(isinstance(x, str) for x in first):
            prompt = "\n".join([x for x in first if x.strip()]).strip()
            # Some exports represent an image-only prompt as a synthetic filename.
            if re.fullmatch(r"image_[0-9a-fA-F]{4,}\.(?:png|jpe?g|gif|webp|bmp|tiff?)", prompt.strip() or ""):
                return "[图片：导出未包含原图]"
            return prompt
        if all(isinstance(x, str) for x in slot):
            prompt = "\n".join([x for x in slot if x.strip()]).strip()
            if re.fullmatch(r"image_[0-9a-fA-F]{4,}\.(?:png|jpe?g|gif|webp|bmp|tiff?)", prompt.strip() or ""):
                return "[图片：导出未包含原图]"
            return prompt

    # Fallback: first short-ish string list
    for obj in (slot, turn):
        for s in _iter_strings(obj):
            t = s.strip()
            if 1 < len(t) <= 400 and "\n" not in t and not _ID_LIKE_RE.match(t):
                if re.fullmatch(r"image_[0-9a-fA-F]{4,}\.(?:png|jpe?g|gif|webp|bmp|tiff?)", t):
                    return "[图片：导出未包含原图]"
                return t

    # If the prompt text is missing (common when the first user turn is an image-only prompt
    # and the export omits the image payload), preserve a placeholder so chronology and
    # context remain visible.
    if _turn_likely_has_image(turn):
        return "[图片：导出未包含原图]"

    return ""


def _extract_response_and_thinking(turn: Any) -> Tuple[str, Optional[str]]:
    if not isinstance(turn, list) or len(turn) < 4:
        return "", None

    response_slot = turn[3]

    # 1) Prefer structural extraction of the primary response.
    # In observed batchexecute payloads, assistant outputs usually appear under a list like:
    #   ["rc_xxx", ["<markdown text>"], ...]
    # Thinking (when present) may also exist as free-form strings elsewhere in the slot.
    rc_texts: List[str] = []

    def _walk_rc(o: Any) -> None:
        if isinstance(o, list):
            if len(o) >= 2 and isinstance(o[0], str) and o[0].startswith("rc_"):
                payload = o[1]
                if isinstance(payload, list):
                    parts = [p.strip("\r\n ") for p in payload if isinstance(p, str) and p.strip()]
                    if parts:
                        rc_texts.append("\n".join(parts).strip())
            for it in o:
                _walk_rc(it)
        elif isinstance(o, dict):
            for v in o.values():
                _walk_rc(v)

    _walk_rc(response_slot)

    def _looks_like_report(text: str) -> bool:
        t = (text or "").lstrip()
        if len(t) < 4000:
            return False
        if not t.startswith("#"):
            return False
        return ("\n## " in t) or ("\n### " in t)

    def _final_score(text: str) -> int:
        t = (text or "").strip()
        if not t:
            return -10**9
        score = len(t)
        if "\n" in t:
            score += 80
        if "```" in t:
            score += 120
        if "#" in t or "*" in t or "- " in t:
            score += 20

        # Deep Research exports sometimes include short confirmation/link-only blobs.
        # Prefer the actual report body over these.
        tl = t.lower()
        if "googleusercontent.com/deep_research_confirmation_content" in tl:
            score -= 8000
        if "googleusercontent.com/immersive_entry_chip" in tl:
            score -= 8000

        # Strongly down-rank obvious thinking narrations; these are usually not the final answer.
        if _thinking_score(t) >= 60:
            score -= 10000
        return score

    # We will pick the best "final answer" candidate across both structured rc_* payloads
    # and unstructured strings (Deep Research exports sometimes embed the full report outside
    # the rc_* response payload).
    response = ""
    strings_raw = [s for s in _iter_strings(response_slot) if isinstance(s, str)]
    strings = _dedupe_preserve_order([s.strip("\r\n ") for s in strings_raw if s and s.strip()])

    # Prefer separating "thinking" and "final answer".
    thinking_candidates: List[str] = []
    final_candidates: List[str] = []

    for s in strings:
        if _ID_LIKE_RE.match(s) or _BASE64ISH_RE.match(s):
            continue
        if len(s) < 20:
            continue

        # Prefer separating "thinking" and "final answer".

        ts = _thinking_score(s)
        if ts >= 60 and len(s) >= 120:
            thinking_candidates.append(s)
        else:
            final_candidates.append(s)

    rc_pool = [t for t in rc_texts if isinstance(t, str) and t.strip()]

    # Deep Research reports can live outside the rc_* payload. Always prefer a report-like
    # markdown candidate when present.
    report_candidates = [t for t in (rc_pool + final_candidates) if _looks_like_report(t)]
    if report_candidates:
        response = max(report_candidates, key=_final_score).strip()
    elif rc_pool:
        # Some exports embed many auxiliary strings in the response slot (e.g. link preview
        # descriptions). Prefer the structurally-extracted rc_* payload when present.
        response = max(rc_pool, key=_final_score).strip()
    elif final_candidates:
        response = max(final_candidates, key=_final_score).strip()

    thinking = None
    if thinking_candidates:
        # Pick the most "thinking-like"; tie-break by length.
        thinking = max(thinking_candidates, key=lambda x: (_thinking_score(x), len(x)))

    if not response:
        if final_candidates:
            response = _pick_best_text(final_candidates)
        else:
            # Fallback: if we only have thinking, at least render it as content.
            response = _pick_best_text(strings)

    # Don't duplicate: if thinking overlaps the selected response, drop it.
    if thinking and response:
        if thinking == response or thinking in response or response in thinking:
            thinking = None

    return response, thinking


def _extract_turn_timestamp_seconds(turn: Any) -> Optional[float]:
    if not isinstance(turn, list):
        return None

    # Prefer explicit [seconds, nanos] pairs found near the top of the turn structure.
    # Deep Research exports often embed many epoch-like numbers inside the report body;
    # naively taking max() can pick those and break ordering (prompt/report inversion).
    pairs: List[Tuple[int, float, float]] = []
    scalars: List[Tuple[int, float]] = []

    def _walk(o: Any, depth: int) -> None:
        if isinstance(o, bool) or o is None:
            return

        if isinstance(o, (int, float)):
            n = float(o)
            if 1e9 <= n <= 2e13:
                scalars.append((depth, n))
            return

        if isinstance(o, list):
            if (
                len(o) == 2
                and isinstance(o[0], (int, float))
                and isinstance(o[1], (int, float))
                and 1e9 <= float(o[0]) <= 2e10
                and 0.0 <= float(o[1]) < 1e9
            ):
                pairs.append((depth, float(o[0]), float(o[1])))
            for it in o:
                _walk(it, depth + 1)
            return

        if isinstance(o, dict):
            for v in o.values():
                _walk(v, depth + 1)
            return

    _walk(turn, 0)

    if pairs:
        # Pick the shallowest pair; tie-break by larger seconds.
        depth, sec, sub = min(pairs, key=lambda x: (x[0], -x[1], -x[2]))
        return sec + (sub / 1e9)

    if not scalars:
        return None

    # Fallback: shallowest epoch-like scalar; normalize seconds vs ms.
    depth, n = min(scalars, key=lambda x: (x[0], x[1]))
    if n >= 1e12:
        return n / 1000.0
    return n


_URL_RE = re.compile(r"https?://[^\s\"\)<>]+", re.IGNORECASE)


_URL_TRAILING_JUNK_RE = re.compile(r"[\]\)\>\}\.,;:!\?\u3001\u3002`]+$")


def _clean_and_validate_url(url: str) -> Optional[str]:
    u = (url or "").strip()
    if not u:
        return None

    # Strip common markdown/formatting garbage.
    u = u.strip("`")
    u = _URL_TRAILING_JUNK_RE.sub("", u)

    # Some payloads include stray backticks mid-token; discard those.
    if "`" in u:
        return None

    if len(u) > 2048:
        return None

    try:
        p = urlparse(u)
    except Exception:
        return None

    if p.scheme not in {"http", "https"}:
        return None
    if not p.netloc:
        return None
    return u


def _extract_urls(obj: Any) -> List[str]:
    urls: List[str] = []
    seen = set()
    for s in _iter_strings(obj):
        for m in _URL_RE.finditer(s or ""):
            raw = (m.group(0) or "").strip()
            u = _clean_and_validate_url(raw)
            if not u:
                continue

            key = u.lower()
            if key not in seen:
                seen.add(key)
                urls.append(u)
    return urls


_NOISY_SOURCE_URL_RE = re.compile(
    r"(?:^https?://t\d\.gstatic\.com/faviconV2\b|googleusercontent\.com/(?:deep_research_confirmation_content|immersive_entry_chip)/)",
    re.IGNORECASE,
)


def _filter_source_urls(urls: Sequence[str], *, limit: int = 60) -> List[str]:
    out: List[str] = []
    seen = set()
    for u in urls:
        if not u:
            continue
        if _NOISY_SOURCE_URL_RE.search(u) is not None:
            continue
        # Most useful citations are normal web URLs; drop remaining googleusercontent.
        if "googleusercontent.com/" in u.lower():
            continue
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= limit:
            break
    return out


_CITATION_SINGLE_RE = re.compile(r"\[(\d{1,4})\](?!\()")
_CITATION_SINGLE_ZH_RE = re.compile(r"【(\d{1,4})】")

# Match citation groups like: [2, 15, 20] / [152, 153, 154] / [2，15，20]
_CITATION_GROUP_RE = re.compile(
    r"\[(\d{1,4}(?:\s*[-–—]\s*\d{1,4})?(?:\s*[,，;；]\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*)\]"
)


def _parse_citation_group(text: str, *, max_n: int = 5000) -> List[int]:
    raw = (text or "").strip()
    if not raw:
        return []

    out: List[int] = []
    for part in re.split(r"\s*[,，;；]\s*", raw):
        p = (part or "").strip()
        if not p:
            continue
        # Support simple ranges like 141-147 (any dash).
        m = re.fullmatch(r"(\d{1,4})\s*[-–—]\s*(\d{1,4})", p)
        if m:
            a = int(m.group(1))
            b = int(m.group(2))
            if 1 <= a <= max_n and 1 <= b <= max_n:
                lo, hi = (a, b) if a <= b else (b, a)
                # Avoid exploding huge ranges.
                if hi - lo <= 50:
                    out.extend(list(range(lo, hi + 1)))
                else:
                    out.extend([lo, hi])
            continue

        if re.fullmatch(r"\d{1,4}", p):
            n = int(p)
            if 1 <= n <= max_n:
                out.append(n)

    return out


def _extract_citation_numbers(md: str, *, max_n: int = 5000) -> List[int]:
    if not md:
        return []

    nums: List[int] = []

    # 1) Parse groups like [2, 15, 20]
    for m in _CITATION_GROUP_RE.finditer(md):
        nums.extend(_parse_citation_group(m.group(1), max_n=max_n))

    # 2) Also accept standalone markers.
    for m in _CITATION_SINGLE_RE.finditer(md):
        try:
            nums.append(int(m.group(1)))
        except Exception:
            continue
    for m in _CITATION_SINGLE_ZH_RE.finditer(md):
        try:
            nums.append(int(m.group(1)))
        except Exception:
            continue

    return sorted({n for n in nums if 1 <= n <= max_n})


def _expand_citation_groups_for_links(md: str) -> str:
    """Rewrite citation groups like [2, 15, 20] into '[2] [15] [20]'.

    This enables reference-style markdown linking once we append '[n]: url' definitions.
    """

    if not md:
        return md

    def _repl(m: re.Match) -> str:
        nums = _parse_citation_group(m.group(1))
        if not nums:
            return m.group(0)
        return " " + " ".join([f"[{n}]" for n in nums])

    return _CITATION_GROUP_RE.sub(_repl, md)


_CITATION_LINKABLE_RE = re.compile(r"(?<!\[)\[(\d{1,4})\](?!\()")
_CITATION_LINKABLE_ZH_RE = re.compile(r"【(\d{1,4})】")


def _markdown_url_dest(url: str) -> str:
    # Use angle brackets to avoid issues with ')' and other special chars in URLs.
    return f"<{url}>"


def _linkify_citations(md: str, source_urls: Sequence[str]) -> str:
    """Replace standalone citation markers with explicit inline links.

    Produces links like: [[71]](<https://example.com>) so the visible label stays '[71]'.
    Skips fenced code blocks.
    """

    if not md or not source_urls:
        return md

    def _url_for(n: int) -> Optional[str]:
        if 1 <= n <= len(source_urls):
            return source_urls[n - 1]
        return None

    parts: List[Tuple[bool, str]] = []
    last = 0
    for m in _FENCED_CODEBLOCK_RE.finditer(md):
        if m.start() > last:
            parts.append((False, md[last : m.start()]))
        parts.append((True, m.group(0)))
        last = m.end()
    if last < len(md):
        parts.append((False, md[last:]))

    def _linkify_segment(s: str) -> str:
        if not s:
            return s

        def _repl(m: re.Match) -> str:
            try:
                n = int(m.group(1))
            except Exception:
                return m.group(0)
            url = _url_for(n)
            if not url:
                return m.group(0)
            return f"[[{n}]]({_markdown_url_dest(url)})"

        s = _CITATION_LINKABLE_RE.sub(_repl, s)

        def _repl_zh(m: re.Match) -> str:
            try:
                n = int(m.group(1))
            except Exception:
                return m.group(0)
            url = _url_for(n)
            if not url:
                return m.group(0)
            return f"[[{n}]]({_markdown_url_dest(url)})"

        s = _CITATION_LINKABLE_ZH_RE.sub(_repl_zh, s)
        return s

    return "".join(seg if is_code else _linkify_segment(seg) for is_code, seg in parts)


def _text_has_urls(text: str) -> bool:
    if not text:
        return False
    return _URL_RE.search(text) is not None


@dataclass
class GeminiBatchexecuteTurn:
    prompt: str
    response_md: str
    thinking: Optional[str]
    ts: Optional[float]


def _parse_turns(inner: Any) -> List[GeminiBatchexecuteTurn]:
    if not isinstance(inner, list) or not inner:
        return []

    turns_raw = inner[0]
    if not isinstance(turns_raw, list):
        return []

    out: List[GeminiBatchexecuteTurn] = []
    for t in turns_raw:
        if not isinstance(t, list):
            continue
        prompt = _extract_prompt_from_turn(t)
        resp, thinking = _extract_response_and_thinking(t)

        ts = _extract_turn_timestamp_seconds(t)

        if not prompt and not resp and not thinking:
            continue

        out.append(GeminiBatchexecuteTurn(prompt=prompt, response_md=resp, thinking=thinking, ts=ts))

    # Ordering:
    # - Batchexecute exports are commonly reverse-chronological.
    # - Timestamps may be missing or duplicated; only sort when we have informative ts.
    ts_vals = [t.ts for t in out if t.ts is not None]
    distinct_ts = len(set(ts_vals))
    if distinct_ts >= 2:
        out.sort(key=lambda x: (x.ts is None, x.ts or 0.0))
    else:
        # No useful timestamp signal -> fall back to the common batchexecute ordering.
        out.reverse()

    return out


def parse_gemini_batchexecute_conversation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse one gemini_export_*.json file into the API conversation shape."""

    outer = _extract_first_outer_json(_safe_str(data.get("batchexecute_raw")))
    if not outer or not isinstance(outer, list):
        raise ValueError("invalid batchexecute export: missing outer chunk")

    # Outer chunk shape: [["wrb.fr", "hNvQHb", "<json-string>", null, null, ...]]
    inner_str = None
    try:
        if isinstance(outer[0], list) and len(outer[0]) >= 3 and isinstance(outer[0][2], str):
            inner_str = outer[0][2]
    except Exception:
        inner_str = None

    if not inner_str:
        # Some exports only contain a minimal batchexecute envelope without the inner payload
        # (e.g. access denied / fetch failure). Return a stub conversation instead of
        # throwing, so the UI can still render the item.
        def _extract_error_codes(o: Any) -> List[str]:
            codes: List[str] = []

            def _walk(x: Any) -> None:
                if isinstance(x, list):
                    # Pattern like: ["e", 4, null, null, 140]
                    if x and x[0] == "e":
                        for v in x[1:]:
                            if isinstance(v, (int, float)):
                                codes.append(str(int(v)))
                    for it in x:
                        _walk(it)
                elif isinstance(x, dict):
                    for v in x.values():
                        _walk(v)

            _walk(o)
            return _dedupe_preserve_order(codes)

        codes = _extract_error_codes(outer)
        code_str = f" (error codes: {', '.join(codes)})" if codes else ""

        fetched_at = _iso_to_epoch_seconds(_safe_str(data.get("fetched_at")))
        conv_id = _safe_str(data.get("conversation_id"))
        title = _safe_str(data.get("title"))

        meta = {
            "source": "gemini_export",
            "conversation_id": conv_id,
            "fetched_at": fetched_at,
            "model_slug": _safe_str(data.get("model")) or "gemini",
            "create_time": None,
            "update_time": fetched_at,
        }

        messages: List[Dict[str, Any]] = [
            {
                "role": "assistant",
                "ts": fetched_at,
                "content": (
                    "[Gemini 导出解析提示] 该条记录缺少 batchexecute 的 inner payload，可能是导出/抓取失败或访问受限"
                    + code_str
                ),
            }
        ]

        return {"title": title, "messages": messages, "meta": meta}

    try:
        inner = json.loads(inner_str)
    except Exception as e:
        raise ValueError(f"invalid batchexecute inner json: {e}")

    # Deep Research exports often store citation/source URLs in the inner payload rather than
    # embedding them into the final report markdown. Preserve them for the UI by appending
    # a compact link list to the final report when needed.
    # Keep a large pool to support high citation numbers (e.g. [141]). We'll only render
    # what's necessary in the final markdown.
    source_urls = _filter_source_urls(_extract_urls(inner), limit=5000)

    turns = _parse_turns(inner)

    messages: List[Dict[str, Any]] = []
    for t in turns:
        prompt = _normalize_math_delimiters(t.prompt) if t.prompt else ""
        resp_md = _normalize_math_delimiters(t.response_md) if t.response_md else ""
        thinking = _normalize_math_delimiters(t.thinking) if isinstance(t.thinking, str) else None

        if prompt:
            messages.append({"role": "user", "ts": t.ts, "content": prompt})

        if resp_md or thinking:
            msg: Dict[str, Any] = {"role": "assistant", "ts": t.ts, "content": resp_md or ""}
            if thinking:
                msg["thinking"] = [{"title": "思考", "content": thinking}]
            messages.append(msg)

    # Append sources to the final long report (Deep Research).
    # Many exports store citations separately from the final report markdown.
    if source_urls:
        last_assistant_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx is not None:
            content = _safe_str(messages[last_assistant_idx].get("content"))
            content_stripped = content.lstrip()
            looks_like_report = (
                len(content) >= 4000
                and content_stripped.startswith("#")
                and ("\n## " in content or "\n### " in content)
            )

            if looks_like_report and "\n### 引用链接\n" not in content and "\n### Sources\n" not in content:
                # Make grouped citations linkable and turn them into explicit inline links.
                content = _expand_citation_groups_for_links(content)
                content = _linkify_citations(content, source_urls)
                cited = _extract_citation_numbers(content)

                lines: List[str] = []
                if cited:
                    # Render only cited numbers, preserving their numeric meaning.
                    # Citations are assumed 1-based indices into the filtered source list.
                    shown = 0
                    max_lines = 300
                    for n in cited:
                        if shown >= max_lines:
                            lines.append(f"- …（已截断，仅展示前 {max_lines} 个引用编号）")
                            break
                        url = source_urls[n - 1] if 1 <= n <= len(source_urls) else None
                        if url:
                            lines.append(f"- [[{n}]]({_markdown_url_dest(url)}) {url}")
                        else:
                            lines.append(f"- [{n}] （未找到对应链接）")
                        shown += 1
                else:
                    # No explicit citation markers: show a compact numbered list.
                    max_lines = 120
                    for i, u in enumerate(source_urls[:max_lines], start=1):
                        lines.append(f"- [[{i}]]({_markdown_url_dest(u)}) {u}")
                    if len(source_urls) > max_lines:
                        lines.append(f"- …（共 {len(source_urls)} 条，已截断）")

                if lines:
                    block = "\n\n---\n\n### 引用链接\n" + "\n".join(lines)
                    content = content.rstrip() + block + "\n"
                    messages[last_assistant_idx]["content"] = content

    fetched_at = _iso_to_epoch_seconds(_safe_str(data.get("fetched_at")))
    conv_id = _safe_str(data.get("conversation_id"))

    # Optional title (many exports omit it; routes.py will fallback to filename title).
    title = _safe_str(data.get("title"))

    # NOTE: We intentionally do not append a standalone “Sources” message.
    # If links exist, they should already be present in the assistant final answer markdown.

    meta = {
        "source": "gemini_export",
        "conversation_id": conv_id,
        "fetched_at": fetched_at,
        "model_slug": _safe_str(data.get("model")) or "gemini",
        "create_time": None,
        "update_time": fetched_at,
    }

    return {
        "title": title,
        "messages": messages,
        "meta": meta,
    }


def extract_gemini_batchexecute_text(data: Dict[str, Any]) -> str:
    """Lightweight text extraction for search indexing."""

    try:
        conv = parse_gemini_batchexecute_conversation(data)
    except Exception:
        return ""

    parts: List[str] = []
    for m in conv.get("messages") or []:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            parts.append(c.strip())
        th = m.get("thinking")
        if isinstance(th, list):
            for step in th:
                if isinstance(step, dict):
                    cc = step.get("content")
                    if isinstance(cc, str) and cc.strip():
                        parts.append(cc.strip())

    return "\n".join(parts).strip()
