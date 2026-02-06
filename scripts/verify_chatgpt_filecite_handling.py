from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_text(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return "\n".join(_collect_text(v) for v in obj.values())
    if isinstance(obj, list):
        return "\n".join(_collect_text(v) for v in obj)
    return str(obj)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify ChatGPT filecite markers are handled by the parser.")
    ap.add_argument(
        "--path",
        default=r"data\chatgpt_backup_2026-02-05\Game Dev\STBN原理与优势分析_5686ac48801b.json",
        help="Path to a ChatGPT per-conversation export JSON.",
    )
    args = ap.parse_args()

    root = _repo_root()
    json_path = (root / args.path).resolve()
    if not json_path.exists():
        print(f"[FAIL] JSON not found: {json_path}", file=sys.stderr)
        return 2

    # Make backend/app importable (package name: app)
    sys.path.insert(0, str(root / "backend"))
    from app.parser import ConversationParser  # noqa: E402

    raw = _load_json(json_path)
    conv = ConversationParser().parse_conversation(raw)
    text = _collect_text(conv)

    bad = ["\ue200filecite\ue202", "filecite"]
    if any(m in text for m in bad):
        print("[FAIL] filecite marker leaked into parsed output.", file=sys.stderr)
        return 2

    if re.search(r"[【\[]\s*\d{1,4}\s*:\s*\d{1,4}\s*[†+]", text):
        print("[FAIL] deep message-index citations leaked into parsed output.", file=sys.stderr)
        return 2

    if "citepayload:" not in text:
        print("[FAIL] Expected citation payloads in output (no pills rendered).", file=sys.stderr)
        return 2

    print("[OK] No filecite markers leaked; citation pills present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
