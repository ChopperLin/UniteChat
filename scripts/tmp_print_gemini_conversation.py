"""Debug: print parsed Gemini conversation messages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.gemini_batchexecute import parse_gemini_batchexecute_conversation


def main() -> None:
    rel = sys.argv[1] if len(sys.argv) > 1 else "data/gemini_export_2026-02-02_Piqa/Skills：AI 的最佳实践结晶_55321ed1f9.json"
    p = (ROOT / rel).resolve()
    data = json.loads(p.read_text(encoding="utf-8"))
    conv = parse_gemini_batchexecute_conversation(data)

    print("title:", conv.get("title"))
    msgs = conv.get("messages") or []
    print("messages:", len(msgs))

    for i, m in enumerate(msgs):
        role = m.get("role")
        ts = m.get("ts")
        content = m.get("content")
        if not isinstance(content, str):
            content = ""
        print(f"\n--- {i} {role} ts={ts} len={len(content)}")
        preview = content[:500].replace("\n", "\\n")
        print(preview)


if __name__ == "__main__":
    main()
