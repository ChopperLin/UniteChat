"""Persistent per-chat overrides (rename/delete) for container exports like Claude.

We avoid mutating the original export blobs (e.g. Claude's conversations.json).
Instead, we store a small overrides file under the folder root:
  data/<folder>/.unitechat_overrides.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


OVERRIDES_FILENAME = ".unitechat_overrides.json"
SCHEMA_VERSION = 1


@dataclass
class OverridesFile:
    path: Path
    data: Dict[str, Any]


def _default_doc() -> Dict[str, Any]:
    return {"version": SCHEMA_VERSION, "items": {}}


def load_overrides(folder_path: Path) -> OverridesFile:
    path = (Path(folder_path) / OVERRIDES_FILENAME)
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = _default_doc()
        else:
            data = _default_doc()
    except Exception:
        data = _default_doc()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return OverridesFile(path=path, data=data)


def save_overrides(doc: OverridesFile) -> None:
    path = Path(doc.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    raw = json.dumps(doc.data, ensure_ascii=False, indent=2, sort_keys=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(raw)
        f.write("\n")
    os.replace(str(tmp), str(path))


def get_override(folder_path: Path, key: str) -> Optional[Dict[str, Any]]:
    doc = load_overrides(folder_path)
    items = doc.data.get("items") or {}
    v = items.get(key)
    return v if isinstance(v, dict) else None


def set_override(folder_path: Path, key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    doc = load_overrides(folder_path)
    items = doc.data.setdefault("items", {})
    cur = items.get(key)
    if not isinstance(cur, dict):
        cur = {}
    merged = dict(cur)
    merged.update(patch or {})
    items[key] = merged
    save_overrides(doc)
    return merged

