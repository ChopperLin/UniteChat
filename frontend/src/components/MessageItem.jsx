import React, { useMemo, useState } from 'react';
import ThinkingBlock from './ThinkingBlock';
import CollapsibleContent from './CollapsibleContent';

function MessageItem({ message }) {
  const { role } = message;

  const [hovered, setHovered] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasThinking = Boolean(message?.thinking || message?.thinking_summary || message?.thinking_duration);

  const copyToClipboard = async (text) => {
    const s = (text == null) ? '' : String(text);
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(s);
      } else {
        const ta = document.createElement('textarea');
        ta.value = s;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 900);
    } catch (e) {
      console.error('copy failed', e);
    }
  };

  const CopyButton = ({ onClick }) => (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (typeof onClick === 'function') onClick();
      }}
      style={{
        width: '30px',
        height: '30px',
        borderRadius: '10px',
        border: '1px solid rgba(229, 224, 219, 0.95)',
        background: 'rgba(255, 255, 255, 0.92)',
        boxShadow: '0 1px 3px rgba(42, 37, 35, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        opacity: hovered ? 1 : 0,
        transform: hovered ? 'translateY(0)' : 'translateY(-2px)',
        transition: 'opacity 0.12s ease, transform 0.12s ease, background-color 0.08s',
        pointerEvents: hovered ? 'auto' : 'none'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = '#FFFFFF';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.92)';
      }}
      title={copied ? '已复制' : '复制'}
      aria-label="复制"
    >
      {copied ? (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3.2 8.4L6.3 11.4L12.8 4.9" stroke="#2A2523" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="5" y="5" width="9" height="9" rx="2" stroke="#2A2523" strokeWidth="1.4"/>
          <path d="M3 11V4.8C3 3.805 3.805 3 4.8 3H11" stroke="#2A2523" strokeWidth="1.4" strokeLinecap="round"/>
        </svg>
      )}
    </button>
  );

  const ts = message?.ts;
  const dateLabel = useMemo(() => {
    if (!ts) return '';
    const ms = Number(ts) * 1000;
    if (!Number.isFinite(ms)) return '';
    const d = new Date(ms);
    const y = d.getFullYear();
    const m = d.getMonth() + 1;
    const day = d.getDate();
    return `${y}年${m}月${day}日`;
  }, [ts]);

  const fullLabel = useMemo(() => {
    if (!ts) return '';
    const ms = Number(ts) * 1000;
    if (!Number.isFinite(ms)) return '';
    const d = new Date(ms);
    // Include time in tooltip; visible label shows only Y/M/D.
    return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  }, [ts]);

  const TimestampPill = ({ align = 'right' }) => {
    if (!dateLabel) return null;
    return (
      <div
        title={fullLabel}
        style={{
          position: 'absolute',
          bottom: '-18px',
          [align]: 0,
          fontSize: '12px',
          color: '#8A7F76',
          opacity: hovered ? 1 : 0,
          transform: hovered ? 'translateY(0)' : 'translateY(-2px)',
          transition: 'opacity 0.15s ease, transform 0.15s ease',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
          padding: '2px 6px',
          borderRadius: '999px',
          background: 'rgba(255, 255, 255, 0.75)',
          border: '1px solid rgba(229, 224, 219, 0.9)',
          boxShadow: '0 1px 2px rgba(42, 37, 35, 0.04)'
        }}
      >
        {dateLabel}
      </div>
    );
  };

  if (role === 'user') {
    return (
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
        display: 'flex',
        gap: '18px',
        marginBottom: '32px',
        maxWidth: '100%',
        alignItems: 'flex-start'
      }}>
        {/* User Avatar - Claude Style: Professional user icon */}
        <div style={{ position: 'relative', width: '36px', flexShrink: 0 }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #5D5449 0%, #4A443A 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 4px rgba(42, 37, 35, 0.15)'
          }}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="10" cy="7" r="3.5" fill="#FFFFFF" opacity="0.9"/>
              <path d="M4 17C4 13.5 6.5 11 10 11C13.5 11 16 13.5 16 17" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" opacity="0.9"/>
            </svg>
          </div>

          {/* Copy button (below avatar, never overlaps avatar) */}
          <div style={{
            position: 'absolute',
            top: '46px',
            left: '50%',
            transform: 'translateX(-50%)'
          }}>
            <CopyButton onClick={() => copyToClipboard(message?.content)} />
          </div>
        </div>

        {/* Bubble + copy button (outside, left) */}
        <div
          style={{ position: 'relative', flex: 1, minWidth: 0, overflow: 'visible' }}
        >
          <div
            style={{
              position: 'relative',
              background: '#E8E3DB',
              padding: '16px 20px',
              borderRadius: '14px',
              fontSize: '15.5px',
              lineHeight: '1.7',
              color: '#2A2523',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              overflowWrap: 'break-word',
              border: '1px solid #DCD7CF',
              boxShadow: '0 1px 2px rgba(42, 37, 35, 0.04)'
            }}
          >
            <CollapsibleContent 
              content={message.content} 
              isMarkdown={false} 
              gradientColor="#E8E3DB"
            />
            <TimestampPill align="right" />
          </div>
        </div>
      </div>
    );
  }

  // Assistant 消息 - Claude风格
  if (!hasThinking) {
    return (
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: 'flex',
          gap: '18px',
          marginBottom: '32px',
          maxWidth: '100%',
          alignItems: 'flex-start'
        }}
      >
        {/* AI Avatar */}
        <div style={{ position: 'relative', width: '36px', flexShrink: 0 }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #CC9966 0%, #B8835A 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 4px rgba(42, 37, 35, 0.15)',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <div style={{
              position: 'absolute',
              inset: 0,
              background: 'radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.15) 0%, transparent 60%)',
              pointerEvents: 'none'
            }}></div>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 2L10.9 6.8L13 4.5L11.5 9L16 8L12 10L16 12L11.5 11L13 15.5L10.9 13.2L10 18L9.1 13.2L7 15.5L8.5 11L4 12L8 10L4 8L8.5 9L7 4.5L9.1 6.8L10 2Z" fill="#FFFFFF" opacity="0.95"/>
            </svg>
          </div>

          {/* Copy button (below avatar, never overlaps avatar) */}
          {message?.content && (
            <div style={{
              position: 'absolute',
              top: '46px',
              left: '50%',
              transform: 'translateX(-50%)'
            }}>
              <CopyButton onClick={() => copyToClipboard(message?.content)} />
            </div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0, maxWidth: '100%' }}>
          {/* 回复内容 - Claude风格卡片 */}
          {message.content && (
            <div
              style={{
                position: 'relative',
                background: '#FDFBF9',
                padding: '22px 24px',
                borderRadius: '14px',
                border: '1px solid #E5E0DB',
                overflowX: 'auto',
                overflowY: 'visible',
                boxShadow: '0 1px 3px rgba(42, 37, 35, 0.04)'
              }}
            >
              <CollapsibleContent 
                content={message.content} 
                isMarkdown={true} 
                gradientColor="#FDFBF9"
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '36px 1fr',
        columnGap: '18px',
        rowGap: '12px',
        marginBottom: '32px',
        maxWidth: '100%',
        alignItems: 'start'
      }}
    >
      {/* AI Avatar */}
      <div style={{
        gridColumn: '1',
        gridRow: '1',
        width: '36px',
        height: '36px',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #CC9966 0%, #B8835A 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 2px 4px rgba(42, 37, 35, 0.15)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.15) 0%, transparent 60%)',
          pointerEvents: 'none'
        }}></div>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M10 2L10.9 6.8L13 4.5L11.5 9L16 8L12 10L16 12L11.5 11L13 15.5L10.9 13.2L10 18L9.1 13.2L7 15.5L8.5 11L4 12L8 10L4 8L8.5 9L7 4.5L9.1 6.8L10 2Z" fill="#FFFFFF" opacity="0.95"/>
        </svg>
      </div>

      {/* Thinking row */}
      {hasThinking && (
        <div style={{ gridColumn: '2', gridRow: '1', minWidth: 0 }}>
          <ThinkingBlock
            thinking={message.thinking}
            thinkingSummary={message.thinking_summary}
            thinkingDuration={message.thinking_duration}
          />
        </div>
      )}

      {/* Copy button aligned to response row (never above response) */}
      {message?.content && (
        <div style={{
          gridColumn: '1',
          gridRow: hasThinking ? '2' : '1',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-start',
          paddingTop: '10px'
        }}>
          <CopyButton onClick={() => copyToClipboard(message?.content)} />
        </div>
      )}

      {/* Response bubble */}
      {message.content && (
        <div style={{ gridColumn: '2', gridRow: hasThinking ? '2' : '1', minWidth: 0 }}>
          <div
            style={{
              position: 'relative',
              background: '#FDFBF9',
              padding: '22px 24px',
              borderRadius: '14px',
              border: '1px solid #E5E0DB',
              overflowX: 'auto',
              overflowY: 'visible',
              boxShadow: '0 1px 3px rgba(42, 37, 35, 0.04)'
            }}
          >
            <CollapsibleContent 
              content={message.content} 
              isMarkdown={true} 
              gradientColor="#FDFBF9"
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default MessageItem;
