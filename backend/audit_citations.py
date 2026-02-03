"""Audit raw ChatGPT-export JSON files for citation marker coverage.

Goal
- Scan exported conversation JSONs under a directory.
- Find citation markers in message text.
- Verify each marker has a corresponding entry in the same message node's
  metadata.content_references with at least one extractable URL.

This is intentionally independent from backend/app/parser.py so we can
validate whether the data itself is consistently complete.

Usage (PowerShell)
- python backend/audit_citations.py --root data/chatgpt_team_chat_1231
- python backend/audit_citations.py --root data --glob "**/*.json" --top 30 --out backend/audit_report.json

Exit code
- 0: no missing/empty-url citations encountered
- 2: at least one missing/empty-url citation encountered
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


P_START = "\ue200"  # Private-use char used by ChatGPT exports
P_MID = "\ue202"
P_END = "\ue201"

# Other observed variants
BRACKET_CITE_RE = re.compile(r"⸢cite⸣.*?⸣")
CITETURN_RE = re.compile(r"citeturn\d+[a-z]+\d+", re.IGNORECASE)
TURN_TOKEN_RE = re.compile(r"turn\d+[a-z]+\d+", re.IGNORECASE)


@dataclass
class FileStats:
    path: str
    nodes_with_messages: int = 0
    nodes_with_text: int = 0
    nodes_with_cite: int = 0

    cite_marks_total: int = 0
    cite_marks_with_ref: int = 0
    cite_marks_with_urls: int = 0
    cite_marks_missing_ref: int = 0
    cite_marks_ref_no_urls: int = 0

    read_error: Optional[str] = None


@dataclass
class Sample:
    path: str
    node_id: str
    kind: str  # missing_ref | no_urls
    matched_text: str
    extracted_turn_tokens: List[str]


def _safe_join_parts(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    out: List[str] = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            # Sometimes parts contain structured blocks; best-effort stringify
            try:
                out.append(json.dumps(p, ensure_ascii=False, sort_keys=True))
            except Exception:
                out.append(str(p))
        else:
            out.append(str(p))
    return "\n".join(out)


def _extract_private_use_cites(text: str) -> List[str]:
    """Extract full matched_text markers like \ue200cite\ue202...\ue201.

    We avoid complex regex here to be resilient against odd payload contents.
    """
    if not text or P_START not in text:
        return []
    markers: List[str] = []
    i = 0
    needle = f"{P_START}cite{P_MID}"
    while True:
        start = text.find(needle, i)
        if start < 0:
            break
        end = text.find(P_END, start + len(needle))
        if end < 0:
            # Unterminated; stop scanning further to avoid infinite loop
            break
        markers.append(text[start : end + 1])
        i = end + 1
    return markers


def _extract_other_cites(text: str) -> List[str]:
    markers: List[str] = []
    if not text:
        return markers
    markers.extend(m.group(0) for m in BRACKET_CITE_RE.finditer(text))
    markers.extend(m.group(0) for m in CITETURN_RE.finditer(text))
    return markers


def extract_cite_markers(text: str) -> List[str]:
    markers = []
    markers.extend(_extract_private_use_cites(text))
    markers.extend(_extract_other_cites(text))
    return markers


def _iter_nodes(mapping: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if not isinstance(mapping, dict):
        return
    for node_id, node in mapping.items():
        if isinstance(node_id, str) and isinstance(node, dict):
            yield node_id, node


def _extract_urls_from_ref(ref: Any) -> List[str]:
    urls: List[str] = []
    if not isinstance(ref, dict):
        return urls

    def push(val: Any) -> None:
        if isinstance(val, str) and val.strip():
            urls.append(val.strip())
        elif isinstance(val, list):
            for it in val:
                push(it)

    # Common keys
    for k in ("url", "source_url", "href"):
        push(ref.get(k))

    # Some exports keep safe_urls/urls as lists
    for k in ("safe_urls", "urls"):
        push(ref.get(k))

    # Items array
    items = ref.get("items")
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                push(it.get("url"))
                push(it.get("source_url"))
                push(it.get("href"))

    # Dedup while preserving order
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _index_content_references(message: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    md = message.get("metadata")
    if not isinstance(md, dict):
        return {}
    refs = md.get("content_references")
    if not isinstance(refs, list):
        return {}

    idx: Dict[str, List[Dict[str, Any]]] = {}
    for r in refs:
        if not isinstance(r, dict):
            continue
        mt = r.get("matched_text")
        if isinstance(mt, str) and mt:
            idx.setdefault(mt, []).append(r)
    return idx


def audit_file(path: Path, sample_limit_per_file: int = 3) -> Tuple[FileStats, List[Sample]]:
    stats = FileStats(path=str(path))
    samples: List[Sample] = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        stats.read_error = f"{type(e).__name__}: {e}"
        return stats, samples

    mapping = data.get("mapping") if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        # Not a conversation export; ignore gracefully
        return stats, samples

    for node_id, node in _iter_nodes(mapping):
        msg = node.get("message") if isinstance(node, dict) else None
        if not isinstance(msg, dict):
            continue

        stats.nodes_with_messages += 1

        content = msg.get("content")
        parts_text = ""
        if isinstance(content, dict):
            parts_text = _safe_join_parts(content.get("parts"))

        if parts_text:
            stats.nodes_with_text += 1

        cite_marks = extract_cite_markers(parts_text)
        if not cite_marks:
            continue

        stats.nodes_with_cite += 1
        stats.cite_marks_total += len(cite_marks)

        ref_index = _index_content_references(msg)

        for mt in cite_marks:
            refs_for_mt = ref_index.get(mt)
            if not refs_for_mt:
                stats.cite_marks_missing_ref += 1
                if len([s for s in samples if s.kind == "missing_ref"]) < sample_limit_per_file:
                    samples.append(
                        Sample(
                            path=str(path),
                            node_id=node_id,
                            kind="missing_ref",
                            matched_text=mt,
                            extracted_turn_tokens=TURN_TOKEN_RE.findall(mt),
                        )
                    )
                continue

            stats.cite_marks_with_ref += 1
            urls: List[str] = []
            for r in refs_for_mt:
                urls.extend(_extract_urls_from_ref(r))

            # Dedup
            dedup = []
            seen = set()
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    dedup.append(u)
            urls = dedup

            if urls:
                stats.cite_marks_with_urls += 1
            else:
                stats.cite_marks_ref_no_urls += 1
                if len([s for s in samples if s.kind == "no_urls"]) < sample_limit_per_file:
                    samples.append(
                        Sample(
                            path=str(path),
                            node_id=node_id,
                            kind="no_urls",
                            matched_text=mt,
                            extracted_turn_tokens=TURN_TOKEN_RE.findall(mt),
                        )
                    )

    return stats, samples


def _gather_files(root: Path, glob_pat: str) -> List[Path]:
    # Path.rglob doesn't accept "**/*.json" reliably when root is file; normalize
    if root.is_file():
        return [root]
    return sorted(root.glob(glob_pat))


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/chatgpt_team_chat_1231", help="Root directory (or a single .json file)")
    ap.add_argument("--glob", default="**/*.json", help="Glob pattern under root")
    ap.add_argument("--top", type=int, default=20, help="Show top N worst files")
    ap.add_argument("--samples", type=int, default=3, help="Samples per file (for missing/no_urls)")
    ap.add_argument("--out", default="", help="Write full report JSON to this path")
    ap.add_argument("--max-files", type=int, default=0, help="Limit number of files (0=all)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    files = _gather_files(root, args.glob)
    if args.max_files and args.max_files > 0:
        files = files[: args.max_files]

    all_stats: List[FileStats] = []
    all_samples: List[Sample] = []

    for i, p in enumerate(files, 1):
        st, sm = audit_file(p, sample_limit_per_file=args.samples)
        all_stats.append(st)
        all_samples.extend(sm)
        if i % 200 == 0:
            print(f"...scanned {i}/{len(files)} files")

    # Aggregate
    total = FileStats(path="<TOTAL>")
    total.nodes_with_messages = sum(s.nodes_with_messages for s in all_stats)
    total.nodes_with_text = sum(s.nodes_with_text for s in all_stats)
    total.nodes_with_cite = sum(s.nodes_with_cite for s in all_stats)
    total.cite_marks_total = sum(s.cite_marks_total for s in all_stats)
    total.cite_marks_with_ref = sum(s.cite_marks_with_ref for s in all_stats)
    total.cite_marks_with_urls = sum(s.cite_marks_with_urls for s in all_stats)
    total.cite_marks_missing_ref = sum(s.cite_marks_missing_ref for s in all_stats)
    total.cite_marks_ref_no_urls = sum(s.cite_marks_ref_no_urls for s in all_stats)

    offenders = [s for s in all_stats if (s.cite_marks_missing_ref or s.cite_marks_ref_no_urls or s.read_error)]
    offenders.sort(key=lambda s: (s.read_error is None, -(s.cite_marks_missing_ref + s.cite_marks_ref_no_urls), -s.cite_marks_total))

    print("\n=== Citation audit summary ===")
    print(f"Scanned files: {len(files)}")
    print(f"Nodes w/ messages: {total.nodes_with_messages}")
    print(f"Nodes w/ text: {total.nodes_with_text}")
    print(f"Nodes w/ cite: {total.nodes_with_cite}")
    print(f"Cite marks total: {total.cite_marks_total}")
    print(f"Cite marks with matched ref: {total.cite_marks_with_ref}")
    print(f"Cite marks with URL(s): {total.cite_marks_with_urls}")
    print(f"Cite marks missing ref: {total.cite_marks_missing_ref}")
    print(f"Cite marks ref but no urls: {total.cite_marks_ref_no_urls}")

    if total.cite_marks_total:
        ok_rate = total.cite_marks_with_urls / total.cite_marks_total
        print(f"URL coverage rate: {ok_rate:.2%}")

    if offenders:
        print("\n=== Top offenders ===")
        for s in offenders[: args.top]:
            if s.read_error:
                print(f"READ_ERROR  {s.path}  {s.read_error}")
            else:
                bad = s.cite_marks_missing_ref + s.cite_marks_ref_no_urls
                print(
                    f"BAD={bad:5d}  missing_ref={s.cite_marks_missing_ref:5d}  no_urls={s.cite_marks_ref_no_urls:5d}  total_cite={s.cite_marks_total:5d}  {s.path}"
                )

    # Optional report output
    if args.out:
        out_path = Path(args.out)
        report = {
            "summary": asdict(total),
            "files": [asdict(s) for s in all_stats],
            "samples": [asdict(s) for s in all_samples],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote report: {out_path}")

    has_fail = (total.cite_marks_missing_ref + total.cite_marks_ref_no_urls) > 0
    return 2 if has_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
