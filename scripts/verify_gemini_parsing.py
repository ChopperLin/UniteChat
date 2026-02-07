"""Quick regression check for Gemini parsing.

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


def _check_skills_youtube_preview_not_selected(path: Path) -> Tuple[bool, str]:
    """Regression: ensure link-preview description isn't chosen as the assistant answer."""

    data = _load_json(path)
    conv = parse_gemini_batchexecute_conversation(data)
    messages = conv.get("messages") or []

    assistants = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    if len(assistants) < 2:
        return False, f"expected >=2 assistant messages, got {len(assistants)}"

    second = assistants[1].get("content") or ""
    if not isinstance(second, str):
        second = ""

    # This string comes from a YouTube link preview description inside the export payload.
    if second.lstrip().startswith("For startup ideas, trends and prompts"):
        return False, "selected YouTube preview description instead of assistant answer"

    # The real answer for this sample includes a recognizable Chinese heading.
    if "项目结构最佳实践" not in second and "沉淀" not in second:
        return False, "second assistant answer does not look like the expected Skills response"

    return True, f"messages={len(messages)} assistant={len(assistants)} second_assistant_len={len(second)}"


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


def _check_math_escape_cleanup(path: Path) -> Tuple[bool, str]:
    """Regression: KaTeX-sensitive escaping should be normalized in math spans."""
    data = _load_json(path)
    conv = parse_gemini_batchexecute_conversation(data)
    messages = conv.get("messages") or []

    blob = "\n\n".join(
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and isinstance(m.get("content"), str)
    )
    if not blob:
        return False, "empty conversation content"

    # Ensure the known problematic formula is normalized (subscripts + greek commands).
    if r"$T_{pixel} = \alpha T_0 + \beta T_1 + \gamma T_2$" not in blob:
        return False, "expected normalized T_pixel formula not found"

    # These over-escaped forms are known to render incorrectly in KaTeX.
    if r"T\_{pixel}" in blob or r"T\_0" in blob or r"\\alpha" in blob:
        return False, "found over-escaped math tokens (e.g. T\\_0 or \\\\alpha)"

    return True, "math escaping normalized for KaTeX"


def main() -> int:
    normal = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "深度学习：21世纪的生物学_e9acfbfd90.json"
    deep = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "贝叶斯公式深度研究报告方案_05473e3116.json"
    skills = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "Skills：AI 的最佳实践结晶_55321ed1f9.json"
    persp = ROOT / "data" / "gemini_export_2026-02-02" / "透视空间重心坐标插值难点_84593318bd.json"

    checks = [
        ("normal_chat", normal, _check_normal_chat),
        ("deep_research", deep, _check_deep_research),
        ("skills_preview", skills, _check_skills_youtube_preview_not_selected),
        ("math_escape_cleanup", persp, _check_math_escape_cleanup),
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
