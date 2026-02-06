import React, { useMemo, useState } from 'react';
import ThinkingBlock from './ThinkingBlock';
import CollapsibleContent from './CollapsibleContent';
import './MessageItem.css';

function MessageItem({ message }) {
  const { role } = message;
  const isUser = role === 'user';
  const [copied, setCopied] = useState(false);

  const hasThinking = Boolean(message?.thinking || message?.thinking_summary || message?.thinking_duration);

  const copyToClipboard = async () => {
    const s = message?.content == null ? '' : String(message.content);
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
      setTimeout(() => setCopied(false), 1000);
    } catch (e) {
      console.error('copy failed', e);
    }
  };

  const ts = message?.ts;
  const dateLabel = useMemo(() => {
    if (!ts) return '';
    const ms = Number(ts) * 1000;
    if (!Number.isFinite(ms)) return '';
    const d = new Date(ms);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  }, [ts]);

  const fullLabel = useMemo(() => {
    if (!ts) return '';
    const ms = Number(ts) * 1000;
    if (!Number.isFinite(ms)) return '';
    const d = new Date(ms);
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [ts]);

  return (
    <div className={`message-item ${isUser ? 'is-user' : 'is-assistant'}`}>
      {!isUser && hasThinking && (
        <div className="message-thinking-wrap">
          <ThinkingBlock
            thinking={message.thinking}
            thinkingSummary={message.thinking_summary}
            thinkingDuration={message.thinking_duration}
          />
        </div>
      )}

      {message?.content && (
        <div className="message-bubble-wrap">
          <div className={`message-bubble ${isUser ? 'message-bubble-user' : 'message-bubble-assistant'}`}>
            <CollapsibleContent
              content={message.content}
              isMarkdown={!isUser}
              gradientColor={isUser ? '#E9E2D9' : '#FDFBF9'}
            />
          </div>

          <div className={`message-meta-row ${isUser ? 'meta-user' : 'meta-assistant'}`}>
            {dateLabel && (
              <span className="message-date" title={fullLabel}>
                {dateLabel}
              </span>
            )}
            <button type="button" className="message-copy-btn" onClick={copyToClipboard}>
              {copied ? '已复制' : '复制'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default MessageItem;
