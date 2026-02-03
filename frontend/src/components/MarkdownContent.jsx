import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/atom-one-light.css';
import 'katex/dist/katex.min.css';
import './MarkdownContent.css';

function decodeCitePayloadFromHref(href) {
  try {
    const prefix = 'cite://';
    if (!href || !href.startsWith(prefix)) return null;
    const b64 = href.slice(prefix.length);
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const normalized = padded.replace(/-/g, '+').replace(/_/g, '/');
    const jsonStr = decodeURIComponent(
      Array.prototype.map
        .call(atob(normalized), (c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonStr);
    if (!payload || !Array.isArray(payload.refs)) return null;
    return payload;
  } catch (e) {
    return null;
  }
}

function decodeCitePayloadFromTitle(title) {
  try {
    const prefix = 'citepayload:';
    if (!title || typeof title !== 'string' || !title.startsWith(prefix)) return null;
    const b64 = title.slice(prefix.length);
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const normalized = padded.replace(/-/g, '+').replace(/_/g, '/');
    const jsonStr = decodeURIComponent(
      Array.prototype.map
        .call(atob(normalized), (c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonStr);
    if (!payload || !Array.isArray(payload.refs)) return null;
    return payload;
  } catch (e) {
    return null;
  }
}

function CitationPill({ label, refs }) {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const rootRef = useRef(null);
  const hoverTimeoutRef = useRef(null);
  const isHoveringRef = useRef(false);

  const safeRefs = useMemo(() => {
    const arr = Array.isArray(refs) ? refs : [];
    // 调试信息：检查refs数量
    if (arr.length > 0) {
      console.log(`[Citation] "${label}" has ${arr.length} references`);
    }
    return arr;
  }, [refs, label]);
  const current = safeRefs[idx] || null;

  // 计算弹出窗口的位置
  const updatePosition = () => {
    if (!rootRef.current) return;
    const rect = rootRef.current.getBoundingClientRect();
    setPosition({
      top: rect.bottom + window.scrollY + 4,
      left: rect.left + window.scrollX
    });
  };

  useEffect(() => {
    if (!open) return;
    updatePosition();
    
    function onDocMouseDown(e) {
      if (!rootRef.current) return;
      const popover = document.getElementById('citation-popover-portal');
      if (!rootRef.current.contains(e.target) && (!popover || !popover.contains(e.target))) {
        setOpen(false);
      }
    }
    
    function onScroll() {
      updatePosition();
    }
    
    function onResize() {
      updatePosition();
    }
    
    document.addEventListener('mousedown', onDocMouseDown);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') setOpen(false);
      if (e.key === 'ArrowLeft') setIdx((v) => Math.max(0, v - 1));
      if (e.key === 'ArrowRight') setIdx((v) => Math.min(safeRefs.length - 1, v + 1));
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, safeRefs.length]);

  // 清理悬停定时器
  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
    };
  }, []);

  const handleMouseEnter = () => {
    isHoveringRef.current = true;
    // 清除任何关闭定时器
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    // 鼠标进入时，短延迟显示（避免快速划过时频繁弹出）
    hoverTimeoutRef.current = setTimeout(() => {
      if (isHoveringRef.current) {
        setOpen(true);
        setIdx(0);
      }
    }, 200);
  };

  const handleMouseLeave = () => {
    isHoveringRef.current = false;
    // 清除显示定时器
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    // 鼠标离开时，快速关闭
    hoverTimeoutRef.current = setTimeout(() => {
      if (!isHoveringRef.current) {
        setOpen(false);
      }
    }, 150);
  };

  const handlePopoverMouseEnter = () => {
    isHoveringRef.current = true;
    // 鼠标进入弹出窗口时，清除关闭定时器
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  };

  const handlePopoverMouseLeave = () => {
    isHoveringRef.current = false;
    // 鼠标离开弹出窗口时，快速关闭
    hoverTimeoutRef.current = setTimeout(() => {
      if (!isHoveringRef.current) {
        setOpen(false);
      }
    }, 150);
  };

  const total = safeRefs.length;

  return (
    <span 
      className="citation" 
      ref={rootRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        className="citation-pill"
        onClick={() => {
          setOpen((v) => !v);
          setIdx(0);
        }}
        aria-label="Open citations"
      >
        {label}
      </button>

      {open && total > 0 && createPortal(
        <div 
          id="citation-popover-portal"
          className="citation-popover-portal" 
          role="dialog" 
          aria-label="Citations"
          style={{
            position: 'absolute',
            top: `${position.top}px`,
            left: `${position.left}px`,
            zIndex: 9999
          }}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
        >
          <div className="citation-popover-header">
            <div className="citation-popover-title">{label}</div>
            {total > 1 && (
              <div className="citation-popover-controls">
                <button
                  type="button"
                  className="citation-nav"
                  onClick={() => setIdx((v) => Math.max(0, v - 1))}
                  disabled={idx <= 0}
                  aria-label="Previous citation"
                >
                  ‹
                </button>
                <button
                  type="button"
                  className="citation-nav"
                  onClick={() => setIdx((v) => Math.min(total - 1, v + 1))}
                  disabled={idx >= total - 1}
                  aria-label="Next citation"
                >
                  ›
                </button>
                <div className="citation-count">{idx + 1}/{total}</div>
              </div>
            )}
          </div>

          <div className="citation-popover-body">
            {current && (
              <a
                className="citation-card"
                href={current.url}
                target="_blank"
                rel="noopener noreferrer"
                title={current.url}
              >
                <div className="citation-card-host">{current.host || 'source'}</div>
                <div className="citation-card-title">{current.title || current.url}</div>
              </a>
            )}
          </div>
        </div>,
        document.body
      )}
    </span>
  );
}

function MarkdownContent({ content }) {
  // 更安全的LaTeX转换方法
  // 分步处理，避免正则表达式的贪婪匹配问题
  
  let result = content;
  
  // 1. 先处理块级公式 \[...\]
  const blockMatches = [];
  let blockStart = 0;
  while (true) {
    const startIdx = result.indexOf('\\[', blockStart);
    if (startIdx === -1) break;
    
    const endIdx = result.indexOf('\\]', startIdx + 2);
    if (endIdx === -1) break;
    
    blockMatches.push({
      start: startIdx,
      end: endIdx + 2,
      formula: result.substring(startIdx + 2, endIdx)
    });
    
    blockStart = endIdx + 2;
  }
  
  // 从后往前替换，避免索引偏移
  for (let i = blockMatches.length - 1; i >= 0; i--) {
    const match = blockMatches[i];
    // 清理公式内容：移除每行开头的引用块标记 "> "
    let cleanFormula = match.formula;
    if (cleanFormula.includes('\n>')) {
      cleanFormula = cleanFormula
        .split('\n')
        .map(line => line.replace(/^>\s*/, ''))
        .join('\n')
        .trim();
    } else {
      cleanFormula = cleanFormula.trim();
    }
    
    const replacement = '\n\n$$\n' + cleanFormula + '\n$$\n\n';
    result = result.substring(0, match.start) + replacement + result.substring(match.end);
  }
  
  // 2. 处理行内公式 \(...\)
  const inlineMatches = [];
  let inlineStart = 0;
  while (true) {
    const startIdx = result.indexOf('\\(', inlineStart);
    if (startIdx === -1) break;
    
    const endIdx = result.indexOf('\\)', startIdx + 2);
    if (endIdx === -1) break;
    
    inlineMatches.push({
      start: startIdx,
      end: endIdx + 2,
      formula: result.substring(startIdx + 2, endIdx)
    });
    
    inlineStart = endIdx + 2;
  }
  
  // 从后往前替换
  for (let i = inlineMatches.length - 1; i >= 0; i--) {
    const match = inlineMatches[i];
    const replacement = '$' + match.formula.trim() + '$';
    result = result.substring(0, match.start) + replacement + result.substring(match.end);
  }

  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
          // 链接在新窗口打开
          a: ({ node, children, ...props }) => {
            const href = props.href || '';
            const citePayload = decodeCitePayloadFromTitle(props.title) || decodeCitePayloadFromHref(href);
            if (citePayload) {
              const label = React.Children.toArray(children)
                .map((c) => (typeof c === 'string' ? c : ''))
                .join('')
                .trim() || 'ref';
              return <CitationPill label={label} refs={citePayload.refs} />;
            }

            const text = React.Children.toArray(children)
              .map((c) => (typeof c === 'string' ? c : ''))
              .join('')
              .trim();

            // 后端输出的 citation 形态通常是 [[1]] / [[12]]
            const m = text.match(/^\[\[(\d+)\]\]$/) || text.match(/^\[(\d+)\]$/);
            if (m) {
              const num = m[1];
              return (
                <sup className="citation-sup">
                  <a
                    className="citation-link"
                    target="_blank"
                    rel="noopener noreferrer"
                    {...props}
                  >
                    [{num}]
                  </a>
                </sup>
              );
            }

            return <a target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
          },
        }}
      >
        {result}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownContent;
