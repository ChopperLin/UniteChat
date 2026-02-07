import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import ConfirmDialog from './ConfirmDialog';
import './SettingsModal.css';

const SOURCE_KINDS = [
  { value: 'auto', label: 'Auto Detect' },
  { value: 'chatgpt', label: 'ChatGPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'gemini', label: 'Gemini' },
];

const MODAL_SIZE_KEY = 'unitechat_settings_modal_size_v1';
const MIN_MODAL_W = 860;
const MIN_MODAL_H = 520;
const MIN_MODAL_W_RATIO = 0.62;
const MIN_MODAL_H_RATIO = 0.58;
const RESIZE_CLOSE_GUARD_MS = 700;

function clampModalSize(size) {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1440;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 900;
  const maxW = Math.max(680, vw - 40);
  const maxH = Math.max(460, vh - 40);
  const desiredMinW = Math.max(MIN_MODAL_W, Math.floor(vw * MIN_MODAL_W_RATIO));
  const desiredMinH = Math.max(MIN_MODAL_H, Math.floor(vh * MIN_MODAL_H_RATIO));
  const minW = Math.min(desiredMinW, maxW);
  const minH = Math.min(desiredMinH, maxH);

  const width = Math.max(minW, Math.min(Number(size?.width || minW), maxW));
  const height = Math.max(minH, Math.min(Number(size?.height || minH), maxH));
  return { width: Math.round(width), height: Math.round(height) };
}

function getDefaultModalSize() {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1440;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 900;
  return clampModalSize({
    width: Math.min(1480, Math.floor(vw * 0.96)),
    height: Math.min(920, Math.floor(vh * 0.95)),
  });
}

function normalizeSources(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x) => x && typeof x === 'object')
    .map((x) => ({
      id: String(x.id || '').trim(),
      name: String(x.name || '').trim(),
      path: String(x.path || '').trim(),
      kind: String(x.kind || 'auto').trim().toLowerCase() || 'auto',
      enabled: x.enabled !== false,
      exists: Boolean(x.exists),
      resolved_path: String(x.resolved_path || ''),
      matched_paths: Array.isArray(x.matched_paths) ? x.matched_paths : [],
    }));
}

function splitPathParts(rawPath) {
  const text = String(rawPath || '').trim();
  if (!text) return [];
  const normalized = text.replace(/[\\/]+/g, '/').replace(/\/+$/g, '');
  if (!normalized) return [];
  return normalized.split('/').filter(Boolean);
}

