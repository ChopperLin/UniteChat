"""Quick regression check for Gemini export parsing.

Runs a couple of known-good samples (normal chat + Deep Research) through the
batchexecute parser and asserts a few invariants that the frontend depends on.

Usage:
  D:/UGit/UniteChat/.venv/Scripts/python.exe scripts/verify_gemini_parsing.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Allow `from app...` imports
sys.path.insert(0, "backend")

from app.gemini_batchexecute import parse_gemini_batchexecute_conversation


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AssistantStats:
    idx: int
    content_len: int
    has_thinking: bool


def _assistant_stats(messages: List[Dict[str, Any]]) -> List[AssistantStats]:
    out: List[AssistantStats] = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content = m.get("content") or ""
        thinking = m.get("thinking")
        out.append(
            AssistantStats(
                idx=i,
                content_len=len(content) if isinstance(content, str) else 0,
                has_thinking=bool(thinking),
            )
        )
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_normal_chat(path: Path) -> Tuple[bool, str]:
    data = _load_json(path)
    conv = parse_gemini_batchexecute_conversation(data)
    messages = conv.get("messages") or []
    a = _assistant_stats(messages)

    if not a:
        return False, "no assistant messages"

    # Expect at least one substantial assistant answer.
    if max(s.content_len for s in a) < 400:
        return False, f"assistant max content too small: {max(s.content_len for s in a)}"

    # Frontend expects content to carry the main answer (thinking is optional).
    empty_content_with_thinking = [s for s in a if s.content_len == 0 and s.has_thinking]
    if empty_content_with_thinking:
        return False, f"assistant messages with thinking but empty content: {[s.idx for s in empty_content_with_thinking]}"

    return True, f"messages={len(messages)} assistant={len(a)} max_assistant_content={max(s.content_len for s in a)}"


def _check_deep_research(path: Path) -> Tuple[bool, str]:
    data = _load_json(path)
    conv = parse_gemini_batchexecute_conversation(data)
    messages = conv.get("messages") or []
    a = _assistant_stats(messages)

    if not a:
        return False, "no assistant messages"

    # Expect a large markdown report in content.
    biggest = max(a, key=lambda s: s.content_len)
    if biggest.content_len < 5000:
        return False, f"deep research report too small: content_len={biggest.content_len}"

    big_content = (messages[biggest.idx].get("content") or "")
    if isinstance(big_content, str) and not (big_content.lstrip().startswith("#") or "\n##" in big_content):
        # Allow non-# markdown, but require some structure.
        return False, "deep research biggest content does not look like a markdown report"

    # Ensure we didn't accidentally choose the confirmation link blob as the final answer.
    if isinstance(big_content, str) and "googleusercontent.com/deep_research_confirmation_content" in big_content.lower():
        return False, "deep research content is still the confirmation blob"

    return True, f"messages={len(messages)} assistant={len(a)} biggest_assistant_idx={biggest.idx} biggest_content_len={biggest.content_len}"


def main() -> int:
    normal = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "深度学习：21世纪的生物学_e9acfbfd90.json"
    deep = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "贝叶斯公式深度研究报告方案_05473e3116.json"

    checks = [
        ("normal_chat", normal, _check_normal_chat),
        ("deep_research", deep, _check_deep_research),
    ]

    ok_all = True
    for name, path, fn in checks:
        if not path.exists():
            print(f"[SKIP] {name}: missing sample: {path}")
            continue
        ok, msg = fn(path)
        ok_all = ok_all and ok
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {path.name} :: {msg}")

    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
