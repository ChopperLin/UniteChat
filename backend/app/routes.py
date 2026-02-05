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
from config import Config

api = Blueprint('api', __name__)


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
        folders = scanner.get_available_folders()

        # 设定默认 folder（与前端默认逻辑一致），并尽早预热搜索索引
        if (not scanner.current_folder) and folders:
            scanner.set_folder(folders[0])

        if scanner.current_folder:
            searcher.schedule_build(scanner.current_folder, Config.DATA_ROOT_PATH / scanner.current_folder)

        return jsonify({
            'folders': folders,
            'current': scanner.current_folder
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
            searcher.schedule_build(folder_name, Config.DATA_ROOT_PATH / folder_name)
            return jsonify({'success': True, 'folder': folder_name})
        else:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
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
        scanner.clear_cache()
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
            searcher.schedule_build(folder_to_index, Config.DATA_ROOT_PATH / folder_to_index)

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
                ov = get_override(Config.DATA_ROOT_PATH / src.folder, f"claude:{chat_id}") or {}
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
            root = Path(Config.DATA_ROOT_PATH).resolve()
            if root not in old_path.parents:
                return jsonify({'error': 'invalid path'}), 400

            new_path = old_path.with_name(f"{new_title}_{chat_id}{old_path.suffix}")
            if new_path.exists() and new_path != old_path:
                return jsonify({'error': 'a conversation with the same title already exists'}), 409

            if new_path != old_path:
                old_path.rename(new_path)
        elif src.kind == 'claude':
            # Persist rename into overrides file; do not mutate the original export JSON.
            set_override(Config.DATA_ROOT_PATH / src.folder, f"claude:{chat_id}", {"title": new_title, "deleted": False})
        else:
            return jsonify({'error': f'Unsupported rename source: {src.kind}'}), 400

        scanner.clear_cache()
        folder_to_index = folder or scanner.current_folder
        if folder_to_index:
            searcher.invalidate(folder_to_index)
        if folder_to_index:
            searcher.schedule_build(folder_to_index, Config.DATA_ROOT_PATH / folder_to_index)

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
            root = Path(Config.DATA_ROOT_PATH).resolve()
            if root not in p.parents:
                return jsonify({'error': 'invalid path'}), 400

            if p.exists():
                p.unlink()
        elif src.kind == 'claude':
            # Persist delete as a hide flag.
            set_override(Config.DATA_ROOT_PATH / src.folder, f"claude:{chat_id}", {"deleted": True})
        else:
            return jsonify({'error': f'Unsupported delete source: {src.kind}'}), 400

        scanner.clear_cache()

        folder_to_index = folder or scanner.current_folder
        if folder_to_index:
            searcher.invalidate(folder_to_index)
        if folder_to_index:
            searcher.schedule_build(folder_to_index, Config.DATA_ROOT_PATH / folder_to_index)

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

    folder_root = (Config.DATA_ROOT_PATH / folder).resolve()
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
        if str(scope).lower() == 'all':
            folders = scanner.get_available_folders()
            if not folders:
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

            for folder_name in folders:
                folder_path = Config.DATA_ROOT_PATH / folder_name
                searcher.schedule_build(folder_name, folder_path)
                result = searcher.search(folder_name, folder_path, q, limit=int(limit or 50))
                total_docs += (result.get('stats') or {}).get('docCount', 0)
                if result.get('ready') is False:
                    ready = False
                for item in result.get('results') or []:
                    item['folder'] = folder_name
                    all_results.append(item)

            all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
            all_results = all_results[:max(1, min(int(limit or 50), 200))]
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
            folders = scanner.get_available_folders()
            folder_to_use = folders[0] if folders else ''
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

        folder_path = Config.DATA_ROOT_PATH / folder_to_use
        result = searcher.search(folder_to_use, folder_path, q, limit=int(limit or 50))
        for item in result.get('results') or []:
            item['folder'] = folder_to_use
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
            folders = scanner.get_available_folders()
            for folder_name in folders:
                folder_path = Config.DATA_ROOT_PATH / folder_name
                searcher.schedule_build(folder_name, folder_path)
            return jsonify({'success': True, 'scope': 'all', 'scheduled': len(folders)})

        folder_to_use = (folder or scanner.current_folder or '').strip()
        if not folder_to_use:
            folders = scanner.get_available_folders()
            folder_to_use = folders[0] if folders else ''
            if folder_to_use:
                scanner.set_folder(folder_to_use)

        if not folder_to_use:
            return jsonify({'success': True, 'scope': 'folder', 'folder': '', 'scheduled': 0})

        folder_path = Config.DATA_ROOT_PATH / folder_to_use
        searcher.schedule_build(folder_to_use, folder_path)
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