function inferRootFromSources(rows) {
  const paths = (Array.isArray(rows) ? rows : [])
    .map((r) => String(r?.resolved_path || '').trim())
    .filter(Boolean);
  if (!paths.length) return '';

  const parentParts = paths
    .map((p) => {
      const parts = splitPathParts(p);
      return parts.length > 1 ? parts.slice(0, -1) : parts;
    })
    .filter((parts) => parts.length > 0);

  if (!parentParts.length) return '';

  let prefix = [...parentParts[0]];
  for (let i = 1; i < parentParts.length; i += 1) {
    const cur = parentParts[i];
    const maxLen = Math.min(prefix.length, cur.length);
    let j = 0;
    while (j < maxLen) {
      const left = j === 0 ? String(prefix[j] || '').toLowerCase() : String(prefix[j] || '');
      const right = j === 0 ? String(cur[j] || '').toLowerCase() : String(cur[j] || '');
      if (left !== right) break;
      j += 1;
    }
    prefix = prefix.slice(0, j);
    if (!prefix.length) break;
  }

  if (!prefix.length) return '';
  const isWindowsDrive = /^[A-Za-z]:$/.test(prefix[0] || '');
  if (isWindowsDrive && prefix.length === 1) return `${prefix[0]}\\`;
  const joined = prefix.join('/');
  return isWindowsDrive ? joined.replace(/\//g, '\\') : joined;
}

export default function SettingsModal({ open, onClose, currentFolder, onSaved }) {
  const [activeTab, setActiveTab] = useState('sources');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [sources, setSources] = useState([]);
  const [query, setQuery] = useState('');
  const [rootImportPath, setRootImportPath] = useState('');
  const [pickingRoot, setPickingRoot] = useState(false);
  const [importingRoot, setImportingRoot] = useState(false);
  const [rowActionBusy, setRowActionBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState({ open: false, source: null, index: -1 });
  const [modalSize, setModalSize] = useState(() => getDefaultModalSize());
  const [isResizing, setIsResizing] = useState(false);
  const resizeStateRef = useRef(null);
  const latestSizeRef = useRef(modalSize);
  const suppressBackdropCloseUntilRef = useRef(0);
  const backdropPressedRef = useRef(false);

  const canSave = useMemo(
    () => !saving && !loading && !importingRoot && !pickingRoot && !rowActionBusy,
    [saving, loading, importingRoot, pickingRoot, rowActionBusy]
  );

  const filteredRows = useMemo(() => {
    const q = String(query || '').trim().toLowerCase();
    const rows = sources.map((src, idx) => ({ src, idx }));
    if (!q) return rows;
    return rows.filter(({ src }) => {
      const name = String(src.name || '').toLowerCase();
      const kind = String(src.kind || '').toLowerCase();
      return name.includes(q) || kind.includes(q);
    });
  }, [sources, query]);

  useEffect(() => {
    if (!open) return;
    setActiveTab('sources');
    setLoading(true);
    setError('');
    setInfo('');
    setQuery('');
    setIsResizing(false);
    setDeleteTarget({ open: false, source: null, index: -1 });

    try {
      const raw = localStorage.getItem(MODAL_SIZE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setModalSize(clampModalSize(parsed));
      } else {
        setModalSize(getDefaultModalSize());
      }
    } catch {
      setModalSize(getDefaultModalSize());
    }

    axios.get('/api/settings/sources')
      .then((res) => {
        const data = res?.data || {};
        const normalized = normalizeSources(data?.sources);
        setSources(normalized);
        const root = String(data?.root || '').trim() || inferRootFromSources(normalized);
        if (root) setRootImportPath(root);
      })
      .catch((e) => {
        setError(e?.response?.data?.error || e?.message || '加载设置失败');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose?.();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const onResize = () => {
      setModalSize((prev) => clampModalSize(prev));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open]);

  useEffect(() => {
    latestSizeRef.current = modalSize;
  }, [modalSize]);

  const updateSource = (index, patch) => {
    setSources((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  const pickFolder = async (title = '选择目录') => {
    const res = await axios.post('/api/settings/sources/pick-root', {
      initial: String(rootImportPath || '').trim(),
      title,
    });
    return String(res?.data?.selected || '').trim();
  };

  const removeSource = (index) => {
    setSources((prev) => prev.filter((_, i) => i !== index));
  };

  const requestDeleteSource = (src, index) => {
    if (!src?.id) {
      removeSource(index);
      return;
    }
    setDeleteTarget({ open: true, source: src, index });
  };

  const confirmDeleteSource = async () => {
    const src = deleteTarget?.source;
    if (!src?.id) {
      setDeleteTarget({ open: false, source: null, index: -1 });
      return;
    }
    setRowActionBusy(true);
    setError('');
    setInfo('');
    try {
      const res = await axios.post(
        `/api/settings/sources/${encodeURIComponent(src.id)}/delete`,
        { delete_dir: true }
      );
      const data = res?.data || {};
      setSources(normalizeSources(data.sources));
      const nextRoot = String(data?.root || '').trim() || inferRootFromSources(data?.sources);
      if (nextRoot) setRootImportPath(nextRoot);
      setInfo(`目录已删除：${src.name || src.id}`);
      onSaved?.({ ...data, keep_open: true });
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || '删除目录失败');
    } finally {
      setRowActionBusy(false);
      setDeleteTarget({ open: false, source: null, index: -1 });
    }
  };

  const handleRootImport = async (rootOverride = '') => {
    const root = String(rootOverride || rootImportPath || '').trim();
    if (!root) {
      setError('请先选择数据根目录');
      return;
    }

    setImportingRoot(true);
    setError('');
    setInfo('');
    try {
      const res = await axios.post('/api/settings/sources/import-root', {
        root,
      });
      const data = res?.data || {};
      const detected = data?.detected || {};
      const normalized = normalizeSources(data.sources);
      setSources(normalized);
      const nextRoot = String(data?.root || '').trim() || inferRootFromSources(normalized) || root;
      if (nextRoot) setRootImportPath(nextRoot);
      setInfo(
        `扫描 ${data.scanned || 0}，识别 ${data.matched || 0}，新增 ${data.imported || 0}，跳过 ${data.skipped || 0}（GPT ${detected.chatgpt || 0} / Claude ${detected.claude || 0} / Gemini ${detected.gemini || 0}）`
      );
      onSaved?.({ ...data, keep_open: true });
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || '子目录批量导入失败');
    } finally {
      setImportingRoot(false);
    }
  };

  const handlePickRoot = async () => {
    setPickingRoot(true);
    setError('');
    try {
      const selected = await pickFolder('选择数据根目录');
      if (!selected) return;
      setRootImportPath(selected);
      await handleRootImport(selected);
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || '打开目录选择器失败');
    } finally {
      setPickingRoot(false);
    }
  };

  const handleSave = async () => {
    const payloadSources = sources.map((s) => ({
      id: String(s.id || '').trim() || undefined,
      name: String(s.name || '').trim(),
      path: String(s.path || '').trim(),
      kind: String(s.kind || 'auto').trim().toLowerCase() || 'auto',
      enabled: Boolean(s.enabled),
    }));

    const validCount = payloadSources.filter((s) => s.path).length;
    if (validCount === 0) {
      setError('至少需要一个有效目录路径。');
      return;
    }

    setSaving(true);
    setError('');
    setInfo('');
    try {
      const res = await axios.put('/api/settings/sources', {
        sources: payloadSources,
        current: currentFolder || '',
      });
      const data = res?.data || {};
      const normalized = normalizeSources(data.sources || sources);
      const nextRoot = String(data?.root || '').trim() || inferRootFromSources(normalized);
      if (nextRoot) setRootImportPath(nextRoot);
      onSaved?.({ ...data, keep_open: false });
      setInfo('保存成功');
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleFitScreen = () => {
    const size = getDefaultModalSize();
    setModalSize(size);
    try {
      localStorage.setItem(MODAL_SIZE_KEY, JSON.stringify(size));
    } catch {
      // ignore
    }
  };

  const beginResize = (event) => {
    if (!open) return;
    event.preventDefault();
    event.stopPropagation();
    suppressBackdropCloseUntilRef.current = Date.now() + 1000;
    const startX = Number(event.clientX || 0);
    const startY = Number(event.clientY || 0);
    resizeStateRef.current = {
      startX,
      startY,
      startW: modalSize.width,
      startH: modalSize.height,
    };
    setIsResizing(true);

    const prevUserSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'nwse-resize';

    const onMove = (moveEvent) => {
      const s = resizeStateRef.current;
      if (!s) return;
      const next = clampModalSize({
        width: s.startW + (Number(moveEvent.clientX || 0) - s.startX),
        height: s.startH + (Number(moveEvent.clientY || 0) - s.startY),
      });
      setModalSize(next);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      resizeStateRef.current = null;
      setIsResizing(false);
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;
      suppressBackdropCloseUntilRef.current = Date.now() + RESIZE_CLOSE_GUARD_MS;
      try {
        localStorage.setItem(MODAL_SIZE_KEY, JSON.stringify(clampModalSize(latestSizeRef.current)));
      } catch {
        // ignore
      }
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
    window.addEventListener('pointercancel', onUp, { once: true });
  };

  if (!open) return null;

  return (
    <div
      className="settings-overlay"
      onPointerDown={(e) => {
        backdropPressedRef.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        if (!backdropPressedRef.current) return;
        if (isResizing) return;
        if (Date.now() < Number(suppressBackdropCloseUntilRef.current || 0)) return;
        backdropPressedRef.current = false;
        onClose?.();
      }}
    >
      <div
        className={`settings-shell ${isResizing ? 'is-resizing' : ''}`}
        onClick={(e) => e.stopPropagation()}
        style={{ width: `${modalSize.width}px`, height: `${modalSize.height}px` }}
      >
        <aside className="settings-side">
          <div className="settings-title">Settings</div>
          <button
            type="button"
            className={`settings-side-item ${activeTab === 'sources' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('sources')}
          >
            Data Sources
          </button>
          <button
            type="button"
            className={`settings-side-item ${activeTab === 'general' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            General
          </button>
        </aside>

        <section className="settings-main">
          <header className="settings-main-header">
            <h2>{activeTab === 'sources' ? 'Data Sources' : 'General'}</h2>
            <div className="settings-main-actions">
              <button type="button" className="settings-btn subtle" onClick={handleFitScreen}>
                Fit
              </button>
              <button type="button" className="settings-btn subtle" onClick={onClose}>
                Close
              </button>
              {activeTab === 'sources' && (
                <button type="button" className="settings-btn" onClick={handleSave} disabled={!canSave}>
                  {saving ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
          </header>

          {error && <div className="settings-error">{error}</div>}
          {!error && info && <div className="settings-info">{info}</div>}

          {activeTab === 'general' && (
            <div className="settings-placeholder">
              <p>当前版本重点是数据源配置。后续可在这里扩展通用行为。</p>
            </div>
          )}

          {activeTab === 'sources' && (
            <div className="settings-content">
              <div className="settings-quick-import">
                <label>Data Path</label>
                <div className="settings-quick-import-row">
                  <input
                    className="readonly-path"
                    value={rootImportPath}
                    readOnly
                    tabIndex={-1}
                    placeholder="未选择目录"
                    title={rootImportPath || '未选择目录'}
                  />
                  <button
                    type="button"
                    className="settings-btn choose-root"
                    onClick={handlePickRoot}
                    disabled={pickingRoot || importingRoot || loading || saving}
                  >
                    {pickingRoot ? 'Opening...' : importingRoot ? 'Scanning...' : 'Choose Folder'}
                  </button>
                </div>
              </div>

              <div className="settings-toolbar">
                <input
                  className="settings-search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索 Name / Type"
                />
                <span className="settings-count">
                  显示 {filteredRows.length} / {sources.length}
                </span>
              </div>

              {loading ? (
                <div className="settings-loading">Loading...</div>
              ) : (
                <div className="source-grid-scroll">
                  <div className="source-grid">
                    <div className="source-grid-head">
                      <span>On</span>
                      <span>Name</span>
                      <span>Type</span>
                      <span>Action</span>
                    </div>
                    {filteredRows.map(({ src, idx }) => (
                      <div key={`${src.id || 'new'}-${idx}`} className="source-grid-row">
                        <label className="source-switch compact">
                          <input
                            type="checkbox"
                            checked={Boolean(src.enabled)}
                            onChange={(e) => updateSource(idx, { enabled: e.target.checked })}
                          />
                        </label>

                        <input
                          value={src.name}
                          onChange={(e) => updateSource(idx, { name: e.target.value })}
                          placeholder="name"
                        />

                        <select
                          value={src.kind || 'auto'}
                          onChange={(e) => updateSource(idx, { kind: e.target.value })}
                        >
                          {SOURCE_KINDS.map((kind) => (
                            <option key={kind.value} value={kind.value}>
                              {kind.label}
                            </option>
                          ))}
                        </select>

                        <div className="row-actions">
                          <button
                            type="button"
                            className="settings-btn danger tiny"
                            onClick={() => requestDeleteSource(src, idx)}
                            disabled={rowActionBusy || saving || importingRoot || pickingRoot || loading}
                            title={src?.id ? '删除磁盘目录并移除数据源' : '移除未保存行'}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
        <div className="settings-resize-handle" onPointerDown={beginResize} title="Drag to resize" />
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget?.open)}
        title="删除目录？"
        message={`将永久删除目录及其全部聊天文件：${deleteTarget?.source?.resolved_path || deleteTarget?.source?.path || ''}。此操作不可恢复。`}
        confirmLabel="删除目录"
        cancelLabel="取消"
        danger
        busy={rowActionBusy}
        onCancel={() => setDeleteTarget({ open: false, source: null, index: -1 })}
        onConfirm={confirmDeleteSource}
      />
    </div>
  );
}
