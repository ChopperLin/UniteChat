"""Smoke test for Gemini `gemini_export_*` batchexecute JSON parsing.

This script scans `data/gemini_export_*` and parses a (possibly random) sample of
exports, checking invariants that keep the frontend stable.

Usage:
  D:/UGit/UniteChat/.venv/Scripts/python.exe scripts/smoke_gemini_exports.py
  D:/UGit/UniteChat/.venv/Scripts/python.exe scripts/smoke_gemini_exports.py --limit 200 --seed 123

Exit code:
  0 if all sampled files pass
  1 if any sampled file fails
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Allow `from app...` imports
sys.path.insert(0, "backend")

from app.gemini_batchexecute import is_gemini_batchexecute_export, parse_gemini_batchexecute_conversation


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@dataclass
class Failure:
    path: Path
    reason: str


def _iter_export_files() -> Iterable[Path]:
    if not DATA.exists():
        return
    for d in DATA.iterdir():
        if not d.is_dir():
            continue
        if not d.name.startswith("gemini_export_"):
            continue
        # Exports are generally flat, but rglob is safer.
        yield from d.rglob("*.json")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _thinking_total_chars(msg: Dict[str, Any]) -> int:
    thinking = msg.get("thinking")
    if not isinstance(thinking, list):
        return 0
    total = 0
    for step in thinking:
        if isinstance(step, dict):
            c = step.get("content")
            if isinstance(c, str):
                total += len(c)
    return total


def _check_conversation(conv: Dict[str, Any]) -> Optional[str]:
    messages = conv.get("messages")
    if not isinstance(messages, list) or not messages:
        return "missing messages"

    assistant_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    if not assistant_msgs:
        return "no assistant messages"

    # Invariant 1: no assistant message should have thinking but empty content.
    for i, m in enumerate(assistant_msgs):
        content = m.get("content")
        has_thinking = bool(m.get("thinking") or m.get("thinking_summary") or m.get("thinking_duration"))
        if has_thinking and (not isinstance(content, str) or not content.strip()):
            return f"assistant[{i}] has thinking but empty content"

    # Invariant 2: guard against Deep Research confirmation blob being selected as the main answer.
    biggest = max(assistant_msgs, key=lambda m: len(m.get("content") or "") if isinstance(m.get("content"), str) else 0)
    biggest_content = biggest.get("content") or ""
    if isinstance(biggest_content, str):
        tl = biggest_content.lower()
        if "googleusercontent.com/deep_research_confirmation_content" in tl:
            return "deep research confirmation blob chosen as content"
        if "googleusercontent.com/immersive_entry_chip" in tl and len(biggest_content) < 500:
            return "immersive_entry_chip link chosen as content"

    # Invariant 3: if any thinking is huge but content is tiny, that’s usually a misclassification.
    for i, m in enumerate(assistant_msgs):
        content = m.get("content") or ""
        if not isinstance(content, str):
            continue
        th_chars = _thinking_total_chars(m)
        if th_chars > 5000 and len(content) < 300:
            return f"assistant[{i}] has huge thinking ({th_chars}) but tiny content ({len(content)})"

    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80, help="max number of files to parse (0 = all)")
    ap.add_argument("--seed", type=int, default=20260203, help="random seed for sampling")
    ap.add_argument("--include-non-gemini", action="store_true", help="try parsing all json files, not just batchexecute exports")
    args = ap.parse_args()

    paths = list(_iter_export_files())
    if not paths:
        print("[SKIP] no data/gemini_export_* folders found")
        return 0

    rng = random.Random(args.seed)
    rng.shuffle(paths)

    if args.limit and args.limit > 0:
        paths = paths[: args.limit]

    failures: List[Failure] = []
    parsed = 0
    skipped = 0

    for p in paths:
        data = _load_json(p)
        if not isinstance(data, dict):
            skipped += 1
            continue

        if not args.include_non_gemini and not is_gemini_batchexecute_export(data):
            skipped += 1
            continue

        try:
            conv = parse_gemini_batchexecute_conversation(data)
        except Exception as e:
            failures.append(Failure(path=p, reason=f"parse error: {e}"))
            continue

        parsed += 1
        err = _check_conversation(conv)
        if err:
            failures.append(Failure(path=p, reason=err))

    print(f"parsed={parsed} skipped={skipped} sampled={len(paths)} failures={len(failures)}")

    if failures:
        # Print a small, actionable list.
        for f in failures[:15]:
            rel = f.path.relative_to(ROOT)
            print(f"[FAIL] {rel} :: {f.reason}")
        if len(failures) > 15:
            print(f"... and {len(failures) - 15} more")
        return 1

    print("[OK] all sampled files passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
