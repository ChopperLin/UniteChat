import React, { useMemo, useState } from 'react';
import ThinkingBlock from './ThinkingBlock';
import MarkdownContent from './MarkdownContent';
import CollapsibleContent from './CollapsibleContent';

function MessageItem({ message }) {
  const { role } = message;

  const [hovered, setHovered] = useState(false);

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
      <div style={{
        display: 'flex',
        gap: '18px',
        marginBottom: '32px',
        maxWidth: '100%',
        alignItems: 'flex-start'
      }}>
        {/* User Avatar - Claude Style: Professional user icon */}
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #5D5449 0%, #4A443A 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 2px 4px rgba(42, 37, 35, 0.15)'
        }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="10" cy="7" r="3.5" fill="#FFFFFF" opacity="0.9"/>
            <path d="M4 17C4 13.5 6.5 11 10 11C13.5 11 16 13.5 16 17" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" opacity="0.9"/>
          </svg>
        </div>
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: 'relative',
            flex: 1,
            minWidth: 0,
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
    );
  }

  // Assistant 消息 - Claude风格
  return (
    <div style={{
      display: 'flex',
      gap: '18px',
      marginBottom: '32px',
      maxWidth: '100%',
      alignItems: 'flex-start'
    }}>
      {/* AI Avatar - Claude Style: Professional AI sparkle icon */}
      <div style={{
        width: '36px',
        height: '36px',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #CC9966 0%, #B8835A 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        boxShadow: '0 2px 4px rgba(42, 37, 35, 0.15)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Subtle gradient overlay */}
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.15) 0%, transparent 60%)',
          pointerEvents: 'none'
        }}></div>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Sparkle/star icon representing AI intelligence */}
          <path d="M10 2L10.9 6.8L13 4.5L11.5 9L16 8L12 10L16 12L11.5 11L13 15.5L10.9 13.2L10 18L9.1 13.2L7 15.5L8.5 11L4 12L8 10L4 8L8.5 9L7 4.5L9.1 6.8L10 2Z" fill="#FFFFFF" opacity="0.95"/>
        </svg>
      </div>
      <div style={{ 
        flex: 1,
        minWidth: 0,
        maxWidth: '100%'
      }}>
        {/* 思考过程 */}
        {(message.thinking || message.thinking_summary || message.thinking_duration) && (
          <ThinkingBlock
            thinking={message.thinking}
            thinkingSummary={message.thinking_summary}
            thinkingDuration={message.thinking_duration}
          />
        )}

        {/* 回复内容 - Claude风格卡片 */}
        {message.content && (
          <div
            style={{
              background: '#FDFBF9',
              padding: '22px 24px',
              borderRadius: '14px',
              border: '1px solid #E5E0DB',
              marginTop: (message.thinking || message.thinking_summary || message.thinking_duration) ? '12px' : '0',
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

export default MessageItem;
