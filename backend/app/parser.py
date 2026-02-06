"""JSON 解析模块 - 核心逻辑：解析对话树形结构"""
from typing import Dict, List, Optional, Any, Tuple
import base64
import json
import re
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from app.gemini_batchexecute import is_gemini_batchexecute_export, parse_gemini_batchexecute_conversation


class ConversationParser:
    """对话解析器 - 将树状结构转换为线性消息流"""
    
    def __init__(self):
        """初始化解析器，编译正则表达式"""
        # 匹配所有 cite / filecite 引用标记格式：
        # - citeturn0search3 (纯文本)
        # - citeturn0search2turn0search3turn0search4 (多个turn，纯文本)
        # - ⸢cite⸣turn0search3⸣ (Unicode字符)
        # - citeturn0search3 (ChatGPT 导出常见私有区字符，\ue200/\ue202/\ue201)
        # - [⸢cite⸣turn0view0⸣]: (带方括号)
        # -  (文件引用，行号范围可选)
        self.cite_pattern = re.compile(
            r'(?:'
            r'⸢cite⸣(?:turn\d+[a-z]+\d+⸣)+|'  # ⸢cite⸣turn0search3⸣ / turn0news48 / turn0image1
            r'\[⸢cite⸣(?:turn\d+[a-z]+\d+⸣)+\]:?|'  # [⸢cite⸣turn0view0⸣]:
            r'\ue200cite\ue202(?:turn\d+[a-z]+\d+\ue202)*turn\d+[a-z]+\d+\ue201|'  # citeturn0search3 / turn0news48 / turn0image1
            r'\ue200filecite\ue202turn\d+file\d+(?:\ue202L\d{1,6}-L\d{1,6})?\ue201|'  # 
            r'[【\[]\s*\d{1,4}\s*:\s*\d{1,4}\s*[†+]\s*.*?\s*[†+]\s*L\s*\d{1,6}\s*[-–—]\s*L\s*\d{1,6}\s*[】\]]|'  # 
            r'【[^】]*?cite(?:turn\d+[a-z]+\d+)+[^】]*?】|'  # 【...citeturn0search3...】 (中文方括号)
            r'cite(?:turn\d+[a-z]+\d+)+'  # citeturn0search3 (纯文本，无Unicode)
            r'|【[^】]*?filecite.*?】|'  # 【...filecite...】（兜底）
            r'filecite(?:turn\d+file\d+)(?:L\d{1,6}-L\d{1,6})?'  # fileciteturn2file5L65-L75（纯文本兜底）
            r'|\ue200navlist\ue202.*?\ue201'  # navlist...
            r')',
            re.IGNORECASE
        )
    
    def _process_citations(self, text: str, content_references: List[Dict]) -> str:
        """
        处理文本中的引用标记，将其转换为Markdown链接
        
        Args:
            text: 原始文本
            content_references: 引用信息列表（从metadata中获取）
            
        Returns:
            处理后的文本（引用标记被替换为Markdown链接）
        """
        if not content_references:
            # 如果没有引用信息，直接删除cite标记
            return self.cite_pattern.sub('', text)

        # Deep research citations commonly look like:  (sometimes with '+' instead of '†')
        deep_ref_pattern = re.compile(
            r'^[【\[]\s*(\d{1,4})\s*[†+]\s*L\s*(\d{1,6})\s*[-–—]\s*L\s*(\d{1,6})\s*[】\]]$'
        )

        # Some exports include "message-index:chunk-index" style line-range citations, typically pointing at file/tool outputs:
        # 
        deep_msgref_pattern = re.compile(
            r'^[【\[]\s*(\d{1,4})\s*:\s*(\d{1,4})\s*[†+]\s*(.+?)\s*[†+]\s*L\s*(\d{1,6})\s*[-–—]\s*L\s*(\d{1,6})\s*[】\]]$'
        )

        def _encode_cite_payload(payload: Dict[str, Any]) -> str:
            raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            enc = base64.urlsafe_b64encode(raw).decode('ascii')
            return enc.rstrip('=')

        def _normalize_url(url: str) -> str:
            url = (url or '').strip()
            if not url:
                return ''
            # 处理 protocol-relative
            if url.startswith('//'):
                return 'https:' + url
            try:
                p = urlparse(url)
            except Exception:
                p = None
            if not p or not getattr(p, 'scheme', None):
                # 没有 scheme 的 URL 在浏览器会变成 localhost 相对路径
                return 'https://' + url.lstrip('/')
            return url

        def _domain_label(url: str) -> str:
            try:
                host = (urlparse(url).hostname or '').lower()
            except Exception:
                host = ''
            if host.startswith('www.'):
                host = host[4:]
            if not host:
                return 'ref'
            parts = [p for p in host.split('.') if p]
            if len(parts) >= 2:
                return parts[-2]
            return host

        def _canonicalize_url_for_dedupe(url: str) -> str:
            try:
                p = urlparse(url)
            except Exception:
                return url
            if not p.scheme:
                return url
            netloc = (p.netloc or '').lower()
            path = p.path or ''
            query = ''
            if p.query:
                pairs = parse_qsl(p.query, keep_blank_values=True)
                filtered = []
                for k, v in pairs:
                    lk = k.lower()
                    if lk.startswith('utm_'):
                        continue
                    if lk in {'gclid', 'fbclid', 'yclid', 'mc_cid', 'mc_eid'}:
                        continue
                    filtered.append((k, v))
                if filtered:
                    query = urlencode(filtered, doseq=True)
            return urlunparse((p.scheme.lower(), netloc, path, p.params, query, ''))

        def _extract_bracket_tag(s: str) -> str:
            """Extract a short '[Tag]' token to use as citation pill label."""
            try:
                m = re.search(r'\[([A-Za-z0-9._-]{1,40})\]', s or '')
            except Exception:
                m = None
            if not m:
                return ''
            return (m.group(1) or '').strip()
        
        def _normalize_cite_key(s: str) -> str:
            s = (s or '').strip()
            # 处理方括号包裹的格式：[⸢cite⸣...⸣]: 或 【...cite...】
            # 移除英文方括号
            if s.startswith('['):
                s = s[1:]
                if s.endswith(':'):
                    s = s[:-1]
                if s.endswith(']'):
                    s = s[:-1]
            # 移除中文方括号【】
            if s.startswith('【'):
                s = s[1:]
            if s.endswith('】'):
                s = s[:-1]
            # 移除【】中间可能包含的前缀文本（如 "manifold hypothesis"），只保留标记部分
            low = s.lower()
            if 'filecite' in low:
                idx = low.find('filecite')
                if idx > 0:
                    s = s[idx:]
            elif 'cite' in low:
                idx = low.find('cite')
                if idx > 0:
                    s = s[idx:]
            return s.strip()

        # 构建引用映射：matched_text -> refs(payload)
        citation_map: Dict[str, List[Dict[str, Any]]] = {}
        normalized_citation_map: Dict[str, List[Dict[str, Any]]] = {}
        deep_refs: List[Tuple[str, str, str, str, str]] = []
        deep_invalid_refs: List[Tuple[str, str, str]] = []
        for ref in content_references:
            matched_text = ref.get('matched_text', '')
            if not matched_text:
                continue

            ref_type = (ref.get('type') or '').lower()
            low_mt = matched_text.lower()

            # "3:10" style deep file/tool citations (even if marked invalid/hidden).
            mm = deep_msgref_pattern.match(matched_text.strip())
            if mm:
                msg_idx, chunk_idx, raw_label, l1, l2 = mm.group(1), mm.group(2), mm.group(3), mm.group(4), mm.group(5)
                raw_label = (raw_label or '').strip()
                host = _extract_bracket_tag(raw_label) or 'file'
                title = raw_label or f"ref {msg_idx}:{chunk_idx}"
                title = f"{title} (L{l1}-L{l2})"

                refs_payload = [{
                    'title': title,
                    'url': '',
                    'host': host,
                    'kind': 'file',
                    'marker': f"{msg_idx}:{chunk_idx}",
                    'line_start': int(l1) if l1.isdigit() else None,
                    'line_end': int(l2) if l2.isdigit() else None,
                }]
                citation_map[matched_text] = refs_payload
                normalized_citation_map[_normalize_cite_key(matched_text)] = refs_payload
                continue

            # File citations (my_files): 
            # NOTE: 'filecite' contains 'cite', so we must handle it before the generic 'cite' branch.
            if ref_type == 'file' or 'filecite' in low_mt:
                name = (ref.get('name') or 'file').strip() or 'file'
                file_id = ref.get('id') or ''

                ip = ref.get('input_pointer') or {}
                try:
                    l1 = int(ip.get('line_range_start')) if ip.get('line_range_start') is not None else None
                except Exception:
                    l1 = None
                try:
                    l2 = int(ip.get('line_range_end')) if ip.get('line_range_end') is not None else None
                except Exception:
                    l2 = None

                # Prefer a real document URL if present; otherwise keep empty (frontend will render as non-clickable).
                file_url = _normalize_url(ref.get('cloud_doc_url', '') or ref.get('url', '') or '')

                # Label/host: use file extension when possible (pdf/png/...) for compact pills.
                ext = ''
                try:
                    dot = name.rfind('.')
                    if dot >= 0 and dot < len(name) - 1:
                        ext = name[dot + 1 :].strip().lower()
                except Exception:
                    ext = ''
                host = ext or 'file'

                title = name
                if l1 is not None and l2 is not None:
                    title = f"{name} (L{l1}-L{l2})"
                elif l1 is not None:
                    title = f"{name} (L{l1})"

                snippet = ref.get('snippet') or ''
                refs_payload = [{
                    'title': title,
                    'url': file_url,
                    'host': host,
                    'kind': 'file',
                    'file_id': file_id,
                    'name': name,
                    'line_start': l1,
                    'line_end': l2,
                    'snippet': snippet,
                }]

                citation_map[matched_text] = refs_payload
                normalized_citation_map[_normalize_cite_key(matched_text)] = refs_payload
                continue

            # Web citations: citeturn0search3
            if 'cite' in low_mt:
                items = ref.get('items', [])
                
                # 收集链接信息
                links: List[Dict[str, Any]] = []
                seen_urls = set()
                max_links = 10

                def _add_link(title: str, url: str) -> None:
                    if not url or len(links) >= max_links:
                        return
                    dedupe_key = _canonicalize_url_for_dedupe(url)
                    if dedupe_key in seen_urls:
                        return
                    seen_urls.add(dedupe_key)
                    links.append({'title': title, 'url': url, 'host': _domain_label(url), 'kind': 'web'})

                for item in (items or []):
                    if len(links) >= max_links:
                        break
                    title = (item.get('title') or item.get('attribution') or 'Reference')
                    url = _normalize_url(item.get('url', ''))
                    if url:
                        # 清理title中可能的换行和特殊字符
                        title = title.replace('\n', ' ').replace('"', "'").strip()[:80]  # 限制长度
                        if not title:
                            title = _domain_label(url)
                        _add_link(title, url)

                    # 追加 supporting_websites（通常包含更多有标题的链接）
                    supporting_sites = item.get('supporting_websites', []) or []
                    for site in supporting_sites:
                        if len(links) >= max_links:
                            break
                        site_url = _normalize_url(site.get('url', ''))
                        if not site_url:
                            continue
                        site_title = (site.get('title') or site.get('attribution') or _domain_label(site_url))
                        site_title = str(site_title).replace('\n', ' ').replace('"', "'").strip()[:80]
                        if not site_title:
                            site_title = _domain_label(site_url)
                        _add_link(site_title, site_url)

                # 有些导出里 items 不带 url 或只有少量，补充 safe_urls
                safe_urls = ref.get('safe_urls', []) or []
                for u in safe_urls:
                    if len(links) >= max_links:
                        break
                    uu = _normalize_url(str(u))
                    if uu:
                        _add_link(_domain_label(uu), uu)
                
                if links:
                    citation_map[matched_text] = links
                    normalized_citation_map[_normalize_cite_key(matched_text)] = links
                continue

            # Deep research line-range citations:  -> linkify as [[4]](url "...")
            m = deep_ref_pattern.match(matched_text.strip())
            if not m:
                continue

            url = _normalize_url(ref.get('url', ''))
            if not url:
                # Some exports include invalid/hidden deep research citations with no URL.
                if ref.get('invalid') is True:
                    deep_invalid_refs.append((m.group(1), m.group(2), m.group(3)))
                continue

            num, l1, l2 = m.group(1), m.group(2), m.group(3)
            title = (ref.get('title') or ref.get('attribution') or _domain_label(url) or 'Reference')
            attribution = (ref.get('attribution') or _domain_label(url) or 'ref')
            deep_refs.append((num, l1, l2, url, f"{attribution}: {title}"))
        
        def _format_citation_pill(refs_in: List[Dict[str, Any]]) -> str:
            # ChatGPT 风格：每个 cite 标记对应一个“按钮”，按钮内显示来源名，多个来源显示 +N
            if not refs_in:
                return ''

            refs: List[Dict[str, Any]] = []
            for r in refs_in:
                url = (r.get('url') or '').strip()
                title = (r.get('title') or 'Reference').strip()
                host = (r.get('host') or (_domain_label(url) if url else '') or 'ref').strip()
                out: Dict[str, Any] = {'title': title, 'url': url, 'host': host}
                # Pass through optional metadata for richer rendering (e.g., file citations).
                for k in ('kind', 'file_id', 'name', 'line_start', 'line_end', 'snippet'):
                    if k in r and r.get(k) is not None:
                        out[k] = r.get(k)
                refs.append(out)

            if not refs:
                return ''

            label_base = refs[0].get('host') or 'ref'
            label = label_base if len(refs) == 1 else f"{label_base} +{len(refs) - 1}"

            payload = {
                'refs': refs,
            }
            payload_enc = _encode_cite_payload(payload)

            # react-markdown 默认会“清洗”不认识的协议（例如 cite://），导致 href 变空，
            # 点击就会跳到 localhost:3000。
            # 所以这里把 href 设为第一条真实 URL，把 payload 放到 title 里。
            href = refs[0].get('url') or 'about:blank'
            title = f"citepayload:{payload_enc}"
            return f"[{label}](<{href}> \"{title}\")"

        # 按文本中出现顺序替换 cite 标记，避免 replace+排序造成编号/替换不稳定
        result_parts: List[str] = []
        last_end = 0
        for m in self.cite_pattern.finditer(text):
            result_parts.append(text[last_end:m.start()])

            matched_text = m.group(0)
            links = citation_map.get(matched_text)
            if not links:
                links = normalized_citation_map.get(_normalize_cite_key(matched_text))
            if links:
                result_parts.append(_format_citation_pill(links))
            # else: 没有匹配到引用信息就直接移除

            last_end = m.end()

        result_parts.append(text[last_end:])
        result = ''.join(result_parts)

        # 再兜底清理一次（以防 content_references 里的 matched_text 和正文略有不一致）
        result = self.cite_pattern.sub('', result)

        # Deep research citations: materialize 【n†Lx-Ly】 into real links so frontend can render them.
        # Use [[n]](...) so the visible label becomes "[n]" and is styled consistently by the frontend.
        if deep_refs:
            for num, l1, l2, url, label_title in deep_refs:
                safe_title = str(label_title).replace('\n', ' ').replace('"', "'").strip()
                if len(safe_title) > 200:
                    safe_title = safe_title[:200]

                replacement = f"[[{num}]](<{url}> \"{safe_title} (L{l1}-L{l2})\")"
                pat = re.compile(
                    rf'[【\[]\s*{re.escape(num)}\s*[†+]\s*L\s*{re.escape(l1)}\s*[-–—]\s*L\s*{re.escape(l2)}\s*[】\]]'
                )
                result = pat.sub(lambda _m, rep=replacement: rep, result)

        # Remove invalid/hidden deep research markers (no URL) so they don't look like broken links.
        if deep_invalid_refs:
            for num, l1, l2 in deep_invalid_refs:
                pat = re.compile(
                    rf'[【\[]\s*{re.escape(num)}\s*[†+]\s*L\s*{re.escape(l1)}\s*[-–—]\s*L\s*{re.escape(l2)}\s*[】\]]'
                )
                result = pat.sub('', result)

        return result
    
    def parse_conversation(self, json_data: Dict) -> Dict:
        """
        解析对话 JSON，提取关键信息
        
        Args:
            json_data: 原始 JSON 数据
            
        Returns:
            {
                'title': '对话标题',
                'messages': [
                    {'role': 'user', 'content': '...'},
                    {'role': 'assistant', 'thinking': [...], 'content': '...'},
                    ...
                ]
            }
        """
        # Gemini per-conversation export JSONs (data/gemini_export_*) embed a batchexecute payload.
        # Normalize them into the same API shape expected by the frontend.
        if is_gemini_batchexecute_export(json_data):
            return parse_gemini_batchexecute_conversation(json_data)

        mapping = json_data.get('mapping', {})
        messages = []

        # 1) Prefer the active branch indicated by current_node (more reliable than children[0])
        current_node = json_data.get('current_node')
        if isinstance(current_node, str) and current_node in mapping:
            for node_id in self._build_path_to_root(mapping, current_node):
                node = mapping.get(node_id)
                if not isinstance(node, dict):
                    continue
                message = node.get('message')
                if not message:
                    continue

                # 检查是否是隐藏的系统消息
                metadata = message.get('metadata', {})
                is_hidden = metadata.get('is_visually_hidden_from_conversation', False)
                role = message.get('author', {}).get('role', '')
                if role == 'system' and is_hidden:
                    continue

                extracted = self._extract_message(message)
                if extracted:
                    messages.append(extracted)
        else:
            # 2) Fall back to legacy traversal
            root_id = self._find_root_node(mapping)
            if root_id:
                self._traverse_and_extract(mapping, root_id, messages)
        
        # 3. 清理和合并消息
        cleaned_messages = self._clean_messages(messages)
        
        meta = self._extract_conversation_meta(json_data)

        return {
            'title': json_data.get('title', 'Untitled'),
            'messages': cleaned_messages,
            'meta': meta,
        }

    def _build_path_to_root(self, mapping: Dict, leaf_id: str) -> List[str]:
        """Build the active node path from root -> leaf using parent pointers."""
        path: List[str] = []
        visited = set()
        cur = leaf_id

        while isinstance(cur, str) and cur and cur not in visited:
            visited.add(cur)
            path.append(cur)
            node = mapping.get(cur)
            if not isinstance(node, dict):
                break
            parent = node.get('parent')
            if not parent:
                break
            cur = parent

        path.reverse()
        return path

    def _extract_conversation_meta(self, json_data: Dict) -> Dict[str, Any]:
        """Extract model + reasoning info from exported ChatGPT JSON.

        We try to find the most recent message node that contains model info.
        """
        mapping = json_data.get('mapping', {})
        if not isinstance(mapping, dict):
            mapping = {}

        best: Tuple[float, Dict[str, Any]] = (0.0, {})

        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            message = node.get('message')
            if not isinstance(message, dict):
                continue
            metadata = message.get('metadata')
            if not isinstance(metadata, dict):
                continue

            model_slug = metadata.get('model_slug') or metadata.get('default_model_slug')
            thinking_effort = metadata.get('thinking_effort')
            if not (model_slug or thinking_effort):
                continue

            # Choose the latest message that includes model information.
            t = message.get('create_time') or message.get('update_time') or 0.0
            try:
                t = float(t) if t is not None else 0.0
            except Exception:
                t = 0.0

            cand = {
                'model_slug': model_slug,
                'thinking_effort': thinking_effort,
            }
            if t >= best[0]:
                best = (t, cand)

        # Fall back to root-level times if needed for consistency
        root_create = json_data.get('create_time')
        root_update = json_data.get('update_time')
        try:
            root_create = float(root_create) if root_create is not None else None
        except Exception:
            root_create = None
        
        try:
            root_update = float(root_update) if root_update is not None else None
        except Exception:
            root_update = None

        out = best[1] or {}
        out['create_time'] = root_create
        out['update_time'] = root_update
        return out
    
    def _find_root_node(self, mapping: Dict) -> Optional[str]:
        """
        找到根节点
        
        根节点特征：parent 为 None 或特殊值
        """
        for node_id, node in mapping.items():
            parent = node.get('parent')
            if not parent or parent in ['client-created-root', 'root']:
                return node_id
        return None
    
    def _traverse_and_extract(self, mapping: Dict, node_id: str, messages: List[Dict]):
        """
        深度优先遍历，提取消息
        
        Args:
            mapping: 消息映射
            node_id: 当前节点ID
            messages: 消息列表（输出）
        """
        node = mapping.get(node_id)
        if not node:
            return
        
        message = node.get('message')
        if not message:
            # 没有消息内容，直接处理子节点
            children = node.get('children', [])
            if children:
                self._traverse_and_extract(mapping, children[0], messages)
            return
        
        # 检查是否是隐藏的系统消息
        metadata = message.get('metadata', {})
        is_hidden = metadata.get('is_visually_hidden_from_conversation', False)
        
        role = message.get('author', {}).get('role', '')
        
        if role == 'system' and is_hidden:
            # 跳过隐藏的系统消息，但继续处理子节点
            children = node.get('children', [])
            if children:
                self._traverse_and_extract(mapping, children[0], messages)
            return
        
        # 提取消息内容
        extracted = self._extract_message(message)
        if extracted:
            messages.append(extracted)
        
        # 继续处理子节点（选择第一个分支）
        children = node.get('children', [])
        if children:
            self._traverse_and_extract(mapping, children[0], messages)
    
    def _extract_message(self, message: Dict) -> Optional[Dict]:
        """
        从消息节点提取有用信息
        
        Returns:
            None 或 {'role': 'user/assistant', 'content': '...', 'thinking': [...]}
        """
        role = message.get('author', {}).get('role', '')
        content_data = message.get('content', {})
        content_type = content_data.get('content_type', '')
        metadata = message.get('metadata', {})

        # Per-message timestamp (seconds since epoch)
        ts = message.get('create_time') or message.get('update_time')
        try:
            ts = float(ts) if ts is not None else None
        except Exception:
            ts = None
        
        # 获取引用信息
        content_references = metadata.get('content_references', [])

        def _is_pro_mode_reasoning() -> bool:
            if role != 'tool':
                return False
            if content_type != 'text':
                return False
            if metadata.get('async_task_type') == 'pro_mode':
                return True
            if metadata.get('async_task_id') and (metadata.get('model_slug', '') or '').endswith('-pro'):
                return True
            return False
        
        # 用户消息
        if role == 'user' and content_type == 'text':
            parts = content_data.get('parts', [])
            if parts:
                content = '\n'.join(str(p) for p in parts)
                return {
                    'role': 'user',
                    'ts': ts,
                    'content': self._process_citations(content, content_references)
                }

        # GPT-Pro（pro_mode）思考链通常是 tool 角色 + text
        if _is_pro_mode_reasoning():
            parts = content_data.get('parts', [])
            if parts:
                content = '\n'.join(str(p) for p in parts).strip()
                if content:
                    return {
                        'role': 'assistant',
                        'type': 'thinking',
                        'ts': ts,
                        'thinking': [
                            {
                                'content': self._process_citations(content, content_references)
                            }
                        ]
                    }
        
        # 助手消息 - 思考过程
        elif role == 'assistant' and content_type == 'thoughts':
            thoughts = content_data.get('thoughts', [])
            # 处理思考过程中的引用标记
            cleaned_thoughts = []
            for thought in thoughts:
                cleaned_thought = thought.copy()
                if 'content' in cleaned_thought:
                    cleaned_thought['content'] = self._process_citations(cleaned_thought['content'], content_references)
                if 'summary' in cleaned_thought:
                    cleaned_thought['summary'] = self._process_citations(cleaned_thought['summary'], content_references)
                cleaned_thoughts.append(cleaned_thought)
            return {
                'role': 'assistant',
                'type': 'thinking',
                'ts': ts,
                'thinking': cleaned_thoughts
            }
        
        # 助手消息 - 思考总结
        elif role == 'assistant' and content_type == 'reasoning_recap':
            recap_content = content_data.get('content', '')
            duration = metadata.get('finished_duration_sec', 0)
            return {
                'role': 'assistant',
                'type': 'thinking_recap',
                'ts': ts,
                'thinking_summary': self._process_citations(recap_content, content_references),
                'thinking_duration': duration
            }
        
        # 助手消息 - 文本回复
        elif role == 'assistant' and content_type == 'text':
            parts = content_data.get('parts', [])
            if parts:
                content = '\n'.join(str(p) for p in parts)
                return {
                    'role': 'assistant',
                    'type': 'text',
                    'ts': ts,
                    'content': self._process_citations(content, content_references)
                }
        
        return None
    
    def _clean_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        清理和合并消息
        
        将连续的 assistant 消息（thinking + text）合并为一条消息
        """
        if not messages:
            return []
        
        cleaned = []
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            
            if msg['role'] == 'user':
                # 用户消息直接添加
                cleaned.append({
                    'role': 'user',
                    'ts': msg.get('ts'),
                    'content': msg['content']
                })
                i += 1
            
            elif msg['role'] == 'assistant':
                # 助手消息 - 可能需要合并 thinking + text
                assistant_msg = {
                    'role': 'assistant',
                    'ts': None,
                    'thinking': [],
                    'thinking_summary': None,
                    'thinking_duration': None,
                    'content': ''
                }
                
                # 收集连续的 assistant 消息
                while i < len(messages) and messages[i]['role'] == 'assistant':
                    current = messages[i]
                    msg_type = current.get('type', '')

                    # Prefer the latest timestamp in the merged assistant block
                    try:
                        cur_ts = float(current.get('ts')) if current.get('ts') is not None else None
                    except Exception:
                        cur_ts = None
                    if cur_ts is not None and (assistant_msg['ts'] is None or cur_ts > assistant_msg['ts']):
                        assistant_msg['ts'] = cur_ts
                    
                    if msg_type == 'thinking':
                        cur_thinking = current.get('thinking', [])
                        if isinstance(cur_thinking, list) and cur_thinking:
                            assistant_msg['thinking'].extend(cur_thinking)
                    elif msg_type == 'thinking_recap':
                        assistant_msg['thinking_summary'] = current.get('thinking_summary', '')
                        assistant_msg['thinking_duration'] = current.get('thinking_duration', 0)
                    elif msg_type == 'text':
                        assistant_msg['content'] = current.get('content', '')
                    
                    i += 1
                
                # Normalize empty thinking list to None
                if not assistant_msg['thinking']:
                    assistant_msg['thinking'] = None

                # 只有在有实际内容时才添加
                if assistant_msg['content'] or assistant_msg['thinking'] or assistant_msg.get('thinking_summary'):
                    # 移除 None 值
                    cleaned_msg = {k: v for k, v in assistant_msg.items() if v is not None}
                    cleaned.append(cleaned_msg)
            else:
                i += 1
        
        return cleaned


# 创建全局解析器实例
parser = ConversationParser()

