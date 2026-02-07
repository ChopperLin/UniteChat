import React from 'react';
import MessageItem from './MessageItem';
import './ChatView.css';

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M10.5 10.5L13.5 13.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function ChatView({ chatData, loading, onOpenSearch, onShutdown, shuttingDown }) {
  const meta = chatData?.meta;
  const modelSlug = (meta?.model_slug || '').trim();
  const thinkingEffort = (meta?.thinking_effort || '').trim();
  const thinkingLabel = thinkingEffort ? (thinkingEffort === 'extended' ? 'extended' : thinkingEffort) : 'normal';
  const hasChat = Boolean(chatData);

  return (
    <div className="chat-view">
      <div className="chat-header">
        <div className="chat-header-main">
          <h2 className="chat-title">{chatData?.title || 'UniteChat'}</h2>

          {hasChat && (
            <div className="chat-meta-tags">
              <span className="chat-meta-tag">
                {modelSlug ? `Model: ${modelSlug}` : 'Model: (unknown)'}
              </span>
              <span className={`chat-meta-tag ${thinkingLabel === 'extended' ? 'is-extended' : ''}`}>
                {`Reasoning: ${thinkingLabel}`}
              </span>
            </div>
          )}
        </div>

        <div className="chat-header-actions">
          <button
            type="button"
            className="chat-action-btn search-btn"
            onClick={onOpenSearch}
            title="搜索 (Ctrl+K)"
          >
            <SearchIcon />
            <span>搜索</span>
            <kbd className="chat-kbd">Ctrl K</kbd>
          </button>

          <button
            type="button"
            className="chat-action-btn exit-btn"
            onClick={onShutdown}
            title="退出并停止服务"
          >
            <span>退出</span>
          </button>
        </div>
      </div>

      {shuttingDown ? (
        <div className="chat-empty-state">正在退出并停止服务...</div>
      ) : loading ? (
        <div className="chat-empty-state">加载中...</div>
      ) : !chatData ? (
        <div className="chat-empty-state is-idle">← 选择一个对话查看（或点右上角搜索）</div>
      ) : (
        <div className="chat-scroll">
          <div className="chat-scroll-inner">
            {chatData.messages.map((message, index) => (
              <MessageItem key={index} message={message} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ChatView;
