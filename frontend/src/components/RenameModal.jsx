import React, { useEffect, useMemo, useRef, useState } from 'react';

export default function RenameModal({
  open,
  initialTitle,
  onClose,
  onSubmit,
}) {
  const [title, setTitle] = useState('');
  const [err, setErr] = useState('');
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);

  const titleTrim = useMemo(() => title.trim(), [title]);

  useEffect(() => {
    if (!open) return;
    setTitle(String(initialTitle || ''));
    setErr('');
    setSaving(false);

    const raf = requestAnimationFrame(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [open, initialTitle]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose?.();
        return;
      }
      if (e.key === 'Enter') {
        if (e.target !== inputRef.current) return;
        e.preventDefault();
        handleSubmit();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, titleTrim]);

  const handleSubmit = async () => {
    if (saving) return;
    if (!titleTrim) {
      setErr('标题不能为空');
      return;
    }

    setErr('');
    setSaving(true);
    try {
      await onSubmit?.(titleTrim);
      onClose?.();
    } catch (e) {
      setErr(e?.message || '重命名失败');
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(26, 23, 21, 0.35)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2000,
        padding: '24px',
        boxSizing: 'border-box'
      }}
    >
      <div
        style={{
          width: 'min(520px, 92vw)',
          background: '#FFFFFF',
          borderRadius: '16px',
          border: '1px solid rgba(229, 224, 219, 0.95)',
          boxShadow: '0 20px 60px rgba(42, 37, 35, 0.22)',
          padding: '18px 18px 14px',
          boxSizing: 'border-box'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <div style={{ fontSize: '15px', fontWeight: '800', color: '#2A2523' }}>重命名对话</div>
          <button
            onClick={() => onClose?.()}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              color: '#6B615B',
              fontSize: '18px',
              lineHeight: 1,
              padding: '6px 8px',
              borderRadius: '10px'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(42, 37, 35, 0.06)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
            }}
            title="关闭 (Esc)"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div style={{ marginTop: '12px' }}>
          <input
            ref={inputRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="输入新标题"
            style={{
              width: '100%',
              padding: '12px 12px',
              borderRadius: '12px',
              border: '1px solid #D8CBBE',
              fontSize: '14px',
              outline: 'none',
              boxSizing: 'border-box'
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = '#A89B8F';
              e.currentTarget.style.boxShadow = '0 0 0 3px rgba(168, 155, 143, 0.18)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = '#D8CBBE';
              e.currentTarget.style.boxShadow = 'none';
            }}
          />
          {err ? (
            <div style={{ marginTop: '10px', color: '#8B2E1F', fontSize: '13px', fontWeight: '600' }}>{err}</div>
          ) : (
            <div style={{ marginTop: '10px', color: '#8A7F76', fontSize: '12.5px' }}>回车保存，Esc 取消</div>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
          <button
            onClick={() => onClose?.()}
            disabled={saving}
            style={{
              border: '1px solid #E5E0DB',
              background: '#FFFFFF',
              padding: '10px 14px',
              borderRadius: '12px',
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: '13.5px',
              color: '#2A2523',
              fontWeight: '700',
              opacity: saving ? 0.6 : 1
            }}
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            style={{
              border: '1px solid #D4C4B0',
              background: saving ? '#EEE7DF' : '#F2EDE7',
              padding: '10px 14px',
              borderRadius: '12px',
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: '13.5px',
              color: '#2A2523',
              fontWeight: '800',
              boxShadow: '0 1px 2px rgba(42, 37, 35, 0.06)',
              opacity: saving ? 0.8 : 1
            }}
            title="保存 (Enter)"
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

