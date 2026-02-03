import React, { useState, useEffect, useRef } from 'react';

function ellipsizeMiddle(text, maxLen = 26) {
  if (!text) return '';
  const str = String(text);
  if (str.length <= maxLen) return str;
  const headLen = Math.max(6, Math.ceil((maxLen - 3) / 2));
  const tailLen = Math.max(4, Math.floor((maxLen - 3) / 2));
  return `${str.slice(0, headLen)}...${str.slice(-tailLen)}`;
}

function Sidebar({ 
  folders, 
  currentFolder, 
  onFolderChange, 
  conversations, 
  selectedCategory, 
  onCategoryChange, 
  selectedChat, 
  onChatSelect,
  collapsed,
  onToggleCollapse
}) {
  const [categoryExpanded, setCategoryExpanded] = useState({});
  const [folderDropdownOpen, setFolderDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  const safeFolders = Array.isArray(folders) ? folders : [];
  const safeConversations = conversations && typeof conversations === 'object' ? conversations : {};
  const categories = Object.keys(safeConversations);

  const toggleCategory = (category, currentExpanded) => {
    setCategoryExpanded(prev => ({
      ...prev,
      // Use the current rendered state (which may be implicit via selectedCategory)
      // so the first click always toggles correctly.
      [category]: !currentExpanded
    }));
  };

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setFolderDropdownOpen(false);
      }
    };

    if (folderDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [folderDropdownOpen]);

  return (
    <div style={{
      width: collapsed ? '60px' : '280px',
      transition: 'width 0.3s ease',
      borderRight: '1px solid #E5E0DB',
      display: 'flex',
      flexDirection: 'column',
      background: '#EBE9E5',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '1px 0 3px rgba(0, 0, 0, 0.03)'
    }}>
      {/* 顶部操作栏 - Claude风格，与ChatView标题栏对齐 */}
      <div style={{
        height: '72px',
        padding: '0 14px',
        borderBottom: '1px solid #D8D4CE',
        background: '#F2EDE7',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '8px',
        minWidth: 0,
        boxSizing: 'border-box'
      }}>
        {!collapsed && (
          <div ref={dropdownRef} style={{ flex: '1 1 auto', minWidth: 0, position: 'relative' }}>
            {/* 自定义文件夹选择器 */}
            <div
              onClick={() => setFolderDropdownOpen(!folderDropdownOpen)}
              tabIndex={0}
              style={{
                width: '100%',
                padding: '9px 12px',
                border: '1px solid #D8CBBE',
                borderRadius: '11px',
                fontSize: '13.5px',
                lineHeight: 1.2,
                cursor: 'pointer',
                background: folderDropdownOpen ? '#FFFFFF' : '#FBF7F2',
                color: '#2A2523',
                fontWeight: '500',
                transition: 'background-color 0.08s, border-color 0.08s, box-shadow 0.08s',
                outline: 'none',
                boxShadow: folderDropdownOpen 
                  ? '0 0 0 3px rgba(168, 155, 143, 0.15)' 
                  : '0 1px 3px rgba(42, 37, 35, 0.05)',
                boxSizing: 'border-box',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                overflow: 'hidden',
                userSelect: 'none',
                borderColor: folderDropdownOpen ? '#A89B8F' : '#D8CBBE'
              }}
              onMouseEnter={(e) => {
                if (!folderDropdownOpen) {
                  e.currentTarget.style.borderColor = '#C4B4A0';
                  e.currentTarget.style.boxShadow = '0 2px 6px rgba(42, 37, 35, 0.1)';
                  e.currentTarget.style.background = '#FFFFFF';
                }
              }}
              onMouseLeave={(e) => {
                if (!folderDropdownOpen) {
                  e.currentTarget.style.borderColor = '#D4C4B0';
                  e.currentTarget.style.boxShadow = '0 1px 3px rgba(42, 37, 35, 0.05)';
                  e.currentTarget.style.background = '#FDFBF9';
                }
              }}
              title={currentFolder}
            >
              {/* 文件夹图标 */}
              <span style={{ fontSize: '16px', color: '#8A7F76', flexShrink: 0 }}>
                📁
              </span>

              {/* 当前选中的文件夹名 */}
              <span style={{
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}>
                {ellipsizeMiddle(currentFolder, 24)}
              </span>

              {/* 下拉箭头 */}
              <svg 
                width="12" 
                height="8" 
                viewBox="0 0 12 8" 
                style={{
                  flexShrink: 0,
                  transform: `rotate(${folderDropdownOpen ? '180deg' : '0deg'})`,
                  transition: 'transform 0.2s ease',
                  pointerEvents: 'none'
                }}
              >
                <path 
                  d="M1 1.5L6 6.5L11 1.5" 
                  stroke="#8A7F76" 
                  strokeWidth="1.5" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                  fill="none"
                />
              </svg>
            </div>

            {/* 下拉菜单 */}
            {folderDropdownOpen && (
              <div style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                left: 0,
                right: 0,
                background: '#FFFFFF',
                border: '1px solid #D4C4B0',
                borderRadius: '10px',
                boxShadow: '0 4px 12px rgba(42, 37, 35, 0.15)',
                maxHeight: '300px',
                overflowY: 'auto',
                zIndex: 1000,
                animation: 'slideDown 0.2s ease'
              }}>
                {safeFolders.map((folder, index) => (
                  <div
                    key={folder}
                    onClick={() => {
                      onFolderChange(folder);
                      setFolderDropdownOpen(false);
                    }}
                    style={{
                      padding: '10px 14px',
                      cursor: 'pointer',
                      fontSize: '13.5px',
                      color: '#2A2523',
                      background: currentFolder === folder ? '#F2EDE7' : 'transparent',
                      fontWeight: currentFolder === folder ? '600' : '400',
                      transition: 'background-color 0.06s',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      borderBottom: index === safeFolders.length - 1 ? 'none' : '1px solid #F2EDE7'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = currentFolder === folder ? '#E8E3DB' : '#F7F5F2';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = currentFolder === folder ? '#F2EDE7' : 'transparent';
                    }}
                    title={folder}
                  >
                    {folder}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        <button
          onClick={onToggleCollapse}
          style={{
            padding: '8px',
            border: 'none',
            background: 'rgba(42, 37, 35, 0.05)',
            cursor: 'pointer',
            fontSize: '16px',
            lineHeight: 1,
            color: '#5A504A',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '7px',
            transition: 'background-color 0.06s',
            minWidth: '32px',
            minHeight: '32px'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(42, 37, 35, 0.1)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(42, 37, 35, 0.05)';
          }}
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          {collapsed ? '☰' : '◀'}
        </button>
      </div>

      {/* 对话列表 - Claude 风格 */}
      {!collapsed && (
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '10px'
        }}>
          {categories.map(category => {
            const isExpanded = categoryExpanded[category] ?? (category === selectedCategory);
            const chatList = safeConversations[category] || [];
            
            return (
              <div key={category} style={{ marginBottom: '6px' }}>
                {/* 分类标题 - Claude风格 */}
                <div
                  onClick={() => {
                    toggleCategory(category, isExpanded);
                    onCategoryChange(category);
                  }}
                  style={{
                    padding: '11px 14px',
                    background: selectedCategory === category ? '#D8D4CE' : 'transparent',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'background-color 0.06s',
                    fontSize: '14px',
                    fontWeight: '600',
                    color: '#2A2523',
                    letterSpacing: '-0.01em'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedCategory !== category) {
                      e.currentTarget.style.background = 'rgba(42, 37, 35, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedCategory !== category) {
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span>{category}</span>
                  <span style={{
                    fontSize: '12px',
                    color: '#8A7F76',
                    marginLeft: '8px'
                  }}>
                    {isExpanded ? '▼' : '▶'} {chatList.length}
                  </span>
                </div>

                {/* 对话列表 - Claude风格 */}
                {isExpanded && (
                  <div style={{
                    marginLeft: '10px',
                    marginTop: '4px'
                  }}>
                    {chatList.map(chat => (
                      <div
                        key={chat.id}
                        onClick={() => onChatSelect(chat.id)}
                        style={{
                          padding: '10px 14px',
                          marginBottom: '3px',
                          borderRadius: '10px',
                          cursor: 'pointer',
                          background: selectedChat === chat.id ? '#D0C8BE' : 'transparent',
                          transition: 'background-color 0.06s',
                          fontSize: '13.5px',
                          color: '#3A3330',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontWeight: selectedChat === chat.id ? '500' : '400'
                        }}
                        onMouseEnter={(e) => {
                          if (selectedChat !== chat.id) {
                            e.currentTarget.style.background = 'rgba(42, 37, 35, 0.04)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (selectedChat !== chat.id) {
                            e.currentTarget.style.background = 'transparent';
                          }
                        }}
                      >
                        {chat.title}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default Sidebar;
