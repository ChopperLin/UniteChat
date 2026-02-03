import React, { useState } from 'react';

function ThinkingBlock({ thinking, thinkingSummary, thinkingDuration }) {
  const [expanded, setExpanded] = useState(false);

  const hasThinkingSteps = Array.isArray(thinking) && thinking.length > 0;
  const hasRecap = Boolean(thinkingSummary) || (typeof thinkingDuration === 'number' && thinkingDuration > 0);

  const totalThinkingChars = hasThinkingSteps
    ? thinking.reduce((acc, step) => {
        const content = step?.content || (Array.isArray(step?.chunks) ? step.chunks.join('\n') : '') || '';
        const summary = step?.summary || step?.title || '';
        return acc + String(content).length + String(summary).length;
      }, 0)
    : 0;

  const likelyMissingFullThinking = hasRecap && (!hasThinkingSteps || totalThinkingChars < 120);

  if (!hasThinkingSteps && !hasRecap) {
    return null;
  }

  return (
    <div style={{
      background: '#FAF4ED',
      border: '1px solid #E5D6C8',
      borderRadius: '12px',
      padding: '14px 18px',
      marginBottom: '12px',
      boxShadow: '0 1px 2px rgba(42, 37, 35, 0.03)'
    }}>
      <button
        className="no-scale-effect"
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: '14px',
          color: '#A67C52',
          fontWeight: '600',
          width: '100%',
          padding: 0,
          transition: 'color 0.1s ease-out'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = '#8B6F47';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = '#A67C52';
        }}
      >
        <span style={{
          fontSize: '12px',
          transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)'
        }}>
          ▶
        </span>
        <span>💭 思考过程</span>
      </button>

      {expanded && (
        <div style={{
          marginTop: '14px',
          paddingTop: '14px',
          borderTop: '1px solid #E5D6C8'
        }}>
          {hasRecap && (
            <div style={{
              marginBottom: hasThinkingSteps ? '14px' : '0',
              paddingLeft: '18px',
              borderLeft: '3px solid #C89968'
            }}>
              <div style={{
                fontWeight: '600',
                fontSize: '14px',
                color: '#9C6644',
                marginBottom: '7px',
                letterSpacing: '-0.01em'
              }}>
                思考摘要
              </div>
              <div style={{
                fontSize: '13.5px',
                color: '#5A504A',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap'
              }}>
                {thinkingSummary || (typeof thinkingDuration === 'number' ? `已思考 ${thinkingDuration}s` : '')}
              </div>
            </div>
          )}

          {likelyMissingFullThinking && (
            <div style={{
              marginBottom: hasThinkingSteps ? '14px' : '0',
              color: '#7A6B63',
              fontSize: '12.5px',
              lineHeight: '1.6'
            }}>
              提示：部分对话导出文件不会包含完整“思考过程”正文，只会提供思考摘要/用时或少量片段；本页面只能展示导出数据里实际存在的内容。
            </div>
          )}

          {hasThinkingSteps && thinking.map((step, index) => {
            const summary = step?.summary || step?.title || `步骤 ${index + 1}`;
            const content = step?.content || (Array.isArray(step?.chunks) ? step.chunks.join('\n') : '') || '';
            return (
            <div key={index} style={{
              marginBottom: '14px',
              paddingLeft: '18px',
              borderLeft: '3px solid #C89968'
            }}>
              <div style={{
                fontWeight: '600',
                fontSize: '14px',
                color: '#9C6644',
                marginBottom: '7px',
                letterSpacing: '-0.01em'
              }}>
                {summary}
              </div>
              <div style={{
                fontSize: '13.5px',
                color: '#5A504A',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap'
              }}>
                {content}
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ThinkingBlock;
