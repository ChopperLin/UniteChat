"""API 路由"""
import json
import os
import threading
import time
import subprocess
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file
from app.scanner import scanner
from app.parser import parser
from app.normalize import normalize_claude_conversation, normalize_claude_project, normalize_gemini_activity
from app.search import searcher
from app.overrides import set_override, get_override

api = Blueprint('api', __name__)


def _pick_directory_dialog(initial_dir: str = '', title: str = '选择数据根目录') -> str:
    """Open a native folder picker on the local machine running backend."""
    init = str(initial_dir or '').strip()
    ttl = str(title or '选择数据根目录').strip() or '选择数据根目录'

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askdirectory(
            initialdir=init or str(scanner.source_store.base_dir),
            title=ttl,
            mustexist=True,
        )
        try:
            root.destroy()
        except Exception:
            pass
        return str(selected or '').strip()
    except Exception:
        pass

    if os.name == 'nt':
        escaped_title = ttl.replace("'", "''")
        escaped_init = (init or str(scanner.source_store.base_dir)).replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description='{escaped_title}'; "
            "$d.ShowNewFolderButton=$false; "
            f"$d.SelectedPath='{escaped_init}'; "
            "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){"
            " [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            " Write-Output $d.SelectedPath }"
        )
        try:
            done = subprocess.run(
                ['powershell', '-NoProfile', '-STA', '-Command', ps],
                capture_output=True,
                text=True,
                timeout=240,
            )
            if done.returncode == 0:
                return str(done.stdout or '').strip()
        except Exception:
            pass

    return ''


def _get_folder_entries():
    return scanner.get_available_folder_entries()


def _pick_default_folder() -> str:
    entries = _get_folder_entries()
    if not entries:
        scanner.current_folder = None
        return ''
    first_id = str(entries[0].get('id') or '').strip()
    if not scanner.current_folder:
        scanner.set_folder(first_id)
    return scanner.current_folder or first_id


def _resolve_folder_path(folder_id: str) -> Path:
    p = scanner.get_folder_path(folder_id)
    if not p:
        raise FileNotFoundError(f'Folder not found: {folder_id}')
    return Path(p).resolve()


def _settings_payload(success: bool = True, **extra):
    data = {
        'success': bool(success),
        'sources': scanner.source_store.get_sources_for_api(),
        'root': scanner.source_store.get_root_for_api(),
        'folders': _get_folder_entries(),
        'current': scanner.current_folder or '',
    }
    data.update(extra or {})
    return data


