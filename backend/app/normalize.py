"""Normalize multiple chat export formats into the API shape used by the frontend.

Frontend expects:
{
  "title": str,
  "messages": [{"role": "user"|"assistant", "content": str, "ts": float? , ...}],
  "meta": {...}
}

ChatGPT export already matches via ConversationParser.
This module adds normalization for:
- Claude (conversations.json)
- Gemini Takeout activity (MyActivity.html)
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.parse import urlparse

from app.external_sources import GeminiConversationRecord, _iso_to_epoch_seconds


def _safe_epoch(ts: Optional[float]) -> Optional[float]:
    try:
        if ts is None:
            return None
        v = float(ts)
        return v if v > 0 else None
    except Exception:
        return None


def _build_file_url(folder: str, relpath: str) -> str:
    folder_q = quote(str(folder or ""))
    path_q = quote(str(relpath or ""))
    return f"/api/file?folder={folder_q}&path={path_q}"


def normalize_claude_conversation(
    conv_raw: Dict[str, Any],
    project_raw: Optional[Dict[str, Any]] = None,
    project_memory: str = "",
) -> Dict[str, Any]:
    """Normalize one Claude conversation object (from conversations.json).

    If project info is provided, project settings are injected as the first assistant message
    so users can always see them within the project (without needing pseudo-chats).
    """
    title = str(conv_raw.get("name") or conv_raw.get("title") or "Untitled").strip() or "Untitled"

    created_at = _iso_to_epoch_seconds(conv_raw.get("created_at"))
    updated_at = _iso_to_epoch_seconds(conv_raw.get("updated_at"))

    messages_out: List[Dict[str, Any]] = []

    # Claude deep-research often produces the main report as an "artifact" via tool_use.
    # The export may not embed the final report as a normal assistant text message.
    artifacts: Dict[str, Dict[str, Any]] = {}

    def _encode_cite_payload(refs: List[Dict[str, Any]]) -> str:
        raw = json.dumps({"refs": refs}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _domain_label(url: str) -> str:
        try:
            host = (urlparse(url).hostname or "").strip().lower()
        except Exception:
            host = ""
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return "ref"
        parts = [p for p in host.split(".") if p]
        if len(parts) >= 2:
            return parts[-2]
        return host

    def _normalize_web_search_result_item(item: Any) -> Optional[Dict[str, str]]:
        if not isinstance(item, dict):
            return None

        url = item.get("url")
        if not (isinstance(url, str) and url.strip()):
            return None
        url = url.strip()

        title = item.get("title")
        if not (isinstance(title, str) and title.strip()):
            title = url
        else:
            title = title.strip()

        host = _domain_label(url)
        return {"url": url, "title": title, "host": host}

    def _materialize_text_citations(md: str, citations: Any) -> str:
        """Insert Claude-export citations into markdown as clickable citation pills.

        Claudes store web citations separately from the text block, typically under:
          content[i].citations[j] = {start_index, end_index, details:{url,...}}
        Without materialization, the frontend has no way to display them.
        """
        if not (isinstance(md, str) and md.strip()):
            return md or ""
        if not isinstance(citations, list) or not citations:
            return md

        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for c in citations:
            if not isinstance(c, dict):
                continue
            si = c.get("start_index")
            ei = c.get("end_index")
            if not isinstance(si, int) or not isinstance(ei, int):
                continue
            if si < 0 or ei < 0 or si > ei or ei > len(md):
                continue

            url = c.get("url")
            if not (isinstance(url, str) and url.strip()):
                det = c.get("details")
                if isinstance(det, dict):
                    url = det.get("url")
            if not (isinstance(url, str) and url.strip()):
                continue
            url = url.strip()

            title = ""
            det = c.get("details")
            if isinstance(det, dict):
                t2 = det.get("title") or det.get("source") or det.get("domain")
                if isinstance(t2, str) and t2.strip():
                    title = t2.strip()

            host = _domain_label(url)
            groups.setdefault((si, ei), []).append({"url": url, "title": title or url, "host": host})

        if not groups:
            return md

        insertions: List[tuple[int, str]] = []
        for (si, ei), refs0 in groups.items():
            refs: List[Dict[str, Any]] = []
            used: set[str] = set()
            for r in refs0:
                u = r.get("url")
                if not (isinstance(u, str) and u.strip()):
                    continue
                u = u.strip()
                if u in used:
                    continue
                used.add(u)
                refs.append({
                    "url": u,
                    "title": str(r.get("title") or u),
                    "host": str(r.get("host") or _domain_label(u) or "ref"),
                })

            if not refs:
                continue

            label_base = str(refs[0].get("host") or "ref")
            label = label_base if len(refs) == 1 else f"{label_base} +{len(refs) - 1}"
            payload = _encode_cite_payload(refs)

            href = refs[0]["url"]
            insertions.append((ei, f" [{label}](<{href}> \"citepayload:{payload}\")"))

        if not insertions:
            return md

        out = md
        for pos, ins in sorted(insertions, key=lambda t: t[0], reverse=True):
            out = out[:pos] + ins + out[pos:]
        return out

    def _materialize_artifact_citations(md: str, md_citations: Any) -> str:
        if not (isinstance(md, str) and md.strip()):
            return md or ""
        if not isinstance(md_citations, list) or not md_citations:
            return md

        # Group citations by the span they annotate.
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for c in md_citations:
            if not isinstance(c, dict):
                continue
            si = c.get("start_index")
            ei = c.get("end_index")
            if not isinstance(si, int) or not isinstance(ei, int):
                continue
            if si < 0 or ei < 0 or si > ei or ei > len(md):
                continue
            groups.setdefault((si, ei), []).append(c)

        if not groups:
            return md

        # Number citations in reading order, but insert from the back to keep indices stable.
        ordered_groups = sorted(groups.keys(), key=lambda t: (t[1], t[0]))
        label_by_group = {g: i + 1 for i, g in enumerate(ordered_groups)}

        insertions: List[tuple[int, str]] = []
        for (si, ei) in sorted(ordered_groups, key=lambda t: t[1], reverse=True):
            citations = groups[(si, ei)]
            refs: List[Dict[str, Any]] = []
            used_urls: set[str] = set()
            for c in citations:
                url = c.get("url")
                if not (isinstance(url, str) and url.strip()):
                    continue
                url = url.strip()
                if url in used_urls:
                    continue
                used_urls.add(url)
                host = ""
                try:
                    host = (urlparse(url).netloc or "").strip()
                except Exception:
                    host = ""
                title = c.get("title")
                refs.append({
                    "url": url,
                    "title": title.strip() if isinstance(title, str) and title.strip() else url,
                    "host": host,
                })

            if not refs:
                continue

            payload = _encode_cite_payload(refs)
            n = label_by_group[(si, ei)]
            # Use title-based payload transport; some markdown sanitizers strip unknown URL schemes.
            insertions.append((ei, f" [[{n}]](# \"citepayload:{payload}\")"))

        if insertions:
            out = md
            for pos, ins in sorted(insertions, key=lambda t: t[0], reverse=True):
                out = out[:pos] + ins + out[pos:]
            return out

        # Fallback: append a references section if we couldn't safely place inline markers.
        refs_md: List[str] = []
        used: set[str] = set()
        for (si, ei), citations in sorted(groups.items(), key=lambda kv: kv[0][0]):
            for c in citations:
                url = c.get("url")
                if not (isinstance(url, str) and url.strip()):
                    continue
                url = url.strip()
                if url in used:
                    continue
                used.add(url)
                title = c.get("title")
                label = title.strip() if isinstance(title, str) and title.strip() else url
                refs_md.append(f"- [{label}]({url})")
        if not refs_md:
            return md
        return (md.rstrip() + "\n\n---\n\n**References**\n\n" + "\n".join(refs_md)).strip()

    def _apply_artifact_edit(content: str, md_citations: Any, old: str, new: str) -> tuple[str, Any]:
        if not (isinstance(content, str) and content and isinstance(old, str) and isinstance(new, str) and old):
            return content, md_citations
        pos = content.find(old)
        if pos < 0:
            return content, md_citations

        before_len = len(old)
        after_len = len(new)
        delta = after_len - before_len

        updated = content[:pos] + new + content[pos + before_len :]

        # Best-effort: keep md_citations indices aligned with the edited content.
        if isinstance(md_citations, list) and md_citations and delta != 0:
            boundary = pos + before_len
            for c in md_citations:
                if not isinstance(c, dict):
                    continue
                si = c.get("start_index")
                ei = c.get("end_index")
                if not isinstance(si, int) or not isinstance(ei, int):
                    continue
                if si >= boundary:
                    c["start_index"] = si + delta
                    c["end_index"] = ei + delta
                elif ei >= boundary:
                    # Overlap with replaced region: shift end only.
                    c["end_index"] = ei + delta

        return updated, md_citations

    chat_messages = conv_raw.get("chat_messages")
    if isinstance(chat_messages, list):
        for msg in chat_messages:
            if not isinstance(msg, dict):
                continue
            sender = (msg.get("sender") or "").strip().lower()
            role = "user" if sender in {"human", "user"} else "assistant"
            msg_ts = _safe_epoch(_iso_to_epoch_seconds(msg.get("created_at")) or _iso_to_epoch_seconds(msg.get("updated_at")))

            # Claudes often include a simplified msg.text plus a richer msg.content list.
            text_fallback = msg.get("text") if isinstance(msg.get("text"), str) else ""

            def _find_string_payload(obj: Any) -> str:
                if isinstance(obj, str):
                    return obj
                if isinstance(obj, dict):
                    # Prefer common payload keys.
                    for k in ("content", "text", "output", "result", "markdown", "md", "thinking"):
                        v = obj.get(k)
                        if isinstance(v, str) and v.strip():
                            return v
                    # Some tool payloads store text under input.*
                    v = obj.get("input")
                    if isinstance(v, dict):
                        for k in ("content", "text", "md", "markdown"):
                            vv = v.get(k)
                            if isinstance(vv, str) and vv.strip():
                                return vv
                    return ""
                return ""

            def _new_segment(mode: str) -> Dict[str, Any]:
                return {
                    "mode": mode,  # "text" | "reasoning"
                    "content_parts": [],
                    "thinking_steps": [],
                    "thinking_summaries": [],
                    "web_searches": [],
                }

            local_segments: List[Dict[str, Any]] = []
            current_segment: Optional[Dict[str, Any]] = None
            pending_web_search_queries: List[str] = []
            tool_fallback: List[str] = []

            def _flush_segment() -> None:
                nonlocal current_segment
                if current_segment is None:
                    return

                content_text = "\n".join([str(x) for x in current_segment.get("content_parts", []) if isinstance(x, str)]).strip()
                thinking_steps = current_segment.get("thinking_steps") or []
                thinking_summaries = current_segment.get("thinking_summaries") or []
                web_searches = current_segment.get("web_searches") or []

                if not content_text and not thinking_steps and not web_searches:
                    current_segment = None
                    return

                out_msg: Dict[str, Any] = {
                    "role": role,
                    "ts": msg_ts,
                    "content": content_text,
                    "_segment_mode": str(current_segment.get("mode") or ""),
                }
                if thinking_steps:
                    out_msg["thinking"] = thinking_steps
                if thinking_summaries:
                    out_msg["thinking_summary"] = "\n".join(thinking_summaries)
                if web_searches:
                    out_msg["web_searches"] = web_searches

                local_segments.append(out_msg)
                current_segment = None

            def _ensure_segment(mode: str) -> Dict[str, Any]:
                nonlocal current_segment
                if current_segment is None:
                    current_segment = _new_segment(mode)
                elif current_segment.get("mode") != mode:
                    _flush_segment()
                    current_segment = _new_segment(mode)
                return current_segment

            content_list = msg.get("content")
            if isinstance(content_list, list):
                for part in content_list:
                    if not isinstance(part, dict):
                        continue

                    p_type = (part.get("type") or "").strip().lower()
                    if p_type == "thinking":
                        t = part.get("thinking")
                        if not (isinstance(t, str) and t.strip()):
                            t = part.get("text")
                        if isinstance(t, str) and t.strip():
                            seg = _ensure_segment("reasoning")
                            seg["thinking_steps"].append({
                                "title": "思考",
                                "content": t.strip(),
                            })

                        sums = part.get("summaries")
                        if isinstance(sums, list):
                            collected: List[str] = []
                            for s in sums:
                                if isinstance(s, dict) and isinstance(s.get("summary"), str) and s.get("summary").strip():
                                    collected.append(s.get("summary").strip())
                            if collected:
                                seg = _ensure_segment("reasoning")
                                seg["thinking_summaries"].extend(collected)
                        continue

                    if p_type == "text":
                        t = part.get("text")
                        if isinstance(t, str) and t.strip():
                            seg = _ensure_segment("text")
                            seg["content_parts"].append(_materialize_text_citations(t, part.get("citations")))
                        continue

                    if p_type in {"tool_result", "tool_use"}:
                        tool_name = str(part.get("name") or "").strip().lower()

                        # Capture Claude "Search the web" activity and keep original interleaving.
                        if p_type == "tool_use" and tool_name == "web_search":
                            query = ""
                            inp = part.get("input")
                            if isinstance(inp, dict):
                                q = inp.get("query")
                                if isinstance(q, str) and q.strip():
                                    query = q.strip()
                            pending_web_search_queries.append(query)

                        if p_type == "tool_result" and tool_name == "web_search":
                            query = pending_web_search_queries.pop(0) if pending_web_search_queries else ""
                            raw_results = part.get("content")
                            result_count = len(raw_results) if isinstance(raw_results, list) else 0
                            normalized_results: List[Dict[str, str]] = []
                            used_urls: set[str] = set()
                            if isinstance(raw_results, list):
                                for r in raw_results:
                                    rec = _normalize_web_search_result_item(r)
                                    if not rec:
                                        continue
                                    u = rec["url"]
                                    if u in used_urls:
                                        continue
                                    used_urls.add(u)
                                    normalized_results.append(rec)
                                    if len(normalized_results) >= 12:
                                        break
                            seg = _ensure_segment("reasoning")
                            seg["web_searches"].append({
                                "query": query or "Web search",
                                "result_count": result_count,
                                "results": normalized_results,
                                "status": "done",
                            })

                        # Special-case: artifacts tool captures deep-research reports.
                        if p_type == "tool_use" and (part.get("name") == "artifacts"):
                            inp = part.get("input")
                            if isinstance(inp, dict):
                                art_id = str(inp.get("id") or "").strip()
                                if art_id:
                                    rec = artifacts.get(art_id)
                                    if rec is None:
                                        rec = {
                                            "id": art_id,
                                            "title": str(inp.get("title") or "").strip(),
                                            "content": "",
                                            "md_citations": None,
                                        }
                                        artifacts[art_id] = rec

                                    # Create/update
                                    c = inp.get("content")
                                    if isinstance(c, str) and c.strip():
                                        rec["content"] = c
                                        if not rec.get("title"):
                                            rec["title"] = str(inp.get("title") or "").strip()
                                        if isinstance(inp.get("md_citations"), list):
                                            rec["md_citations"] = inp.get("md_citations")

                                    # Edits: replace old_str with new_str (first occurrence)
                                    old = inp.get("old_str")
                                    new = inp.get("new_str")
                                    if isinstance(old, str) and isinstance(new, str) and old and rec.get("content"):
                                        updated, cites = _apply_artifact_edit(str(rec.get("content") or ""), rec.get("md_citations"), old, new)
                                        rec["content"] = updated
                                        rec["md_citations"] = cites

                        # Generic tool payload fallback (only used when message has no visible text/reasoning).
                        payload = _find_string_payload(part)
                        if isinstance(payload, str) and payload.strip():
                            tool_fallback.append(payload.strip())
                        continue

                if pending_web_search_queries:
                    seg = _ensure_segment("reasoning")
                    for q in pending_web_search_queries:
                        seg["web_searches"].append({
                            "query": q or "Web search",
                            "result_count": 0,
                            "results": [],
                            "status": "searching",
                        })

            _flush_segment()

            # Fallback to simplified text when we failed to materialize any visible segment.
            if not local_segments:
                content_text = text_fallback.strip()
                if (not content_text) and tool_fallback:
                    content_text = "\n\n".join(tool_fallback).strip()
                if content_text:
                    local_segments.append({
                        "role": role,
                        "ts": msg_ts,
                        "content": content_text,
                        "_segment_mode": "text",
                    })

            # Copy policy: user prompt is copyable; assistant only copy the primary text segment.
            if role == "user":
                for seg in local_segments:
                    seg["allow_copy"] = True
            else:
                for seg in local_segments:
                    seg["allow_copy"] = False
                text_segment_indices: List[int] = []
                for i, seg in enumerate(local_segments):
                    c = seg.get("content")
                    if isinstance(c, str) and c.strip():
                        text_segment_indices.append(i)
                if text_segment_indices:
                    local_segments[text_segment_indices[-1]]["allow_copy"] = True

            # Internal helper field for normalization logic; do not expose to API.
            for seg in local_segments:
                if isinstance(seg, dict):
                    seg.pop("_segment_mode", None)

            messages_out.extend(local_segments)

    # Append final artifact(s) (deep research report) as assistant messages.
    # We append at the end to keep ordering simple and avoid interleaving tool messages.
    for art in artifacts.values():
        content = str(art.get("content") or "").strip()
        if not content:
            continue
        content = _materialize_artifact_citations(content, art.get("md_citations"))
        title = str(art.get("title") or "").strip()
        header = f"**Deep Research Report**\n\n" + (f"_{title}_\n\n" if title else "")
        messages_out.append({
            "role": "assistant",
            "ts": _safe_epoch(updated_at or created_at),
            "content": (header + content).strip(),
            "allow_copy": True,
        })

    meta = {
        "source": "claude",
        # Claude doesn't reliably include model per conversation.
        "model_slug": (
            (conv_raw.get("model") or conv_raw.get("model_slug") or "").strip()
            if isinstance(conv_raw.get("model") or conv_raw.get("model_slug"), str)
            else ""
        ) or "Claude",
        "create_time": _safe_epoch(created_at),
        "update_time": _safe_epoch(updated_at),
    }

    return {
        "title": title,
        "messages": messages_out,
        "meta": meta,
    }


def normalize_claude_project(project_raw: Dict[str, Any], memory: str = "") -> Dict[str, Any]:
    title = str(project_raw.get("name") or "Project").strip() or "Project"

    created_at = _iso_to_epoch_seconds(project_raw.get("created_at"))
    updated_at = _iso_to_epoch_seconds(project_raw.get("updated_at"))

    description = str(project_raw.get("description") or "").strip()
    prompt_template = str(project_raw.get("prompt_template") or "").strip()
    memory = str(memory or "").strip()

    blocks: List[str] = []
    if description:
        blocks.append(f"**Description**\n\n{description}")
    if prompt_template:
        blocks.append(f"**Prompt Template**\n\n```\n{prompt_template}\n```")
    if memory:
        blocks.append(f"**Project Memory (from export)**\n\n{memory}")

    content = "\n\n---\n\n".join(blocks).strip() or "(empty project)"

    meta = {
        "source": "claude_project",
        "model_slug": "Claude",
        "create_time": _safe_epoch(created_at),
        "update_time": _safe_epoch(updated_at),
    }

    return {
        "title": title,
        "messages": [{"role": "assistant", "ts": _safe_epoch(updated_at or created_at), "content": content}],
        "meta": meta,
    }


def normalize_gemini_activity(record: GeminiConversationRecord, folder: str) -> Dict[str, Any]:
    """Normalize one Gemini conversation (multi-turn grouped from activity logs)."""

    messages: List[Dict[str, Any]] = []

    for turn in record.turns or []:
        ts = _safe_epoch(turn.ts)
        user_content = (turn.prompt or "").strip()
        if user_content:
            messages.append({"role": "user", "ts": ts, "content": user_content})

        # User bubbles are rendered as plain text in the current frontend.
        # To display images nicely, emit an assistant markdown bubble for attachments.
        if turn.attachments:
            links = []
            images = []
            for rel in turn.attachments:
                url = _build_file_url(folder=folder, relpath=rel)
                name = rel.split("/")[-1] if rel else "file"

                lower = name.lower()
                if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                    images.append(f"![{name}]({url})")
                else:
                    links.append(f"- [{name}]({url})")

            attach_md = ""
            if images:
                attach_md += "\n".join(images)
            if links:
                attach_md = (attach_md.rstrip() + ("\n\n" if attach_md else "") + "附件：\n" + "\n".join(links)).strip()

            if attach_md:
                messages.append({"role": "assistant", "ts": ts, "content": attach_md})

        assistant_content = (turn.response_md or "").strip()
        if assistant_content:
            messages.append({"role": "assistant", "ts": ts, "content": assistant_content})

    meta = {
        "source": "gemini",
        "model_slug": "gemini",
        "create_time": _safe_epoch(record.created_at),
        "update_time": _safe_epoch(record.updated_at),
    }

    return {
        "title": record.title or "Gemini Apps",
        "messages": messages,
        "meta": meta,
    }


def extract_search_text_from_normalized(conversation: Dict[str, Any]) -> str:
    """Extract searchable text from normalized conversation."""
    out: List[str] = []

    title = conversation.get("title")
    if isinstance(title, str) and title.strip():
        out.append(title.strip())

    messages = conversation.get("messages")
    if isinstance(messages, list):
        for m in messages:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                out.append(c)

            th = m.get("thinking")
            if isinstance(th, list):
                for step in th:
                    if not isinstance(step, dict):
                        continue
                    t = step.get("content")
                    if isinstance(t, str) and t.strip():
                        out.append(t)

    return "\n".join(out)
