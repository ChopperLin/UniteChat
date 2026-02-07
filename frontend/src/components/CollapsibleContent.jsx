import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import MarkdownContent from './MarkdownContent';
import './CollapsibleContent.css';

/**
 * 可折叠内容组件
 * 当内容超过阈值时自动折叠，显示预览和统计信息
 */
function CollapsibleContent({ 
  content, 
  isMarkdown = false,
  // 用户消息和AI回复的背景色不同，渐变遮罩需要匹配
  gradientColor = '#FDFBF9'
}) {
  const COLLAPSED_HEIGHT = 180;
  const [expanded, setExpanded] = useState(false);
  const [contentHeight, setContentHeight] = useState(COLLAPSED_HEIGHT);
  const [viewportMaxHeight, setViewportMaxHeight] = useState(`${COLLAPSED_HEIGHT}px`);
  const contentRef = useRef(null);
  const animationFrameRef = useRef(null);

  // 计算内容统计信息
  const stats = useMemo(() => {
    if (!content) return { lineCount: 0, charCount: 0, shouldCollapse: false };
    
    const lines = content.split('\n');
    const lineCount = lines.length;
    const charCount = content.length;
    
    // 折叠阈值：字符数超过 600 或行数超过 12 行
    const shouldCollapse = charCount > 600 || lineCount > 12;
    
    return { lineCount, charCount, shouldCollapse };
  }, [content]);

  // 获取预览内容（前 5 行）
  // 注：为了获得平滑“收起/展开”动画，这里始终渲染完整内容并通过 max-height 裁剪。

  // 格式化字数显示
  const formatCount = (count) => {
    if (count >= 1000) {
      return (count / 1000).toFixed(1) + 'k';
    }
    return count.toString();
  };

  // 如果内容为空
  if (!content) {
    return null;
  }

  useLayoutEffect(() => {
    if (!stats.shouldCollapse || !contentRef.current) return;

    const measure = () => {
      const h = Math.ceil(contentRef.current.scrollHeight);
      setContentHeight(Math.max(COLLAPSED_HEIGHT, h));
    };

    measure();

    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => measure());
    ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, [content, isMarkdown, stats.shouldCollapse]);

  useEffect(() => {
    if (!stats.shouldCollapse) {
      setExpanded(false);
      setViewportMaxHeight(`${COLLAPSED_HEIGHT}px`);
    }
  }, [stats.shouldCollapse]);

  useEffect(() => {
    if (!stats.shouldCollapse) {
      return;
    }
    // Keep opening animation target synced while still animating with numeric max-height.
    if (expanded && viewportMaxHeight !== 'none') {
      const next = `${contentHeight}px`;
      setViewportMaxHeight((prev) => (prev === next ? prev : next));
    }
  }, [contentHeight, expanded, stats.shouldCollapse, viewportMaxHeight]);

  useEffect(() => {
    return () => {
      if (animationFrameRef.current != null) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  // 不需要折叠时直接渲染
  if (!stats.shouldCollapse) {
    if (isMarkdown) {
      return <MarkdownContent content={content} />;
    }
    return <span className="collapsible-plain">{content}</span>;
  }

  // 需要折叠的情况
  const handleToggle = () => {
    if (animationFrameRef.current != null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    const measuredHeight = Math.max(
      contentHeight,
      Math.ceil(contentRef.current?.scrollHeight || contentHeight),
      COLLAPSED_HEIGHT
    );

    if (expanded) {
      // Ensure we always collapse from the real current height (works even when max-height is "none").
      setViewportMaxHeight(`${measuredHeight}px`);
      setExpanded(false);
      animationFrameRef.current = requestAnimationFrame(() => {
        setViewportMaxHeight(`${COLLAPSED_HEIGHT}px`);
      });
      return;
    }

    // Expand from collapsed height to measured height, then unlock to "none" on transition end.
    setViewportMaxHeight(`${COLLAPSED_HEIGHT}px`);
    setExpanded(true);
    animationFrameRef.current = requestAnimationFrame(() => {
      setViewportMaxHeight(`${measuredHeight}px`);
    });
  };

  const handleViewportTransitionEnd = (e) => {
    if (!e || e.propertyName !== 'max-height') return;
    if (!expanded) return;
    setViewportMaxHeight((prev) => (prev === 'none' ? prev : 'none'));
  };

  return (
    <div
      className={`collapsible-content ${expanded ? 'is-expanded' : 'is-collapsed'}`}
      style={{ '--collapse-gradient-color': gradientColor }}
    >
      {/* 内容区域 */}
      <div
        className="collapsible-content-viewport"
        style={{ maxHeight: viewportMaxHeight }}
        onTransitionEnd={handleViewportTransitionEnd}
      >
        <div ref={contentRef}>
          {isMarkdown ? <MarkdownContent content={content} /> : <span className="collapsible-plain">{content}</span>}
        </div>

        {/* 渐变遮罩（仅折叠时显示） */}
        <div className="collapsible-content-fade" />
      </div>

      {/* 展开/收起按钮 */}
      <button
        className="collapsible-toggle no-scale-effect"
        onClick={handleToggle}
        aria-expanded={expanded}
      >
        <span className="collapsible-toggle-icon" aria-hidden="true">
          {expanded ? '▴' : '▾'}
        </span>
        <span>
          {expanded ? '收起' : `展开全部 (${formatCount(stats.charCount)} 字 / ${stats.lineCount} 行)`}
        </span>
      </button>
    </div>
  );
}

export default CollapsibleContent;
