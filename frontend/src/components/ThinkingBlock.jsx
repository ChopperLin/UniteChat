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
      background: '#F8F4EE',
      border: '1px solid #E7DDD0',
      borderRadius: '14px',
      padding: '12px 14px',
      marginBottom: '8px'
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
          fontSize: '13.5px',
          color: '#6A5F58',
          fontWeight: '560',
          width: '100%',
          padding: 0,
          transition: 'color 0.1s ease-out'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = '#4D433D';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = '#6A5F58';
        }}
      >
        <span style={{
          fontSize: '12px',
          transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)'
        }}>
          ▶
        </span>
        <span>思考过程</span>
      </button>

      {expanded && (
        <div style={{
          marginTop: '14px',
          paddingTop: '14px',
          borderTop: '1px solid #E7DDD0'
        }}>
          {hasRecap && (
            <div style={{
              marginBottom: hasThinkingSteps ? '14px' : '0',
              paddingLeft: '18px',
              borderLeft: '2px solid #CBB79D'
            }}>
              <div style={{
                fontWeight: '560',
                fontSize: '13.5px',
                color: '#6A5F58',
                marginBottom: '7px',
                letterSpacing: '-0.01em'
              }}>
                思考摘要
              </div>
              <div style={{
                fontSize: '13px',
                color: '#625953',
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
              color: '#7A6F67',
              fontSize: '12px',
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
              borderLeft: '2px solid #CBB79D'
            }}>
              <div style={{
                fontWeight: '560',
                fontSize: '13.5px',
                color: '#6A5F58',
                marginBottom: '7px',
                letterSpacing: '-0.01em'
              }}>
                {summary}
              </div>
              <div style={{
                fontSize: '13px',
                color: '#625953',
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
