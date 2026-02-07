import React, { useMemo, useState } from 'react';
import MarkdownContent from './MarkdownContent';
import './ThinkingBlock.css';

function ThinkingBlock({ thinking, thinkingSummary, thinkingDuration }) {
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const steps = useMemo(() => {
    const arr = Array.isArray(thinking) ? thinking : [];
    return arr
      .map((s, idx) => {
        const titleRaw = String(s?.summary || s?.title || '').trim();
        const title = titleRaw && titleRaw !== '思考' ? titleRaw : '';
        const content = String(s?.content || (Array.isArray(s?.chunks) ? s.chunks.join('\n') : '') || '').trim();
        if (!content) return null;
        return { id: `${idx}-${title}`, title, content };
      })
      .filter(Boolean);
  }, [thinking]);

  const recap = useMemo(() => {
    const s = String(thinkingSummary || '').trim();
    if (s) return s;
    if (typeof thinkingDuration === 'number' && thinkingDuration > 0) return 'Thinking completed.';
    return '';
  }, [thinkingSummary, thinkingDuration]);

  const blocks = useMemo(() => {
    const list = [];
    if (recap) list.push({ kind: 'recap', title: '', content: recap });
    for (const s of steps) list.push({ kind: 'step', title: s.title, content: s.content });
    return list;
  }, [recap, steps]);

  if (blocks.length === 0) return null;

  const hiddenCount = Math.max(0, blocks.length - 2);
  const visible = showAll ? blocks : blocks.slice(0, 2);

  const headline = useMemo(() => {
    const firstTitled = blocks.find((b) => b.title);
    if (firstTitled?.title) return firstTitled.title;
    const firstText = String(blocks[0]?.content || '').replace(/\s+/g, ' ').trim();
    if (!firstText) return 'Thinking process';
    return firstText.slice(0, 88) + (firstText.length > 88 ? '…' : '');
  }, [blocks]);

  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-toggle no-scale-effect"
        onClick={() => {
          setExpanded((v) => {
            const next = !v;
            if (!next) setShowAll(false);
            return next;
          });
        }}
        aria-expanded={expanded}
      >
        <span className="thinking-toggle-main">
          <span className="thinking-toggle-icon" aria-hidden="true">◷</span>
          <span className="thinking-toggle-title">{expanded ? 'Thinking process' : headline}</span>
        </span>
        <span className={`thinking-chevron ${expanded ? 'is-open' : ''}`} aria-hidden="true">›</span>
      </button>

      {expanded && (
        <div className="thinking-timeline">
          {visible.map((b, idx) => (
            <div className="thinking-node" key={`${b.kind}-${idx}`}>
              <span className="thinking-node-icon" aria-hidden="true">◷</span>
              <div className="thinking-node-content">
                {b.title && <div className="thinking-node-title">{b.title}</div>}
                <div className="thinking-node-md">
                  <MarkdownContent content={b.content} />
                </div>
              </div>
            </div>
          ))}

          {hiddenCount > 0 && (
            <button
              type="button"
              className="thinking-more no-scale-effect"
              onClick={() => setShowAll((v) => !v)}
            >
              {showAll ? 'Show less' : `Show more (${hiddenCount})`}
            </button>
          )}

          <div className="thinking-done">
            <span className="thinking-node-icon done" aria-hidden="true">◉</span>
            <span>Done</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default ThinkingBlock;
