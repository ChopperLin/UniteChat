import React, { useState, useMemo } from 'react';
import MarkdownContent from './MarkdownContent';

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
  const [expanded, setExpanded] = useState(false);

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
  const previewContent = useMemo(() => {
    if (!content || !stats.shouldCollapse) return content;
    
    const lines = content.split('\n');
    // 取前 5 行作为预览
    const previewLines = lines.slice(0, 5);
    return previewLines.join('\n');
  }, [content, stats.shouldCollapse]);

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

  // 不需要折叠时直接渲染
  if (!stats.shouldCollapse) {
    if (isMarkdown) {
      return <MarkdownContent content={content} />;
    }
    return <span style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-reading)', lineHeight: 1.75 }}>{content}</span>;
  }

  // 需要折叠的情况
  return (
    <div style={{ position: 'relative' }}>
      {/* 内容区域 */}
      <div style={{
        position: 'relative',
        overflow: 'hidden',
        // 折叠时限制高度，展开时自动
        maxHeight: expanded ? 'none' : '180px',
        transition: 'max-height 0.3s ease'
      }}>
        {isMarkdown ? (
          <MarkdownContent content={expanded ? content : previewContent} />
        ) : (
          <span style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-reading)', lineHeight: 1.75 }}>
            {expanded ? content : previewContent}
          </span>
        )}
        
        {/* 渐变遮罩（仅折叠时显示） */}
        {!expanded && (
          <div style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: '60px',
            background: `linear-gradient(transparent, ${gradientColor})`,
            pointerEvents: 'none'
          }} />
        )}
      </div>

      {/* 展开/收起按钮 */}
      <button
        className="no-scale-effect"
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          width: '100%',
          marginTop: expanded ? '12px' : '4px',
          padding: '10px 14px',
          background: '#FAF4ED',
          border: '1px solid #E5D6C8',
          borderRadius: '8px',
          cursor: 'pointer',
          fontSize: '13px',
          color: '#A67C52',
          fontWeight: '600',
          transition: 'background-color 0.1s ease-out, color 0.1s ease-out, border-color 0.1s ease-out',
          justifyContent: 'center'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = '#F5EDE3';
          e.currentTarget.style.color = '#8B6F47';
          e.currentTarget.style.borderColor = '#D4C4B0';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = '#FAF4ED';
          e.currentTarget.style.color = '#A67C52';
          e.currentTarget.style.borderColor = '#E5D6C8';
        }}
      >
        <span style={{
          fontSize: '10px',
          transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)'
        }}>
          ▼
        </span>
        <span>
          {expanded 
            ? '收起' 
            : `展开全部 (${formatCount(stats.charCount)} 字 / ${stats.lineCount} 行)`
          }
        </span>
      </button>
    </div>
  );
}

export default CollapsibleContent;
