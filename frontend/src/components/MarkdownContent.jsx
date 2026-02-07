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

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function preprocessMarkdownContent(content) {
  // 更安全的LaTeX转换方法
  // 分步处理，避免正则表达式的贪婪匹配问题
  if (content == null) return '';

  let result = String(content);

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
      formula: result.substring(startIdx + 2, endIdx),
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
        .map((line) => line.replace(/^>\s*/, ''))
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
      formula: result.substring(startIdx + 2, endIdx),
    });

    inlineStart = endIdx + 2;
  }

  // 从后往前替换
  for (let i = inlineMatches.length - 1; i >= 0; i--) {
    const match = inlineMatches[i];
    const replacement = '$' + match.formula.trim() + '$';
    result = result.substring(0, match.start) + replacement + result.substring(match.end);
  }

  return result;
}

function reactChildrenToPlainText(children) {
  let text = '';
  React.Children.forEach(children, (child) => {
    if (child == null) return;
    if (typeof child === 'string' || typeof child === 'number') {
      text += String(child);
      return;
    }
    if (Array.isArray(child)) {
      text += reactChildrenToPlainText(child);
      return;
    }
    if (React.isValidElement(child)) {
      text += reactChildrenToPlainText(child.props?.children);
    }
  });
  return text;
}

function looksLikeAccidentalMarkdownCodeBlock(text) {
  const s = String(text || '').trim();
  if (!s) return false;

  // 如果包含 fence，明显是代码/markdown 源文本，别猜
  if (s.includes('```') || s.includes('~~~')) return false;

  // 强信号：包含 markdown 链接、数学、引用、标题/列表等
  const hasLink = /\[[^\]\n]+\]\([^\)\n]+(?:\s+\"[^\"]*\")?\)/.test(s);
  const hasMath = /\$[^$\n]{1,200}\$/.test(s) || /\\\(|\\\[/.test(s);
  const hasBlockQuote = /(^|\n)\s*>\s+/.test(s);
  const hasHeading = /(^|\n)#{1,6}\s+/.test(s);
  const hasList = /(^|\n)\s*(?:[-*+]|\d+\.)\s+/.test(s);
  const hasMdSignal = hasLink || hasMath || hasBlockQuote || hasHeading || hasList;
  if (!hasMdSignal) return false;

  // 弱信号：更像自然语言而不是代码
  const hasCodeKeywords =
    /\b(const|let|var|function|class|import|export|from|return|def|public|private|package|#include|using|namespace)\b/i.test(
      s
    );
  if (hasCodeKeywords) return false;

  // Avoid unwrapping real code blocks that lack explicit language tags.
  const lines = s.split('\n');
  const codeLikeAssignmentLines = lines.filter((line) =>
    /^\s*[A-Za-z_][A-Za-z0-9_.\[\]]*\s*=\s*.+$/.test(line)
  ).length;
  if (codeLikeAssignmentLines >= 2) return false;

  const codeCommentLines = lines.filter((line) => /^\s*#\s+\S+/.test(line)).length;
  if (codeCommentLines >= 2 && lines.length >= 4) return false;

  const symbolHits = (s.match(/[{};<>]/g) || []).length + (s.match(/=>|==|!=|::|:=/g) || []).length * 2;
  if (symbolHits >= 6) return false;

  const wordCount = (s.match(/\b[\p{L}\p{N}']+\b/gu) || []).length;
  if (wordCount < 6) return false;

  return true;
}

function hasExplicitCodeLanguage(node, children) {
  const classes = [];

  const pushClasses = (value) => {
    if (!value) return;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (typeof v === 'string') classes.push(v);
      }
      return;
    }
    if (typeof value === 'string') classes.push(value);
  };

  if (node && Array.isArray(node.children)) {
    for (const child of node.children) {
      if (!child || typeof child !== 'object') continue;
      const props = child.properties || {};
      pushClasses(props.className);
    }
  }

  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return;
    pushClasses(child.props?.className);
  });

  return classes.some((cls) => typeof cls === 'string' && cls.startsWith('language-'));
}

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
  const [popoverMounted, setPopoverMounted] = useState(false);
  const [idx, setIdx] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const rootRef = useRef(null);
  const popoverRef = useRef(null);
  const hoverTimeoutRef = useRef(null);
  const popoverCloseTimerRef = useRef(null);
  const isHoveringRef = useRef(false);

  const safeRefs = useMemo(() => (Array.isArray(refs) ? refs : []), [refs]);
  const current = safeRefs[idx] || null;
  const currentUrl = typeof current?.url === 'string' ? current.url.trim() : '';
  const isClickable = Boolean(currentUrl);
  const total = safeRefs.length;
  const canCycle = total > 1;

  const updatePosition = () => {
    if (!rootRef.current) return;
    const rect = rootRef.current.getBoundingClientRect();
    setPosition({
      top: rect.bottom + window.scrollY + 4,
      left: rect.left + window.scrollX,
    });
  };

  const gotoPrev = () => {
    if (!canCycle) return;
    setIdx((v) => (v - 1 + total) % total);
  };

  const gotoNext = () => {
    if (!canCycle) return;
    setIdx((v) => (v + 1) % total);
  };

  useEffect(() => {
    if (!total) setOpen(false);
    if (idx > total - 1) setIdx(0);
  }, [idx, total]);

  useEffect(() => {
    if (popoverCloseTimerRef.current) {
      clearTimeout(popoverCloseTimerRef.current);
      popoverCloseTimerRef.current = null;
    }
    if (open) {
      setPopoverMounted(true);
      return;
    }
    if (popoverMounted) {
      popoverCloseTimerRef.current = setTimeout(() => {
        setPopoverMounted(false);
      }, 170);
    }
  }, [open, popoverMounted]);

  useEffect(() => {
    if (!open) return;
    updatePosition();

    function onDocMouseDown(e) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target) && !popoverRef.current?.contains(e.target)) {
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
      if (e.key === 'ArrowLeft') gotoPrev();
      if (e.key === 'ArrowRight') gotoNext();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, canCycle, total]);

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
      if (popoverCloseTimerRef.current) {
        clearTimeout(popoverCloseTimerRef.current);
      }
    };
  }, []);

  const handleMouseEnter = () => {
    isHoveringRef.current = true;
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    hoverTimeoutRef.current = setTimeout(() => {
      if (isHoveringRef.current) {
        setOpen(true);
        setIdx(0);
      }
    }, 140);
  };

  const handleMouseLeave = () => {
    isHoveringRef.current = false;
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    hoverTimeoutRef.current = setTimeout(() => {
      if (!isHoveringRef.current) {
        setOpen(false);
      }
    }, 120);
  };

  const handlePopoverMouseEnter = () => {
    isHoveringRef.current = true;
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  };

  const handlePopoverMouseLeave = () => {
    isHoveringRef.current = false;
    hoverTimeoutRef.current = setTimeout(() => {
      if (!isHoveringRef.current) {
        setOpen(false);
      }
    }, 120);
  };

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
          setOpen((v) => {
            const next = !v;
            if (next) setIdx(0);
            return next;
          });
        }}
        aria-label="Open citations"
      >
        {label}
      </button>

      {popoverMounted && total > 0 && createPortal(
        <div
          ref={popoverRef}
          className={`citation-popover-portal ${open ? 'is-open' : 'is-closing'}`}
          role="dialog"
          aria-label="Citations"
          style={{
            position: 'absolute',
            top: `${position.top}px`,
            left: `${position.left}px`,
            zIndex: 9999,
          }}
          onWheel={(e) => {
            if (!canCycle) return;
            e.preventDefault();
            if (e.deltaY > 0) gotoNext();
            else if (e.deltaY < 0) gotoPrev();
          }}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
        >
          <div className="citation-popover-top">
            <div className="citation-popover-label">{label}</div>
            <div className="citation-popover-controls">
              {canCycle && (
                <button
                  type="button"
                  className="citation-nav-btn no-scale-effect"
                  onClick={gotoPrev}
                  aria-label="Previous citation"
                >
                  ‹
                </button>
              )}
              <span className="citation-count">{idx + 1}/{total}</span>
              {canCycle && (
                <button
                  type="button"
                  className="citation-nav-btn no-scale-effect"
                  onClick={gotoNext}
                  aria-label="Next citation"
                >
                  ›
                </button>
              )}
            </div>
          </div>

          <div className="citation-popover-content" key={`${idx}-${currentUrl || current?.title || 'ref'}`}>
            {current && (isClickable ? (
              <a
                className="citation-card"
                href={currentUrl}
                target="_blank"
                rel="noopener noreferrer"
                title={currentUrl}
              >
                <div className="citation-card-host">{current.host || 'source'}</div>
                <div className="citation-card-title">{current.title || currentUrl}</div>
              </a>
            ) : (
              <div className="citation-card no-url" title={(current.title || '').toString()}>
                <div className="citation-card-host">{current.host || 'source'}</div>
                <div className="citation-card-title">{current.title || 'Reference'}</div>
              </div>
            ))}
          </div>

          {canCycle && (
            <div className="citation-popover-dots" role="tablist" aria-label="Citation pages">
              {safeRefs.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  className={`citation-dot no-scale-effect ${i === idx ? 'is-active' : ''}`}
                  onClick={() => setIdx(i)}
                  aria-label={`Go to citation ${i + 1}`}
                  aria-current={i === idx ? 'true' : 'false'}
                />
              ))}
            </div>
          )}
        </div>,
        document.body
      )}
    </span>
  );
}

