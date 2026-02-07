import React, { useMemo, useState } from 'react';
import './ThinkingBlock.css';

function ThinkingBlock({ thinking, thinkingSummary, thinkingDuration }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllSteps, setShowAllSteps] = useState(false);

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

  const summaryPreview = useMemo(() => {
    if (typeof thinkingSummary === 'string' && thinkingSummary.trim()) {
      return thinkingSummary.trim().split('\n').filter(Boolean)[0] || '';
    }
    if (hasThinkingSteps) {
      const first = thinking[0] || {};
      const text = String(first.summary || first.title || first.content || '').trim();
      if (text) return text.slice(0, 140);
    }
    if (typeof thinkingDuration === 'number' && thinkingDuration > 0) {
      return `已思考 ${thinkingDuration}s`;
    }
    return '';
  }, [thinkingSummary, thinking, hasThinkingSteps, thinkingDuration]);

  if (!hasThinkingSteps && !hasRecap) {
    return null;
  }

  const hiddenCount = hasThinkingSteps ? Math.max(0, thinking.length - 3) : 0;
  const visibleSteps = hasThinkingSteps ? (showAllSteps ? thinking : thinking.slice(0, 3)) : [];

  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-toggle no-scale-effect"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="thinking-toggle-left">
          <span className="thinking-icon" aria-hidden="true">◷</span>
          <span className="thinking-label">思考过程</span>
          {!expanded && summaryPreview && <span className="thinking-preview-inline">{summaryPreview}</span>}
        </span>
        <span className="thinking-toggle-right">
          {typeof thinkingDuration === 'number' && thinkingDuration > 0 && (
            <span className="thinking-duration">{thinkingDuration}s</span>
          )}
          <span className={`thinking-chevron ${expanded ? 'is-open' : ''}`} aria-hidden="true">⌄</span>
        </span>
      </button>

      {expanded && (
        <div className="thinking-body">
          {hasRecap && (
            <div className="thinking-recap">
              {thinkingSummary || (typeof thinkingDuration === 'number' ? `已思考 ${thinkingDuration}s` : '')}
            </div>
          )}

          {likelyMissingFullThinking && (
            <div className="thinking-tip">
              提示：当前导出可能只包含思考摘要或片段，不一定有完整思考正文。
            </div>
          )}

          {visibleSteps.map((step, index) => {
            const summary = step?.summary || step?.title || `步骤 ${index + 1}`;
            const content = step?.content || (Array.isArray(step?.chunks) ? step.chunks.join('\n') : '') || '';
            return (
              <div key={index} className="thinking-step">
                <div className="thinking-step-title">{summary}</div>
                <div className="thinking-step-content">{content}</div>
              </div>
            );
          })}

          {hiddenCount > 0 && !showAllSteps && (
            <button
              type="button"
              className="thinking-more no-scale-effect"
              onClick={() => setShowAllSteps(true)}
            >
              Show more ({hiddenCount})
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ThinkingBlock;
