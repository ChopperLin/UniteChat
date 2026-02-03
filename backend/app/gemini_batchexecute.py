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


_THINKING_HINT_RE = re.compile(r"\b(thinking|thought)\b|思考|推理|<think>", re.IGNORECASE)


_THINKING_STYLE_RE = re.compile(
    r"\b("
    r"investigating|analyzing|examining|unpacking|pinpointing|tracing|isolating|"
    r"verifying|assessing|understanding|reframing|refining|constructing|formulating|"
    r"diagnosing|evaluating|dissecting|connecting the dots|unveiling|"
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
    has_hint = _THINKING_HINT_RE.search(t) is not None
    has_style = _THINKING_STYLE_RE.search(t) is not None
    has_narration = _THINKING_NARRATION_RE.search(t) is not None

    # Avoid misclassifying structured final answers: only treat as thinking if we see
    # explicit thinking-style signals.
    if not (has_hint or has_style or has_narration):
        return 0

    if has_hint:
        score += 80
    if has_style:
        score += 80
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
            return "\n".join([x for x in first if x.strip()]).strip()
        if all(isinstance(x, str) for x in slot):
            return "\n".join([x for x in slot if x.strip()]).strip()

    # Fallback: first short-ish string list
    for obj in (slot, turn):
        for s in _iter_strings(obj):
            t = s.strip()
            if 1 < len(t) <= 400 and "\n" not in t and not _ID_LIKE_RE.match(t):
                return t

    return ""


def _extract_response_and_thinking(turn: Any) -> Tuple[str, Optional[str]]:
    if not isinstance(turn, list) or len(turn) < 4:
        return "", None

    response_slot = turn[3]
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

        ts = _thinking_score(s)
        if ts >= 60 and len(s) >= 120:
            thinking_candidates.append(s)
        else:
            final_candidates.append(s)

    thinking = None
    if thinking_candidates:
        # Pick the most "thinking-like"; tie-break by length.
        thinking = max(thinking_candidates, key=lambda x: (_thinking_score(x), len(x)))

    response = ""
    if final_candidates:
        response = _pick_best_text(final_candidates)
    else:
        # Fallback: if we only have thinking, at least render it as content.
        response = _pick_best_text(strings)

    return response, thinking


def _extract_turn_timestamp_seconds(turn: Any) -> Optional[float]:
    if not isinstance(turn, list):
        return None

    nums: List[float] = []

    def _walk(o: Any) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            nums.append(float(o))
            return
        if isinstance(o, list):
            for it in o:
                _walk(it)
            return
        if isinstance(o, dict):
            for v in o.values():
                _walk(v)

    _walk(turn)

    # Accept Unix seconds or milliseconds.
    candidates = [n for n in nums if 1e9 <= n <= 2e13]
    if not candidates:
        return None

    # Prefer the smallest plausible timestamp in the structure (often the actual one).
    n = min(candidates)
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

    # Exports appear to be reverse-chronological; use timestamps when present.
    if any(t.ts is not None for t in out):
        out.sort(key=lambda x: (x.ts is None, x.ts or 0.0))

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
        raise ValueError("invalid batchexecute export: missing inner payload")

    try:
        inner = json.loads(inner_str)
    except Exception as e:
        raise ValueError(f"invalid batchexecute inner json: {e}")

    turns = _parse_turns(inner)

    messages: List[Dict[str, Any]] = []
    for t in turns:
        if t.prompt:
            messages.append({"role": "user", "ts": t.ts, "content": t.prompt})

        if t.thinking:
            messages.append({
                "role": "assistant",
                "ts": t.ts,
                "thinking": [{"title": "思考", "content": t.thinking}],
                "content": "",
            })

        if t.response_md:
            messages.append({"role": "assistant", "ts": t.ts, "content": t.response_md})

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
