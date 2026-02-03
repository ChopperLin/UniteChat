import json
from pathlib import Path

import sys

# Allow importing `app.*` from backend/ without requiring installation.
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.gemini_batchexecute import _extract_first_outer_json, _safe_str, _parse_turns


def main() -> None:
    p = ROOT / "data" / "gemini_export_2026-02-02_Piqa" / "鼻孔为何成对而非单个_25d5c13e84.json"
    data = json.loads(p.read_text(encoding="utf-8"))

    outer = _extract_first_outer_json(_safe_str(data.get("batchexecute_raw")))
    inner_str = None
    if isinstance(outer, list) and outer and isinstance(outer[0], list) and len(outer[0]) >= 3:
        inner_str = outer[0][2]
    assert isinstance(inner_str, str)

    inner = json.loads(inner_str)
    print("inner type", type(inner), "len", len(inner) if hasattr(inner, "__len__") else None)
    if isinstance(inner, list) and inner:
        print("inner[0] type", type(inner[0]), "len", len(inner[0]) if isinstance(inner[0], list) else None)

    turns = _parse_turns(inner)
    print("parsed turns", len(turns))

    for i, t in enumerate(turns[:10]):
        print("--- turn", i)
        print("prompt_len", len(t.prompt or ""))
        print("resp_len", len(t.response_md or ""))
        print("thinking_len", len(t.thinking or ""))


if __name__ == "__main__":
    main()
