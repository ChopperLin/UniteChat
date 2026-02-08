"""Persistent chat data-source configuration.

Each configured source points to one export folder and declares how it should be parsed.
This replaces the hardcoded "data/* by folder prefix" behavior with explicit mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import glob
import hashlib
import json
import os
import re
import stat
import shutil
import time
import uuid

from app.external_sources import (
    detect_claude_folder,
    detect_gemini_batchexecute_folder,
    detect_gemini_folder,
)


SUPPORTED_SOURCE_KINDS = {"auto", "chatgpt", "claude", "gemini"}


def _slug(s: str) -> str:
    text = (s or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "source"


def _normalize_kind(v: Any) -> str:
    k = str(v or "").strip().lower()
    return k if k in SUPPORTED_SOURCE_KINDS else "auto"


def _as_bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
    return bool(default)


def _gen_id(seed: str = "") -> str:
    base = _slug(seed)[:24]
    tail = uuid.uuid4().hex[:8]
    return f"{base}-{tail}" if base else f"source-{tail}"


@dataclass(frozen=True)
class DataSource:
    id: str
    name: str
    path: str
    kind: str
    enabled: bool


@dataclass(frozen=True)
class FolderBinding:
    id: str
    name: str
    kind: str
    configured_path: str
    resolved_path: Path


class DataSourceStore:
    """Read/write + validate chat data-source configuration."""

    def __init__(self, config_file: Path, base_dir: Path, legacy_data_root: Path):
        self.config_file = Path(config_file)
        self.base_dir = Path(base_dir).resolve()
        self.legacy_data_root = Path(legacy_data_root).resolve()

    def _resolve_path(self, raw_path: str) -> Path:
        p = Path(str(raw_path or "").strip())
        if not p.is_absolute():
            p = (self.base_dir / p).resolve()
        else:
            p = p.resolve()
        return p

    @staticmethod
    def _is_retryable_delete_error(exc: BaseException) -> bool:
        if isinstance(exc, PermissionError):
            return True
        if not isinstance(exc, OSError):
            return False

        winerr = int(getattr(exc, "winerror", 0) or 0)
        if winerr in {5, 32, 33}:
            return True

        err = int(getattr(exc, "errno", 0) or 0)
        # 13: EACCES, 16: EBUSY, 39: ENOTEMPTY
        return err in {13, 16, 39}

    @staticmethod
    def _rmtree_onerror(func, path, exc_info):
        # Try to remove readonly bit, then retry the same operation.
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
        try:
            func(path)
            return
        except Exception:
            pass
        raise exc_info[1]

    def _delete_dir_with_retry(self, target: Path, timeout_sec: float = 4.0) -> None:
        deadline = time.time() + max(0.2, float(timeout_sec))
        delay = 0.08

        while True:
            try:
                if not target.exists():
                    return
                shutil.rmtree(target, onerror=self._rmtree_onerror)
                return
            except FileNotFoundError:
                return
            except Exception as e:
                if (not self._is_retryable_delete_error(e)) or (time.time() >= deadline):
                    raise
                time.sleep(delay)
                delay = min(delay * 1.6, 0.4)

    @staticmethod
    def _has_json_payload(folder: Path) -> bool:
        """Best-effort check: does this folder look like a ChatGPT-style export root."""
        try:
            stack: List[tuple[Path, int]] = [(folder, 0)]
            max_depth = 2  # root + 2 levels, enough for common ChatGPT category layouts
            while stack:
                current, depth = stack.pop()
                for entry in current.iterdir():
                    if entry.is_file() and entry.suffix.lower() == ".json":
                        return True
                    if entry.is_dir() and depth < max_depth:
                        stack.append((entry, depth + 1))
            return False
        except Exception:
            return False

    @staticmethod
    def _detect_folder_kind(folder: Path) -> Optional[str]:
        try:
            if detect_claude_folder(folder):
                return "claude"
        except Exception:
            pass
        try:
            if detect_gemini_folder(folder):
                return "gemini"
        except Exception:
            pass
        try:
            if detect_gemini_batchexecute_folder(folder):
                return "gemini"
        except Exception:
            pass
        if DataSourceStore._has_json_payload(folder):
            return "chatgpt"
        return None

    def resolve_path(self, raw_path: str) -> Path:
        return self._resolve_path(raw_path)

    @staticmethod
    def _has_glob_magic(raw_path: str) -> bool:
        return glob.has_magic(str(raw_path or "").strip())

    def has_glob_magic(self, raw_path: str) -> bool:
        return self._has_glob_magic(raw_path)

    @staticmethod
    def _binding_id(source_id: str, path: Path) -> str:
        digest = hashlib.sha1(str(path).encode("utf-8", errors="ignore")).hexdigest()[:8]
        return f"{source_id}__{digest}"

    def _expand_source_paths(self, raw_path: str) -> List[Path]:
        path_str = str(raw_path or "").strip()
        if not path_str:
            return []

        if self._has_glob_magic(path_str):
            pattern = path_str
            if not Path(pattern).is_absolute():
                pattern = str(self.base_dir / pattern)
            hits = glob.glob(pattern, recursive=False)
            out: List[Path] = []
            seen: set[str] = set()
            for h in hits:
                p = Path(h).resolve()
                key = str(p)
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
            out.sort(key=lambda p: str(p).lower())
            return out

        return [self._resolve_path(path_str)]

    def expand_source_paths(self, raw_path: str) -> List[Path]:
        return self._expand_source_paths(raw_path)

    def _to_stored_path(self, p: Path) -> str:
        rp = p.resolve()
        try:
            rel = rp.relative_to(self.base_dir)
            return rel.as_posix()
        except Exception:
            return str(rp)

    def _normalize_sources(self, raw_sources: Any) -> List[DataSource]:
        out: List[DataSource] = []
        used_ids: set[str] = set()

        items = raw_sources if isinstance(raw_sources, list) else []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                continue

            source_id = str(item.get("id") or "").strip() or _gen_id(f"source-{idx + 1}")
            while source_id in used_ids:
                source_id = _gen_id(source_id)
            used_ids.add(source_id)

            default_name = Path(raw_path).name or f"Source {idx + 1}"
            name = str(item.get("name") or "").strip() or default_name
            kind = _normalize_kind(item.get("kind"))
            enabled = _as_bool(item.get("enabled"), default=True)

            out.append(
                DataSource(
                    id=source_id,
                    name=name,
                    path=raw_path,
                    kind=kind,
                    enabled=enabled,
                )
            )

        return out

    def _bootstrap_sources(self) -> List[DataSource]:
        sources: List[DataSource] = []
        used_ids: set[str] = set()

        if self.legacy_data_root.exists() and self.legacy_data_root.is_dir():
            legacy_folders = sorted([p for p in self.legacy_data_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
        else:
            legacy_folders = []

        for folder in legacy_folders:
            source_id = _slug(folder.name)
            if not source_id:
                source_id = "source"
            if source_id in used_ids:
                source_id = _gen_id(source_id)
            used_ids.add(source_id)

            sources.append(
                DataSource(
                    id=source_id,
                    name=folder.name,
                    path=self._to_stored_path(folder),
                    kind="auto",
                    enabled=True,
                )
            )

        return sources

    def _read_raw(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {}
        try:
            data = json.loads(self.config_file.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_raw(self, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self.config_file.write_text(payload + "\n", encoding="utf-8")

    def _read_saved_root(self) -> str:
        raw = self._read_raw()
        val = str(raw.get("root") or "").strip() if isinstance(raw, dict) else ""
        if not val:
            return ""
        try:
            return str(self._resolve_path(val))
        except Exception:
            return val

    def _common_parent(self, paths: List[Path]) -> Optional[Path]:
        items = [Path(p).resolve() for p in (paths or [])]
        if not items:
            return None
        try:
            return Path(os.path.commonpath([str(p) for p in items])).resolve()
        except Exception:
            return items[0]

    def get_root_for_api(self) -> str:
        saved = self._read_saved_root()
        if saved:
            return saved

        parents: List[Path] = []
        for src in self.load_sources():
            if self._has_glob_magic(src.path):
                continue
            try:
                p = self._resolve_path(src.path)
            except Exception:
                continue
            if p.exists() and p.is_dir():
                parents.append(p.parent)

        common = self._common_parent(parents)
        if common:
            return str(common)

        fallback = self.legacy_data_root if self.legacy_data_root.exists() else (self.base_dir / "data")
        return str(fallback.resolve())

    def load_sources(self) -> List[DataSource]:
        raw = self._read_raw()
        normalized = self._normalize_sources(raw.get("sources"))
        if normalized:
            return normalized

        boot = self._bootstrap_sources()
        self.save_sources(boot)
        return boot

    def save_sources(self, sources: List[DataSource]) -> List[DataSource]:
        normalized = self._normalize_sources(
            [
                {
                    "id": s.id,
                    "name": s.name,
                    "path": s.path,
                    "kind": s.kind,
                    "enabled": s.enabled,
                }
                for s in (sources or [])
            ]
        )
        payload: Dict[str, Any] = {
            "version": 1,
            "sources": [self.to_api_dict(s, include_exists=False) for s in normalized],
        }
        saved_root = self._read_saved_root()
        if saved_root:
            payload["root"] = saved_root
        self._write_raw(payload)
        return normalized

    def update_from_payload(self, payload_sources: Any) -> List[DataSource]:
        normalized = self._normalize_sources(payload_sources)
        payload: Dict[str, Any] = {
            "version": 1,
            "sources": [self.to_api_dict(s, include_exists=False) for s in normalized],
        }
        saved_root = self._read_saved_root()
        if saved_root:
            payload["root"] = saved_root
        self._write_raw(payload)
        return normalized

    def list_bindings(self) -> List[FolderBinding]:
        bindings: List[FolderBinding] = []
        used_ids: set[str] = set()
        for src in self.load_sources():
            if not src.enabled:
                continue
            candidates = self._expand_source_paths(src.path)
            is_pattern = self._has_glob_magic(src.path)
            for idx, resolved in enumerate(candidates):
                if not (resolved.exists() and resolved.is_dir()):
                    continue
                binding_id = src.id
                binding_name = src.name
                if is_pattern or len(candidates) > 1:
                    binding_id = self._binding_id(src.id, resolved)
                    tail = resolved.name or str(resolved)
                    binding_name = f"{src.name} / {tail}"
                if binding_id in used_ids:
                    binding_id = self._binding_id(f"{src.id}-{idx}", resolved)
                used_ids.add(binding_id)

                bindings.append(
                    FolderBinding(
                        id=binding_id,
                        name=binding_name,
                        kind=src.kind,
                        configured_path=src.path,
                        resolved_path=resolved,
                    )
                )
        bindings.sort(key=lambda b: b.name.lower())
        return bindings

    def to_api_dict(self, src: DataSource, include_exists: bool = True) -> Dict[str, Any]:
        is_pattern = self._has_glob_magic(src.path)
        out: Dict[str, Any] = {
            "id": src.id,
            "name": src.name,
            "path": src.path,
            "kind": src.kind,
            "enabled": bool(src.enabled),
            "is_pattern": is_pattern,
        }
        if include_exists:
            candidates = self._expand_source_paths(src.path)
            existing = [p for p in candidates if p.exists() and p.is_dir()]
            out["exists"] = bool(existing)
            if not is_pattern:
                rp = self._resolve_path(src.path)
                out["resolved_path"] = str(rp)
            elif existing:
                if len(existing) == 1:
                    out["resolved_path"] = str(existing[0])
                else:
                    out["resolved_path"] = f"{len(existing)} matches"
                out["matched_paths"] = [str(p) for p in existing[:30]]
            else:
                out["resolved_path"] = ""
        return out

    def get_sources_for_api(self) -> List[Dict[str, Any]]:
        return [self.to_api_dict(s, include_exists=True) for s in self.load_sources()]

    def get_source(self, source_id: str) -> Optional[DataSource]:
        sid = str(source_id or "").strip()
        if not sid:
            return None
        for src in self.load_sources():
            if src.id == sid:
                return src
        return None

    @staticmethod
    def _validate_folder_name(name: str) -> str:
        n = str(name or "").strip()
        if not n:
            raise ValueError("name is required")
        if any(ch in n for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']):
            raise ValueError("name contains illegal path characters")
        if n in {".", ".."}:
            raise ValueError("invalid folder name")
        return n

    def delete_source(self, source_id: str, delete_dir: bool = False) -> Dict[str, Any]:
        sid = str(source_id or "").strip()
        if not sid:
            raise ValueError("source id is required")

        sources = self.load_sources()
        idx = next((i for i, s in enumerate(sources) if s.id == sid), -1)
        if idx < 0:
            raise FileNotFoundError(f"source not found: {sid}")

        src = sources[idx]
        if delete_dir:
            if self._has_glob_magic(src.path):
                raise ValueError("pattern source cannot be deleted as a single directory")
            target = self._resolve_path(src.path)
            if target.exists() and target.is_dir():
                self._delete_dir_with_retry(target)

        removed = sources.pop(idx)
        saved = self.save_sources(sources)
        return {
            "removed": {
                "id": removed.id,
                "name": removed.name,
                "path": removed.path,
            },
            "sources": saved,
        }

    def rename_source_folder(self, source_id: str, new_name: str) -> Dict[str, Any]:
        sid = str(source_id or "").strip()
        if not sid:
            raise ValueError("source id is required")

        folder_name = self._validate_folder_name(new_name)
        sources = self.load_sources()
        idx = next((i for i, s in enumerate(sources) if s.id == sid), -1)
        if idx < 0:
            raise FileNotFoundError(f"source not found: {sid}")

        src = sources[idx]
        if self._has_glob_magic(src.path):
            raise ValueError("pattern source cannot be renamed as a single directory")

        old_path = self._resolve_path(src.path)
        if not old_path.exists() or not old_path.is_dir():
            raise FileNotFoundError(f"folder not found: {old_path}")

        target = old_path.with_name(folder_name)
        if target.exists() and target != old_path:
            raise FileExistsError(f"target folder already exists: {target}")

        if target != old_path:
            old_path.rename(target)

        sources[idx] = DataSource(
            id=src.id,
            name=folder_name,
            path=self._to_stored_path(target),
            kind=src.kind,
            enabled=src.enabled,
        )
        saved = self.save_sources(sources)
        return {
            "renamed": {
                "id": src.id,
                "old_path": str(old_path),
                "new_path": str(target),
                "name": folder_name,
            },
            "sources": saved,
        }

    def import_from_pattern(self, pattern: str, kind: str = "auto", enabled: bool = True) -> Dict[str, Any]:
        pat = str(pattern or "").strip()
        if not pat:
            return {"matched": 0, "imported": 0, "skipped": 0, "sources": self.load_sources()}

        matched = [p for p in self._expand_source_paths(pat) if p.exists() and p.is_dir()]
        existing = self.load_sources()
        used_ids = {s.id for s in existing}
        existing_paths: set[str] = set()

        for s in existing:
            for rp in self._expand_source_paths(s.path):
                if rp.exists() and rp.is_dir():
                    existing_paths.add(str(rp.resolve()).lower())

        out = list(existing)
        imported = 0
        skipped = 0
        norm_kind = _normalize_kind(kind)
        en = bool(enabled)

        for p in matched:
            rp = p.resolve()
            key = str(rp).lower()
            if key in existing_paths:
                skipped += 1
                continue

            name = rp.name or str(rp)
            source_id = _slug(name) or "source"
            if source_id in used_ids:
                source_id = _gen_id(name)
            while source_id in used_ids:
                source_id = _gen_id(source_id)

            used_ids.add(source_id)
            existing_paths.add(key)
            out.append(
                DataSource(
                    id=source_id,
                    name=name,
                    path=self._to_stored_path(rp),
                    kind=norm_kind,
                    enabled=en,
                )
            )
            imported += 1

        saved = self.save_sources(out)
        return {
            "matched": len(matched),
            "imported": imported,
            "skipped": skipped,
            "sources": saved,
        }

    def import_from_root(self, root: str, enabled: bool = True, include_root: bool = False) -> Dict[str, Any]:
        root_raw = str(root or "").strip()
        if not root_raw:
            return {
                "root": "",
                "scanned": 0,
                "matched": 0,
                "imported": 0,
                "skipped": 0,
                "detected": {"chatgpt": 0, "claude": 0, "gemini": 0},
                "sources": self.load_sources(),
            }

        root_path = self._resolve_path(root_raw)
        if not root_path.exists() or not root_path.is_dir():
            raise FileNotFoundError(f"root folder not found: {root_path}")

        existing = self.load_sources()
        out = list(existing)
        used_ids = {s.id for s in existing}
        existing_paths: set[str] = set()
        for s in existing:
            for rp in self._expand_source_paths(s.path):
                if rp.exists() and rp.is_dir():
                    existing_paths.add(str(rp.resolve()).lower())

        candidates: List[Path] = []
        if include_root:
            candidates.append(root_path)
        for child in sorted([p for p in root_path.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
            candidates.append(child)

        scanned = 0
        matched = 0
        imported = 0
        skipped = 0
        detected = {"chatgpt": 0, "claude": 0, "gemini": 0}
        en = bool(enabled)

        for folder in candidates:
            scanned += 1
            rp = folder.resolve()
            kind = self._detect_folder_kind(rp)
            if kind is None:
                continue

            matched += 1
            detected[kind] = int(detected.get(kind, 0)) + 1
            key = str(rp).lower()
            if key in existing_paths:
                skipped += 1
                continue

            name = rp.name or str(rp)
            source_id = _slug(name) or "source"
            if source_id in used_ids:
                source_id = _gen_id(name)
            while source_id in used_ids:
                source_id = _gen_id(source_id)

            used_ids.add(source_id)
            existing_paths.add(key)
            out.append(
                DataSource(
                    id=source_id,
                    name=name,
                    path=self._to_stored_path(rp),
                    kind=kind,
                    enabled=en,
                )
            )
            imported += 1

        saved = self.save_sources(out)
        try:
            raw = self._read_raw()
            raw["root"] = str(root_path)
            self._write_raw(raw)
        except Exception:
            pass
        return {
            "root": str(root_path),
            "scanned": scanned,
            "matched": matched,
            "imported": imported,
            "skipped": skipped,
            "detected": detected,
            "sources": saved,
        }
