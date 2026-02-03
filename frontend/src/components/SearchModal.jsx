import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

const HISTORY_KEY = 'gpt-chat-browser-search-history';
const MAX_HISTORY = 10;

// 搜索历史管理
function getSearchHistory() {
  try {
    const data = localStorage.getItem(HISTORY_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

function addToSearchHistory(keyword) {
  if (!keyword || !keyword.trim()) return;
  
  try {
    let history = getSearchHistory();
    const trimmed = keyword.trim();
    
    // 移除已存在的相同关键词
    history = history.filter(h => h !== trimmed);
    
    // 添加到开头
    history.unshift(trimmed);
    
    // 限制最多10条
    if (history.length > MAX_HISTORY) {
      history = history.slice(0, MAX_HISTORY);
    }
    
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch (e) {
    console.error('保存搜索历史失败:', e);
  }
}

function clearSearchHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch (e) {
    console.error('清除搜索历史失败:', e);
  }
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightText(text, q) {
  if (!q || !text) return text;
  const qq = q.trim();
  if (!qq) return text;
  // 小优化：避免过长正则
  if (qq.length > 60) return text;

  try {
    const re = new RegExp(escapeRegExp(qq), 'ig');
    const parts = String(text).split(re);
    const matches = String(text).match(re);
    if (!matches) return text;

    const out = [];
    for (let i = 0; i < parts.length; i++) {
      out.push(parts[i]);
      if (i < matches.length) {
        out.push(
          <mark
            key={`m-${i}`}
            style={{ background: '#F9E9D7', padding: '1px 4px', borderRadius: '4px', color: '#9C6644' }}
          >
            {matches[i]}
          </mark>
        );
      }
    }
    return out;
  } catch {
    return text;
  }
}

function ellipsizeMiddle(text, maxLen = 24) {
  if (!text) return '';
  const str = String(text);
  if (str.length <= maxLen) return str;
  const headLen = Math.max(6, Math.ceil((maxLen - 3) / 2));
  const tailLen = Math.max(4, Math.floor((maxLen - 3) / 2));
  return `${str.slice(0, headLen)}...${str.slice(-tailLen)}`;
}

export default function SearchModal({
  open,
  folder,
  onClose,
  onSelect,
}) {
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [stats, setStats] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [searchHistory, setSearchHistory] = useState([]);
  const [scopeAll, setScopeAll] = useState(false);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  const qTrim = useMemo(() => q.trim(), [q]);

  // 加载搜索历史
  useEffect(() => {
    if (open) {
      setSearchHistory(getSearchHistory());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // reset
    setQ('');
    setResults([]);
    setStats(null);
    setActiveIndex(0);
    setScopeAll(false);

    // 使用 requestAnimationFrame 确保 DOM 渲染后再 focus
    const rafId = requestAnimationFrame(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        // 确保光标在末尾
        inputRef.current.setSelectionRange(inputRef.current.value.length, inputRef.current.value.length);
      }
    });

    return () => cancelAnimationFrame(rafId);
  }, [open, folder]);

  useEffect(() => {
    if (!open) return;

    // debounce search
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }

    if (!qTrim) {
      setResults([]);
      setStats(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let retryTimer = null;

    const runSearch = async () => {
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      try {
        const resp = await axios.get('/api/search', {
          params: {
            q: qTrim,
            folder: scopeAll ? undefined : folder,
            scope: scopeAll ? 'all' : 'folder',
            limit: 80,
          },
          signal: controller.signal,
        });

        const data = resp.data || {};
        const list = Array.isArray(data.results) ? data.results : [];
        const ready = data.ready !== false;

        setResults(list);
        setStats(data.stats || null);
        setActiveIndex(0);

        if (!ready && !cancelled) {
          // 索引构建中：短轮询，直到 ready
          retryTimer = setTimeout(() => {
            if (!cancelled) runSearch();
          }, 260);
          return;
        }

        if (!cancelled) setLoading(false);
      } catch (e) {
        if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') {
          return;
        }
        console.error('搜索失败:', e);
        setResults([]);
        setStats(null);
        if (!cancelled) setLoading(false);
      }
    };

    const handle = setTimeout(runSearch, 160);

    return () => {
      cancelled = true;
      clearTimeout(handle);
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [open, folder, qTrim, scopeAll]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e) => {
      // 检查事件是否来自输入框
      const isFromInput = e.target === inputRef.current;

      if (e.key === 'Escape') {
        e.preventDefault();
        onClose?.();
        return;
      }
      
      // ArrowUp/ArrowDown: 在输入框中也允许导航结果
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => clamp(i + 1, 0, Math.max(0, results.length - 1)));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => clamp(i - 1, 0, Math.max(0, results.length - 1)));
        return;
      }
      
      // Enter: 只在输入框中且有结果时才处理
      if (e.key === 'Enter' && isFromInput) {
        if (!results.length) return;
        e.preventDefault();
        const r = results[activeIndex];
        if (r) {
          // 保存搜索历史
          if (qTrim) {
            addToSearchHistory(qTrim);
          }
          onSelect?.(r);
          onClose?.();
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, results, activeIndex, onClose, onSelect]);

  if (!open) return null;

  return (
    <div
      onClick={(e) => {
        // 点击遮罩关闭
        if (e.target === e.currentTarget) onClose?.();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(42, 37, 35, 0.4)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '10vh',
        paddingLeft: '16px',
        paddingRight: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(720px, 100%)',
          background: '#FDFBF9',
          borderRadius: '20px',
          boxShadow: '0 20px 70px rgba(42, 37, 35, 0.25), 0 0 0 1px rgba(42, 37, 35, 0.08)',
          overflow: 'hidden'
        }}
      >
        {/* 搜索输入区 - Claude风格 */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid #E5E0DB',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            background: '#FFFFFF'
          }}
        >
          {/* 搜索图标 */}
          <svg 
            width="20" 
            height="20" 
            viewBox="0 0 20 20" 
            fill="none" 
            style={{ flexShrink: 0, opacity: 0.5 }}
          >
            <circle cx="8.5" cy="8.5" r="5.75" stroke="#8A7F76" strokeWidth="1.5"/>
            <path d="M12.5 12.5L17 17" stroke="#8A7F76" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          
          <input
            ref={inputRef}
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={(e) => e.target.select()}
            placeholder="搜索对话（标题/内容）"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck="false"
            style={{
              flex: 1,
              padding: '0',
              border: 'none',
              fontSize: '16px',
              outline: 'none',
              background: 'transparent',
              color: '#2A2523',
              fontWeight: '400'
            }}
          />
          
          {/* 快捷键提示 */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            flexShrink: 0
          }}>
            <kbd style={{
              padding: '4px 8px',
              background: '#F2EDE7',
              border: '1px solid #DCD7CF',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#5A504A',
              fontFamily: 'monospace',
              fontWeight: '500',
              boxShadow: '0 1px 2px rgba(42, 37, 35, 0.05)'
            }}>
              Esc
            </kbd>
            
            <button
              onClick={onClose}
              style={{
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: '20px',
                color: '#A89B8F',
                padding: '4px',
                borderRadius: '6px',
                transition: 'background-color 0.06s, color 0.06s',
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#F2EDE7';
                e.currentTarget.style.color = '#5A504A';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = '#A89B8F';
              }}
              title="关闭 (Esc)"
            >
              ✕
            </button>
          </div>
        </div>

        <div style={{ 
          padding: '12px 24px', 
          fontSize: '12.5px', 
          color: '#8A7F76', 
          background: '#F7F5F2',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap'
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ opacity: 0.7 }}>范围</span>
            <button
              type="button"
              onClick={() => setScopeAll((v) => !v)}
              style={{
                border: '1px solid #E5E0DB',
                background: scopeAll ? '#E5D6C8' : '#FFFFFF',
                color: '#2A2523',
                padding: '4px 10px',
                borderRadius: '999px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
              title={scopeAll ? '点击切换到当前文件夹' : '点击切换到全部文件夹'}
            >
              {scopeAll ? '全部文件夹' : (folder || '-')}
            </button>
          </span>
          {stats?.tookMs != null && (
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ opacity: 0.7 }}>耗时</span>
              <span style={{ color: '#2A2523', fontWeight: 600 }}>{stats.tookMs}ms</span>
            </span>
          )}
          {stats?.docCount != null && (
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ opacity: 0.7 }}>索引</span>
              <span style={{ color: '#2A2523', fontWeight: 600 }}>{stats.docCount} 条</span>
            </span>
          )}
          {loading && (
            <span style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px',
              color: '#B8835A',
              fontWeight: 500
            }}>
              <span style={{ 
                display: 'inline-block',
                width: '12px',
                height: '12px',
                border: '2px solid #E5E0DB',
                borderTopColor: '#B8835A',
                borderRadius: '50%',
                animation: 'spin 0.6s linear infinite'
              }}></span>
              搜索中
            </span>
          )}
        </div>

        <div
          style={{
            maxHeight: '60vh',
            overflowY: 'auto',
            borderTop: '1px solid #E5E0DB',
          }}
        >
          {!qTrim && (
            <div>
              <div style={{ 
                padding: '28px 24px', 
                color: '#8A7F76', 
                fontSize: '14.5px',
                lineHeight: '1.6'
              }}>
                <div style={{ marginBottom: '12px', color: '#5A504A', fontWeight: 500 }}>
                  输入关键词，实时搜索标题与内容
                </div>
                <div style={{ 
                  fontSize: '13px', 
                  color: '#A89B8F',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}>
                  <div><kbd style={{
                    padding: '2px 6px',
                    background: '#F2EDE7',
                    border: '1px solid #DCD7CF',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    marginRight: '4px'
                  }}>↑</kbd><kbd style={{
                    padding: '2px 6px',
                    background: '#F2EDE7',
                    border: '1px solid #DCD7CF',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    marginRight: '8px'
                  }}>↓</kbd>选择结果</div>
                  <div><kbd style={{
                    padding: '2px 6px',
                    background: '#F2EDE7',
                    border: '1px solid #DCD7CF',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    marginRight: '8px'
                  }}>Enter</kbd>打开对话</div>
                </div>
              </div>
              
              {/* 搜索历史 - Claude风格 */}
              {searchHistory.length > 0 && (
                <div style={{ borderTop: '1px solid #E5E0DB' }}>
                  <div style={{ 
                    padding: '14px 24px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    background: '#FAF8F6'
                  }}>
                    <span style={{ 
                      fontSize: '12.5px', 
                      color: '#5A504A', 
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ opacity: 0.6 }}>
                        <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2"/>
                        <path d="M7 4V7L9 9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                      </svg>
                      最近搜索
                    </span>
                    <button
                      onClick={() => {
                        clearSearchHistory();
                        setSearchHistory([]);
                      }}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        cursor: 'pointer',
                        fontSize: '12px',
                        color: '#A89B8F',
                        padding: '6px 10px',
                        borderRadius: '7px',
                        transition: 'background-color 0.06s, color 0.06s',
                        fontWeight: 500
                      }}
                      onMouseEnter={(e) => {
                        e.target.style.color = '#5A504A';
                        e.target.style.background = 'rgba(42, 37, 35, 0.06)';
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.color = '#A89B8F';
                        e.target.style.background = 'transparent';
                      }}
                      title="清除历史记录"
                    >
                      清除
                    </button>
                  </div>
                  <div style={{ padding: '12px 24px 18px' }}>
                    {searchHistory.map((keyword, idx) => (
                      <button
                        key={idx}
                        onClick={() => setQ(keyword)}
                        style={{
                          display: 'inline-block',
                          margin: '4px 8px 4px 0',
                          padding: '8px 16px',
                          border: '1px solid #E5E0DB',
                          background: '#FFFFFF',
                          borderRadius: '20px',
                          fontSize: '13.5px',
                          color: '#2A2523',
                          cursor: 'pointer',
                          transition: 'background-color 0.06s, border-color 0.06s, box-shadow 0.06s',
                          fontWeight: '500',
                          boxShadow: '0 1px 2px rgba(42, 37, 35, 0.04)'
                        }}
                        onMouseEnter={(e) => {
                          e.target.style.background = '#F2EDE7';
                          e.target.style.borderColor = '#D4C4B0';
                          e.target.style.boxShadow = '0 2px 4px rgba(42, 37, 35, 0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.background = '#FFFFFF';
                          e.target.style.borderColor = '#E5E0DB';
                          e.target.style.boxShadow = '0 1px 2px rgba(42, 37, 35, 0.04)';
                        }}
                        title={`搜索：${keyword}`}
                      >
                        {keyword}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {qTrim && !loading && results.length === 0 && (
            <div style={{ 
              padding: '40px 24px', 
              color: '#8A7F76', 
              fontSize: '14.5px',
              textAlign: 'center'
            }}>
              <div style={{ marginBottom: '8px', fontSize: '32px', opacity: 0.4 }}>🔍</div>
              <div style={{ fontWeight: 500 }}>没有找到匹配结果</div>
              <div style={{ marginTop: '6px', fontSize: '13px', color: '#A89B8F' }}>
                试试其他关键词
              </div>
            </div>
          )}

          {results.map((r, i) => {
            const active = i === activeIndex;
            const folderLabel = r.folder || folder || '-';
            const categoryLabel = r.category || '-';
            return (
              <div
                key={`${r.category}:${r.id}:${i}`}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => {
                  // 保存搜索历史
                  if (qTrim) {
                    addToSearchHistory(qTrim);
                  }
                  onSelect?.(r);
                  onClose?.();
                }}
                style={{
                  padding: '16px 24px',
                  cursor: 'pointer',
                  background: active ? '#F2EDE7' : 'transparent',
                  borderBottom: '1px solid #E5E0DB',
                  transition: 'background-color 0.04s ease-out'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <div style={{ 
                    fontSize: '14px', 
                    color: '#1A1715', 
                    fontWeight: 600, 
                    flex: 1, 
                    minWidth: 0,
                    letterSpacing: '-0.01em'
                  }}>
                    <span style={{ 
                      whiteSpace: 'nowrap', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      display: 'block' 
                    }}>
                      {highlightText(r.title, qTrim)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                    <div
                      style={{
                        fontSize: '11.5px',
                        color: '#7A5F3D',
                        background: active ? '#F0E6DA' : '#FBF7F2',
                        border: `1px solid ${active ? '#D4C4B0' : '#E5E0DB'}`,
                        padding: '4px 10px',
                        borderRadius: '12px',
                        fontWeight: '600',
                        maxWidth: '220px',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        transition: 'all 0.12s'
                      }}
                      title={folderLabel}
                    >
                      {ellipsizeMiddle(folderLabel, 28)}
                    </div>
                    <div
                      style={{
                        fontSize: '11.5px',
                        color: '#8B6F47',
                        background: active ? '#E5D6C8' : '#F7F3EE',
                        border: `1px solid ${active ? '#D4C4B0' : '#E5E0DB'}`,
                        padding: '4px 11px',
                        borderRadius: '12px',
                        fontWeight: '600',
                        transition: 'all 0.12s'
                      }}
                    >
                      {categoryLabel}
                    </div>
                  </div>
                </div>
                {r.snippet && (
                  <div style={{ 
                    marginTop: '8px', 
                    fontSize: '13px', 
                    color: '#5A504A', 
                    lineHeight: 1.6,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}>
                    {highlightText(r.snippet, qTrim)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