@api.route('/folders', methods=['GET'])
def get_folders():
    """
    获取所有可用的聊天记录文件夹
    
    Returns:
        {
            'folders': ['chatgpt_team_chat_1231', 'another_chat_folder', ...],
            'current': 'chatgpt_team_chat_1231'
        }
    """
    try:
        folders = _get_folder_entries()
        current = _pick_default_folder()

        if current:
            folder_path = scanner.get_folder_path(current)
            if folder_path:
                searcher.schedule_build(current, Path(folder_path))

        return jsonify({
            'folders': folders,
            'current': current
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/folders/<folder_name>', methods=['POST'])
def set_folder(folder_name):
    """
    设置当前使用的文件夹
    
    Args:
        folder_name: 文件夹名称
        
    Returns:
        {'success': True/False}
    """
    try:
        success = scanner.set_folder(folder_name)
        if success:
            folder_path = scanner.get_folder_path(folder_name)
            if folder_path:
                searcher.schedule_build(folder_name, Path(folder_path))
            return jsonify({'success': True, 'folder': folder_name})
        else:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/settings/sources', methods=['GET'])
def get_data_sources_settings():
    """获取数据源设置（目录 + 类型映射）。"""
    try:
        return jsonify(_settings_payload(success=True, current=_pick_default_folder()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/settings/sources', methods=['PUT'])
def update_data_sources_settings():
    """更新数据源设置。"""
    needs_reload = False
    try:
        payload = request.get_json(silent=True) or {}
        incoming_sources = payload.get('sources')
        if not isinstance(incoming_sources, list):
            return jsonify({'error': 'sources must be a list'}), 400

        existing_by_id = {
            str(s.id): s
            for s in scanner.source_store.load_sources()
            if getattr(s, 'id', None)
        }
        rename_plan = []
        seen_ids = set()
        for item in incoming_sources:
            if not isinstance(item, dict):
                continue
            sid = str(item.get('id') or '').strip()
            if not sid or sid in seen_ids:
                continue
            src = existing_by_id.get(sid)
            if not src:
                continue
            desired_name = str(item.get('name') or '').strip()
            if not desired_name:
                continue
            if scanner.source_store.has_glob_magic(src.path):
                continue
            try:
                current_base = scanner.source_store.resolve_path(src.path).name.strip()
            except Exception:
                current_base = ''
            if current_base and current_base != desired_name:
                rename_plan.append((sid, desired_name))
                seen_ids.add(sid)

        if rename_plan:
            scanner.stop_watcher()
            needs_reload = True
            scanner.clear_cache()
            searcher.invalidate_all()
            searcher.wait_for_idle(timeout_sec=3.0)
            for sid, desired_name in rename_plan:
                scanner.source_store.rename_source_folder(source_id=sid, new_name=desired_name)

        latest_by_id = {
            str(s.id): s
            for s in scanner.source_store.load_sources()
            if getattr(s, 'id', None)
        }
        merged_sources = []
        for item in incoming_sources:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            sid = str(row.get('id') or '').strip()
            src = latest_by_id.get(sid)
            if src:
                row['path'] = src.path
                if not str(row.get('name') or '').strip():
                    row['name'] = src.name
            merged_sources.append(row)

        scanner.source_store.update_from_payload(merged_sources)
        folders = scanner.reload_sources(keep_current=True)
        needs_reload = False
        searcher.invalidate_all()

        requested_current = str(payload.get('current') or '').strip()
        if requested_current:
            scanner.set_folder(requested_current)
        current = scanner.current_folder
        if (not current) and folders:
            first_id = str((folders[0] or {}).get('id') or '').strip()
            if first_id:
                scanner.set_folder(first_id)
                current = scanner.current_folder

        return jsonify(_settings_payload(success=True, current=current or ''))
    except (ValueError, FileExistsError) as e:
        return jsonify({'error': str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if needs_reload:
            try:
                scanner.reload_sources(keep_current=True)
            except Exception:
                pass


@api.route('/settings/sources/import', methods=['POST'])
def import_data_sources_settings():
    """按路径模式批量导入数据源（例如 D:/Exports/*）。"""
    try:
        payload = request.get_json(silent=True) or {}
        pattern = str(payload.get('pattern') or '').strip()
        if not pattern:
            return jsonify({'error': 'pattern is required'}), 400

        kind = str(payload.get('kind') or 'auto').strip().lower()
        enabled = payload.get('enabled', True) is not False

        summary = scanner.source_store.import_from_pattern(pattern=pattern, kind=kind, enabled=enabled)
        folders = scanner.reload_sources(keep_current=True)
        searcher.invalidate_all()

        if (not scanner.current_folder) and folders:
            first_id = str((folders[0] or {}).get('id') or '').strip()
            if first_id:
                scanner.set_folder(first_id)

        return jsonify(
            _settings_payload(
                success=True,
                matched=int(summary.get('matched') or 0),
                imported=int(summary.get('imported') or 0),
                skipped=int(summary.get('skipped') or 0),
            )
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/settings/sources/pick-root', methods=['POST'])
def pick_data_sources_root():
    """Open native folder picker and return selected root path."""
    try:
        payload = request.get_json(silent=True) or {}
        initial = str(payload.get('initial') or '').strip()
        title = str(payload.get('title') or '选择数据根目录').strip()
        selected = _pick_directory_dialog(initial_dir=initial, title=title)
        return jsonify({
            'selected': selected,
            'cancelled': not bool(selected),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/settings/sources/import-root', methods=['POST'])
def import_data_sources_from_root():
    """Import child folders from a root directory and auto-detect each folder type."""
    try:
        payload = request.get_json(silent=True) or {}
        root = str(payload.get('root') or '').strip()
        if not root:
            return jsonify({'error': 'root is required'}), 400

        enabled = payload.get('enabled', True) is not False
        include_root = payload.get('include_root', False) is True

        summary = scanner.source_store.import_from_root(
            root=root,
            enabled=enabled,
            include_root=include_root,
        )
        folders = scanner.reload_sources(keep_current=True)
        searcher.invalidate_all()

        if (not scanner.current_folder) and folders:
            first_id = str((folders[0] or {}).get('id') or '').strip()
            if first_id:
                scanner.set_folder(first_id)

        return jsonify(
            _settings_payload(
                success=True,
                root=str(summary.get('root') or ''),
                scanned=int(summary.get('scanned') or 0),
                matched=int(summary.get('matched') or 0),
                imported=int(summary.get('imported') or 0),
                skipped=int(summary.get('skipped') or 0),
                detected=summary.get('detected') or {},
            )
        )
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/settings/sources/<source_id>/delete', methods=['POST'])
def delete_data_source(source_id):
    """Delete one data source config and optionally delete its folder from disk."""
    needs_reload = False
    try:
        payload = request.get_json(silent=True) or {}
        delete_dir = payload.get('delete_dir', True) is not False
        sid = str(source_id or '').strip()
        was_current = str(scanner.current_folder or '').strip() == sid

        # Deletion must have priority over background readers/index builders.
        scanner.stop_watcher()
        needs_reload = True
        scanner.clear_cache()
        searcher.invalidate_all()
        searcher.wait_for_idle(timeout_sec=3.0)

        out = scanner.source_store.delete_source(source_id=source_id, delete_dir=delete_dir)
        searcher.invalidate_all()
        scanner.reload_sources(keep_current=True)
        needs_reload = False
        return jsonify(
            _settings_payload(
                success=True,
                removed=out.get('removed') or {},
                delete_dir=bool(delete_dir),
                removed_current=bool(was_current),
            )
        )
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except (ValueError, FileExistsError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if needs_reload:
            try:
                scanner.reload_sources(keep_current=True)
            except Exception:
                pass


@api.route('/settings/sources/<source_id>/rename', methods=['POST'])
def rename_data_source_folder(source_id):
    """Rename one source folder on disk and persist the updated source path."""
    try:
        payload = request.get_json(silent=True) or {}
        new_name = payload.get('name')
        if not isinstance(new_name, str):
            return jsonify({'error': 'name must be a string'}), 400

        out = scanner.source_store.rename_source_folder(source_id=source_id, new_name=new_name)
        scanner.reload_sources(keep_current=True)
        searcher.invalidate_all()
        return jsonify(
            _settings_payload(
                success=True,
                renamed=out.get('renamed') or {},
            )
        )
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except (ValueError, FileExistsError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/refresh', methods=['POST'])
def refresh_cache():
    """
    手动刷新缓存（清除所有缓存数据）
    
    Returns:
        {'success': True, 'message': '...'}
    """
    try:
        scanner.reload_sources(keep_current=True)
        searcher.invalidate_all()
        return jsonify({'success': True, 'message': '缓存已刷新'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/conversations', methods=['GET'])
def get_conversations():
    """
    获取所有对话列表，按分类组织
    
    Query params:
        folder: 文件夹名称（可选）
    
    Returns:
        {
            'AI': [
                {'id': 'xxx', 'title': 'xxx'},
                ...
            ],
            'CS': [...],
            ...
        }
    """
    folder = request.args.get('folder')
    try:
        conversations = scanner.scan_all_conversations(folder)

        # 后台预热构建搜索索引（不阻塞）
        folder_to_index = folder or scanner.current_folder
        if folder_to_index:
            folder_path = scanner.get_folder_path(folder_to_index)
            if folder_path:
                searcher.schedule_build(folder_to_index, Path(folder_path))

        return jsonify(conversations)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """
    获取单个对话的完整内容（已解析）
    
    Args:
        chat_id: 对话ID
        category: 分类名称（query 参数）
        folder: 文件夹名称（query 参数，可选）
        
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
    category = request.args.get('category', 'AI')
    folder = request.args.get('folder')
    
    try:
        src = scanner.resolve_chat_source(chat_id, category, folder)

        if src.kind == 'chatgpt_file':
            with open(src.file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            conversation = parser.parse_conversation(json_data)

            # Keep UI consistent with the listing (derived from filename).
            # This also enables persistent "rename" by renaming the file, without rewriting exports.
            if isinstance(conversation, dict):
                stem = src.file_path.stem
                parts = stem.rsplit('_', 1)
                if len(parts) == 2 and parts[0].strip():
                    conversation['title'] = parts[0].strip()
            return jsonify(conversation)

        if src.kind == 'claude':
            special = scanner.get_special_folder_cache(src.folder) or {}
            claude_cache = special.get('claude_cache')
            if not claude_cache:
                raise FileNotFoundError('Claude cache not available')
            rec = (claude_cache.by_uuid.get(chat_id) if hasattr(claude_cache, 'by_uuid') else None)
            if not rec:
                raise FileNotFoundError(f'Chat not found: {chat_id}')

            conversation = normalize_claude_conversation(rec.raw)
            try:
                ov = get_override(_resolve_folder_path(src.folder), f"claude:{chat_id}") or {}
                if ov.get("deleted") is True:
                    raise FileNotFoundError(f'Chat not found: {chat_id}')
                t2 = ov.get("title")
                if isinstance(t2, str) and t2.strip() and isinstance(conversation, dict):
                    conversation["title"] = t2.strip()
            except FileNotFoundError:
                raise
            except Exception:
                pass
            return jsonify(conversation)

        if src.kind == 'claude_project':
            special = scanner.get_special_folder_cache(src.folder) or {}
            claude_cache = special.get('claude_cache')
            if not claude_cache:
                raise FileNotFoundError('Claude cache not available')

            project_uuid = (src.extra or {}).get('project_uuid')
            pr = (claude_cache.by_project_uuid.get(project_uuid) if hasattr(claude_cache, 'by_project_uuid') and project_uuid else None)
            if not pr:
                raise FileNotFoundError(f'Project not found: {project_uuid}')
            conversation = normalize_claude_project(pr.raw, memory=getattr(pr, 'memory', '') or '')
            return jsonify(conversation)

        if src.kind == 'gemini':
            special = scanner.get_special_folder_cache(src.folder) or {}
            gemini_cache = special.get('gemini_cache')
            if not gemini_cache:
                raise FileNotFoundError('Gemini cache not available')
            rec = (gemini_cache.by_id.get(chat_id) if hasattr(gemini_cache, 'by_id') else None)
            if not rec:
                raise FileNotFoundError(f'Chat not found: {chat_id}')
            conversation = normalize_gemini_activity(rec, folder=src.folder)
            return jsonify(conversation)

        return jsonify({'error': f'Unsupported chat source: {src.kind}'}), 400
    
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/chat/<chat_id>', methods=['PATCH'])
def rename_chat(chat_id):
    """Rename a single conversation (persistent, by renaming its JSON file).

    Supported:
    - ChatGPT-style per-file JSON exports
    - Gemini web batchexecute per-file JSON exports (data/gemini_export_*)

    Query params:
        category: category name
        folder: folder name
    Body (JSON):
        {"title": "New title"}
    """
    category = request.args.get('category', 'AI')
    folder = request.args.get('folder')

    try:
        payload = request.get_json(silent=True) or {}
        new_title = payload.get('title')
        if not isinstance(new_title, str):
            return jsonify({'error': 'title must be a string'}), 400
        new_title = new_title.strip()
        if not new_title:
            return jsonify({'error': 'title cannot be empty'}), 400
        if len(new_title) > 160:
            return jsonify({'error': 'title too long (max 160 chars)'}), 400

        src = scanner.resolve_chat_source(chat_id, category, folder)

        if src.kind == 'chatgpt_file':
            # Prevent path traversal / illegal filename chars (Windows).
            if any(ch in new_title for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']):
                return jsonify({'error': 'title contains illegal filename characters'}), 400

            old_path = Path(src.file_path).resolve()
            root = _resolve_folder_path(src.folder)
            if root not in old_path.parents:
                return jsonify({'error': 'invalid path'}), 400

            new_path = old_path.with_name(f"{new_title}_{chat_id}{old_path.suffix}")
            if new_path.exists() and new_path != old_path:
                return jsonify({'error': 'a conversation with the same title already exists'}), 409

            if new_path != old_path:
                old_path.rename(new_path)
        elif src.kind == 'claude':
            # Persist rename into overrides file; do not mutate the original export JSON.
            set_override(_resolve_folder_path(src.folder), f"claude:{chat_id}", {"title": new_title, "deleted": False})
        else:
            return jsonify({'error': f'Unsupported rename source: {src.kind}'}), 400

        scanner.clear_cache()
        folder_to_index = folder or scanner.current_folder
        if folder_to_index:
            searcher.invalidate(folder_to_index)
        if folder_to_index:
            folder_path = scanner.get_folder_path(folder_to_index)
            if folder_path:
                searcher.schedule_build(folder_to_index, Path(folder_path))

        return jsonify({'success': True, 'title': new_title})
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/chat/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """Delete a single conversation record (persistent).

    Currently supported:
    - ChatGPT-style per-file JSON exports
    - Gemini web batchexecute per-file JSON exports (data/gemini_export_*)

    Query params:
        category: category name
        folder: folder name
    """
    category = request.args.get('category', 'AI')
    folder = request.args.get('folder')

    try:
        src = scanner.resolve_chat_source(chat_id, category, folder)
        if src.kind == 'chatgpt_file':
            p = Path(src.file_path).resolve()
            root = _resolve_folder_path(src.folder)
            if root not in p.parents:
                return jsonify({'error': 'invalid path'}), 400

            if p.exists():
                p.unlink()
        elif src.kind == 'claude':
            # Persist delete as a hide flag.
            set_override(_resolve_folder_path(src.folder), f"claude:{chat_id}", {"deleted": True})
        else:
            return jsonify({'error': f'Unsupported delete source: {src.kind}'}), 400

        scanner.clear_cache()

        folder_to_index = folder or scanner.current_folder
        if folder_to_index:
            searcher.invalidate(folder_to_index)
        if folder_to_index:
            folder_path = scanner.get_folder_path(folder_to_index)
            if folder_path:
                searcher.schedule_build(folder_to_index, Path(folder_path))

        return jsonify({'success': True})
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/file', methods=['GET'])
def get_file():
    """Serve a file from within a selected data folder.

    Used primarily for Gemini Takeout attachments (images, pdfs, etc.).

    Query params:
        folder: folder name under data/
        path: relative path within that folder
    """
    folder = (request.args.get('folder') or '').strip()
    relpath = (request.args.get('path') or '').strip().lstrip('/').lstrip('\\')

    if not folder or not relpath:
        return jsonify({'error': 'folder and path are required'}), 400

    folder_root = scanner.get_folder_path(folder)
    if not folder_root:
        return jsonify({'error': 'folder not found'}), 404
    folder_root = Path(folder_root).resolve()
    target = (folder_root / relpath).resolve()

    # Prevent path traversal
    if folder_root not in target.parents and target != folder_root:
        return jsonify({'error': 'invalid path'}), 400

    if not target.exists() or not target.is_file():
        return jsonify({'error': 'file not found'}), 404

    try:
        return send_file(str(target), as_attachment=False)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/search', methods=['GET'])
def search_conversations():
    """搜索对话（标题 + 内容）。

    Query params:
        q: 关键词
        folder: 文件夹名称（可选）
        limit: 返回条数（默认 50，最大 200）

    Returns:
        {
          'query': 'xxx',
          'folder': 'chatgpt_team_chat_1231',
          'ready': true,
          'results': [{id, category, title, snippet, score}, ...],
          'stats': {docCount, tookMs}
        }
    """
    q = request.args.get('q', '')
    folder = request.args.get('folder')
    scope = request.args.get('scope', '')
    limit = request.args.get('limit', 50)

    try:
        limit_n = max(1, min(int(limit or 50), 200))
    except Exception:
        limit_n = 50

    try:
        folder_entries = {str(f.get('id')): f for f in _get_folder_entries()}

        if str(scope).lower() == 'all':
            if not folder_entries:
                return jsonify({
                    'query': q,
                    'folder': '',
                    'scope': 'all',
                    'ready': True,
                    'results': [],
                    'stats': {'docCount': 0, 'tookMs': 0}
                })

            t0 = time.perf_counter()
            all_results = []
            total_docs = 0
            ready = True

            for folder_id, entry in folder_entries.items():
                folder_path = scanner.get_folder_path(folder_id)
                if not folder_path:
                    continue
                searcher.schedule_build(folder_id, Path(folder_path))
                result = searcher.search(folder_id, Path(folder_path), q, limit=limit_n)
                total_docs += (result.get('stats') or {}).get('docCount', 0)
                if result.get('ready') is False:
                    ready = False
                for item in result.get('results') or []:
                    item['folder'] = folder_id
                    item['folder_label'] = str(entry.get('name') or folder_id)
                    all_results.append(item)

            all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
            all_results = all_results[:limit_n]
            took_ms = int((time.perf_counter() - t0) * 1000)

            return jsonify({
                'query': q,
                'folder': '',
                'scope': 'all',
                'ready': ready,
                'results': all_results,
                'stats': {'docCount': total_docs, 'tookMs': took_ms}
            })

        # 解析 folder：优先用 query 参数，否则用当前 folder/第一个可用 folder
        folder_to_use = (folder or scanner.current_folder or '').strip()
        if not folder_to_use:
            folder_to_use = _pick_default_folder()
            if folder_to_use:
                scanner.set_folder(folder_to_use)

        if not folder_to_use:
            return jsonify({
                'query': q,
                'folder': '',
                'scope': 'folder',
                'ready': True,
                'results': [],
                'stats': {'docCount': 0, 'tookMs': 0}
            })

        folder_path = scanner.get_folder_path(folder_to_use)
        if not folder_path:
            return jsonify({'error': f'Folder not found: {folder_to_use}'}), 404
        result = searcher.search(folder_to_use, Path(folder_path), q, limit=limit_n)
        for item in result.get('results') or []:
            item['folder'] = folder_to_use
            item['folder_label'] = scanner.get_folder_label(folder_to_use)
        result['scope'] = 'folder'
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/search/prewarm', methods=['GET'])
def prewarm_search_indexes():
    """预热搜索索引（不阻塞），用于减少首次搜索等待时间。

    Query params:
        scope: 'all' | 'folder'（默认 folder）
        folder: 文件夹名称（scope=folder 时可选）
    """
    folder = request.args.get('folder')
    scope = (request.args.get('scope') or 'folder').strip().lower()

    try:
        if scope == 'all':
            folders = _get_folder_entries()
            scheduled = 0
            for entry in folders:
                folder_name = str(entry.get('id') or '')
                folder_path = scanner.get_folder_path(folder_name)
                if not folder_name or not folder_path:
                    continue
                searcher.schedule_build(folder_name, Path(folder_path))
                scheduled += 1
            return jsonify({'success': True, 'scope': 'all', 'scheduled': scheduled})

        folder_to_use = (folder or scanner.current_folder or '').strip()
        if not folder_to_use:
            folder_to_use = _pick_default_folder()
            if folder_to_use:
                scanner.set_folder(folder_to_use)

        if not folder_to_use:
            return jsonify({'success': True, 'scope': 'folder', 'folder': '', 'scheduled': 0})

        folder_path = scanner.get_folder_path(folder_to_use)
        if not folder_path:
            return jsonify({'success': True, 'scope': 'folder', 'folder': folder_to_use, 'scheduled': 0})
        searcher.schedule_build(folder_to_use, Path(folder_path))
        return jsonify({'success': True, 'scope': 'folder', 'folder': folder_to_use, 'scheduled': 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    verbose = (request.args.get('verbose') or '').strip().lower() in {'1', 'true', 'yes'}
    if not verbose:
        return jsonify({'status': 'ok'})

    import sys
    import importlib
    info = {
        'status': 'ok',
        'python': {
            'executable': sys.executable,
            'version': sys.version,
        },
        'modules': {},
    }

    for mod_name in ['app.gemini_batchexecute', 'app.parser', 'app.routes', 'app.scanner']:
        try:
            m = importlib.import_module(mod_name)
            info['modules'][mod_name] = {
                'file': getattr(m, '__file__', None),
            }
        except Exception as e:
            info['modules'][mod_name] = {
                'error': str(e),
            }

    # Expose an explicit parser version string if present.
    try:
        gb = importlib.import_module('app.gemini_batchexecute')
        info['gemini_parser_version'] = getattr(gb, 'PARSER_VERSION', None)
    except Exception:
        info['gemini_parser_version'] = None

    return jsonify(info)


@api.route('/shutdown', methods=['POST'])
def shutdown_server():
    """停止服务（后端 + 前端）。"""
    def _stop_services():
        time.sleep(0.5)
        root_dir = Path(__file__).resolve().parents[2]
        stop_script = root_dir / 'stop.bat'
        if os.name == 'nt' and stop_script.exists():
            try:
                subprocess.Popen(
                    ['cmd', '/c', str(stop_script), '/silent'],
                    cwd=str(root_dir),
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass
        else:
            os._exit(0)

    threading.Thread(target=_stop_services, daemon=True).start()
    return jsonify({'success': True, 'message': '服务将退出'})
