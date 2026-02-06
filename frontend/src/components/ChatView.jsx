import React from 'react';
import MessageItem from './MessageItem';

function ChatView({ chatData, loading, onOpenSearch, onShutdown, shuttingDown }) {

  const meta = chatData?.meta;
  const modelSlug = (meta?.model_slug || '').trim();
  const thinkingEffort = (meta?.thinking_effort || '').trim();
  const thinkingLabel = thinkingEffort ? (thinkingEffort === 'extended' ? 'extended' : thinkingEffort) : 'normal';

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--bg-base)',
      minWidth: 0,
      overflow: 'hidden'
    }}>
      {/* 标题 - Claude风格 */}
      <div style={{
        height: '64px',
        padding: '0 24px',
        borderBottom: '1px solid #E5E0DB',
        background: '#FDFBF9',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        boxSizing: 'border-box'
      }}>
        <h2 style={{ 
          fontSize: '19px', 
          fontWeight: '540', 
          color: 'var(--text-strong)', 
          margin: 0,
          minWidth: 0,
          letterSpacing: '-0.012em',
          lineHeight: 1.2,
          display: 'flex',
          alignItems: 'center',
          fontFamily: 'var(--font-reading)'
        }}>
          <span style={{ display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {chatData?.title || 'UniteChat'}
          </span>
        </h2>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
          <button
            onClick={onOpenSearch}
            style={{
              border: '1px solid #E5E0DB',
              background: '#FDFBF9',
              padding: '8px 12px',
              borderRadius: '10px',
              cursor: 'pointer',
              fontSize: '13.5px',
              lineHeight: 1.2,
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              flexShrink: 0,
              fontWeight: '500',
              transition: 'background-color 0.08s, border-color 0.08s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#F4EFE8';
              e.currentTarget.style.borderColor = '#D4C4B0';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = '#FDFBF9';
              e.currentTarget.style.borderColor = '#E5E0DB';
            }}
            title="搜索 (Ctrl+K / Ctrl+F)"
          >
            <svg 
              width="16" 
              height="16" 
              viewBox="0 0 16 16" 
              fill="none"
              style={{ opacity: 0.6 }}
            >
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M10.5 10.5L13.5 13.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
            <span>搜索</span>
            <kbd style={{
              padding: '3px 7px',
              background: '#F2EDE7',
              border: '1px solid #DCD7CF',
              borderRadius: '5px',
              fontSize: '11px',
              color: '#5A504A',
              fontFamily: 'monospace',
              fontWeight: '600',
              marginLeft: '2px'
            }}>
              ⌘K
            </kbd>
          </button>

          <button
            onClick={onShutdown}
            style={{
              border: '1px solid #E5E0DB',
              background: '#FDF7F6',
              padding: '8px 12px',
              borderRadius: '10px',
              cursor: 'pointer',
              fontSize: '13.5px',
              lineHeight: 1.2,
              color: '#7A3C31',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontWeight: '560',
              transition: 'background-color 0.08s, border-color 0.08s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#FBEDE9';
              e.currentTarget.style.borderColor = '#E3B8AE';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = '#FDF7F6';
              e.currentTarget.style.borderColor = '#E5E0DB';
            }}
            title="退出并停止服务"
          >
            <span>退出</span>
          </button>
        </div>
      </div>

      {/* 消息列表 - Claude风格 */}
      {shuttingDown ? (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '17px',
          color: '#8A7F76',
          fontWeight: '500'
        }}>
          正在退出并停止服务...
        </div>
      ) : loading ? (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '17px',
          color: '#8A7F76',
          fontWeight: '500'
        }}>
          加载中...
        </div>
      ) : !chatData ? (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '17px',
          color: '#A89B8F',
          background: 'var(--bg-base)',
          fontWeight: '400'
        }}>
          ← 选择一个对话查看（或点右上角搜索）
        </div>
      ) : (
        <>
          {/* 对话元信息栏：显示模型与推理强度 */}
          <div style={{
            padding: '8px 24px',
            background: 'var(--bg-base)',
            borderBottom: '1px solid #E5E0DB',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            color: '#5A504A',
            fontSize: '12.5px'
          }}>
            <span style={{
              padding: '3px 8px',
              borderRadius: '999px',
              background: '#FFFFFF',
              border: '1px solid #E5E0DB',
              fontWeight: '560',
              color: 'var(--text-main)'
            }}>
              {modelSlug ? `Model: ${modelSlug}` : 'Model: (unknown)'}
            </span>
            <span style={{
              padding: '3px 8px',
              borderRadius: '999px',
              background: thinkingLabel === 'extended' ? '#FFF2E3' : '#FFFFFF',
              border: '1px solid #E5E0DB',
              fontWeight: '560',
              color: thinkingLabel === 'extended' ? '#8B6F47' : 'var(--text-main)'
            }}>
              {`Reasoning: ${thinkingLabel}`}
            </span>
          </div>

          <div style={{
            flex: 1,
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: '18px 10px 24px',
            background: 'var(--bg-base)'
          }}>
          <div style={{
            maxWidth: 'min(96%, 1120px)',
            margin: '0 auto',
            width: '100%'
          }}>
            {chatData.messages.map((message, index) => (
              <MessageItem key={index} message={message} />
            ))}
          </div>
          </div>
        </>
      )}
    </div>
  );
}

export default ChatView;