function MarkdownContent({ content }) {
  const result = useMemo(() => preprocessMarkdownContent(content), [content]);

  const renderMarkdown = (md, depth = 0) => {
    const safeDepth = clamp(Number(depth) || 0, 0, 3);
    const components = {
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
              <a className="citation-link" target="_blank" rel="noopener noreferrer" {...props}>
                [{num}]
              </a>
            </sup>
          );
        }

        return (
          <a target="_blank" rel="noopener noreferrer" {...props}>
            {children}
          </a>
        );
      },

      // 处理“误触发的缩进代码块”：把它当成普通 markdown 再解析一次
      pre: ({ node, children, ...props }) => {
        if (safeDepth >= 2) {
          return <pre {...props}>{children}</pre>;
        }

        if (hasExplicitCodeLanguage(node, children)) {
          return <pre {...props}>{children}</pre>;
        }

        const plain = reactChildrenToPlainText(children).replace(/\n$/, '');
        if (looksLikeAccidentalMarkdownCodeBlock(plain)) {
          return <div>{renderMarkdown(preprocessMarkdownContent(plain), safeDepth + 1)}</div>;
        }

        return <pre {...props}>{children}</pre>;
      },
    };

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={components}
      >
        {md}
      </ReactMarkdown>
    );
  };

  return (
    <div className="markdown-content">
      {renderMarkdown(result, 0)}
    </div>
  );
}

export default MarkdownContent;
