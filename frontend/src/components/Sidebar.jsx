import React, { useState, useEffect, useRef } from 'react';

function ellipsizeMiddle(text, maxLen = 26) {
  if (!text) return '';
  const str = String(text);
  if (str.length <= maxLen) return str;
  const headLen = Math.max(6, Math.ceil((maxLen - 3) / 2));
  const tailLen = Math.max(4, Math.floor((maxLen - 3) / 2));
  return `${str.slice(0, headLen)}...${str.slice(-tailLen)}`;
}

function FolderIcon({ size = 16, color = '#8A7F76' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M2.5 6.8A1.8 1.8 0 0 1 4.3 5h3.2l1.4 1.8h6.8A1.8 1.8 0 0 1 17.5 8.6v6.8a1.8 1.8 0 0 1-1.8 1.8H4.3a1.8 1.8 0 0 1-1.8-1.8V6.8Z" stroke={color} strokeWidth="1.45" strokeLinejoin="round" />
      <path d="M2.8 9h14.4" stroke={color} strokeWidth="1.45" strokeLinecap="round" />
    </svg>
  );
}

function ChevronIcon({ direction = 'down', size = 12, color = '#8A7F76' }) {
  const rotate = direction === 'up' ? 180 : direction === 'right' ? -90 : direction === 'left' ? 90 : 0;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      style={{ transform: `rotate(${rotate}deg)`, transition: 'transform 0.2s ease' }}
      aria-hidden="true"
    >
      <path d="M2 4.2L6 8L10 4.2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PanelToggleIcon({ collapsed = false, color = '#5A504A' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="2.25" width="13" height="11.5" rx="2" stroke={color} strokeWidth="1.2" />
      <path d="M5.8 2.25V13.75" stroke={color} strokeWidth="1.2" />
      {collapsed ? (
        <path d="M8.4 8L6.9 6.7V9.3L8.4 8Z" fill={color} />
      ) : (
        <path d="M7.4 8L8.9 6.7V9.3L7.4 8Z" fill={color} />
      )}
    </svg>
  );
}

function MoreIcon({ color = '#6B615B' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="4" cy="8" r="1.2" fill={color} />
      <circle cx="8" cy="8" r="1.2" fill={color} />
      <circle cx="12" cy="8" r="1.2" fill={color} />
    </svg>
  );
}

function RenameIcon({ color = '#6B615B' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 11.8L4 9.1L10.5 2.6A1.4 1.4 0 0 1 12.5 4.6L6 11.1L3 11.8Z" stroke={color} strokeWidth="1.35" strokeLinejoin="round" />
      <path d="M9.4 3.7L11.4 5.7" stroke={color} strokeWidth="1.35" strokeLinecap="round" />
    </svg>
  );
}

function TrashIcon({ color = '#8B2E1F' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2.7 4.6H13.3" stroke={color} strokeWidth="1.35" strokeLinecap="round" />
      <path d="M6.2 2.8H9.8" stroke={color} strokeWidth="1.35" strokeLinecap="round" />
      <path d="M4.2 4.6L4.9 12.7A1.2 1.2 0 0 0 6.1 13.8H9.9A1.2 1.2 0 0 0 11.1 12.7L11.8 4.6" stroke={color} strokeWidth="1.35" strokeLinejoin="round" />
      <path d="M6.6 7.1V11.2M9.4 7.1V11.2" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function CogIcon({ color = '#6B615B' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 2.2L8.7 3.7L10.4 3.9L10.7 5.6L12.2 6.3L11.5 7.8L12.2 9.3L10.7 10L10.4 11.7L8.7 11.9L8 13.4L7.3 11.9L5.6 11.7L5.3 10L3.8 9.3L4.5 7.8L3.8 6.3L5.3 5.6L5.6 3.9L7.3 3.7L8 2.2Z" stroke={color} strokeWidth="1.15" strokeLinejoin="round" />
      <circle cx="8" cy="7.8" r="1.9" stroke={color} strokeWidth="1.15" />
    </svg>
  );
}

function WorkspaceIcon({ color = '#5A504A' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="2" y="2.2" width="12" height="11.6" rx="2.1" stroke={color} strokeWidth="1.2" />
      <path d="M2.4 6.2H13.6" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M5.2 4.2H6.8" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
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
  onChatDelete,
  onChatRename,
  collapsed,
  onToggleCollapse,
  onOpenSettings
}) {
  const [categoryExpanded, setCategoryExpanded] = useState({});
  const [folderDropdownOpen, setFolderDropdownOpen] = useState(false);
  const [chatMenuOpen, setChatMenuOpen] = useState(null); // {category, id} | null
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const dropdownRef = useRef(null);
  const chatMenuRef = useRef(null);
  const profileMenuRef = useRef(null);
  const safeFolders = Array.isArray(folders) ? folders.map((f) => {
    if (typeof f === 'string') {
      return { id: f, name: f, kind: 'auto', path: f };
    }
    return f;
  }).filter(Boolean) : [];
  const safeConversations = conversations && typeof conversations === 'object' ? conversations : {};
  const currentFolderObj = safeFolders.find((f) => f.id === currentFolder);
  const currentFolderLabel = currentFolderObj?.name || currentFolder || '';
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

  // 点击外部关闭对话菜单
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!chatMenuOpen) return;
      if (chatMenuRef.current && !chatMenuRef.current.contains(event.target)) {
        setChatMenuOpen(null);
      }
    };

    if (chatMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [chatMenuOpen]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!profileMenuOpen) return;
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setProfileMenuOpen(false);
      }
    };

    if (profileMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [profileMenuOpen]);

  return (
    <div style={{
      width: collapsed ? '60px' : '280px',
      transition: 'width 0.3s ease',
      borderRight: '1px solid #E5E0DB',
      display: 'flex',
      flexDirection: 'column',
      background: '#F4F1EC',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '1px 0 3px rgba(0, 0, 0, 0.02)'
    }}>
      {/* 顶栏：品牌 + 侧栏开关（与主区顶栏统一高度） */}
      <div style={{
        height: 'var(--topbar-h)',
        padding: '0 14px',
        borderBottom: 'none',
        background: '#F8F5F1',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        gap: '8px',
        minWidth: 0,
        boxSizing: 'border-box'
      }}>
        {!collapsed && (
          <div style={{
            fontFamily: 'var(--font-reading)',
            fontSize: '32px',
            lineHeight: 1,
            letterSpacing: '-0.012em',
            color: '#1F1A16',
            fontWeight: '560',
            userSelect: 'none',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            UniteChat
          </div>
        )}
        
        <button
          onClick={onToggleCollapse}
          style={{
            padding: '8px',
            border: '1px solid #DDD5CB',
            background: '#FFFFFF',
            cursor: 'pointer',
            fontSize: '16px',
            lineHeight: 1,
            color: '#5A504A',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '9px',
            transition: 'background-color 0.06s',
            minWidth: '32px',
            minHeight: '32px'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#F3EEE6';
            e.currentTarget.style.borderColor = '#CEC3B6';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = '#FFFFFF';
            e.currentTarget.style.borderColor = '#DDD5CB';
          }}
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          <PanelToggleIcon collapsed={collapsed} />
        </button>
      </div>

      {/* 对话列表 - Claude 风格 */}
      {!collapsed && (
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px 10px 10px'
        }}>
          <div ref={dropdownRef} style={{ marginBottom: '10px', position: 'relative' }}>
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
              title={currentFolderLabel}
            >
              <span style={{ fontSize: '16px', color: '#8A7F76', flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                <FolderIcon />
              </span>

              <span style={{
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}>
                {ellipsizeMiddle(currentFolderLabel, 24)}
              </span>

              <span style={{ flexShrink: 0, pointerEvents: 'none', display: 'flex', alignItems: 'center' }}>
                <ChevronIcon direction={folderDropdownOpen ? 'up' : 'down'} />
              </span>
            </div>

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
                    key={folder.id}
                    onClick={() => {
                      onFolderChange(folder.id);
                      setFolderDropdownOpen(false);
                    }}
                    style={{
                      padding: '10px 14px',
                      cursor: 'pointer',
                      fontSize: '13.5px',
                      color: '#2A2523',
                      background: currentFolder === folder.id ? '#F2EDE7' : 'transparent',
                      fontWeight: currentFolder === folder.id ? '600' : '400',
                      transition: 'background-color 0.06s',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      borderBottom: index === safeFolders.length - 1 ? 'none' : '1px solid #F2EDE7'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = currentFolder === folder.id ? '#E8E3DB' : '#F7F5F2';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = currentFolder === folder.id ? '#F2EDE7' : 'transparent';
                    }}
                      title={folder.path || folder.name || folder.id}
                    >
                    {folder.name || folder.id}
                  </div>
                ))}
              </div>
            )}
          </div>

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
                    marginLeft: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    <ChevronIcon direction={isExpanded ? 'down' : 'right'} size={10} color="#8A7F76" />
                    {chatList.length}
                  </span>
                </div>

                {/* 对话列表 - Claude风格 */}
                {isExpanded && (
                  <div style={{
                    marginLeft: '10px',
                    marginTop: '4px'
                  }}>
                    {chatList.map(chat => {
                      const canEdit = (chat?.can_edit !== false);
                      return (
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
                            fontWeight: selectedChat === chat.id ? '500' : '400',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            minWidth: 0,
                            position: 'relative'
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
                        <span style={{
                          flex: '1 1 auto',
                          minWidth: 0,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {chat.title}
                        </span>

                        {canEdit && (
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            const key = { category, id: chat.id };
                            const same = chatMenuOpen && chatMenuOpen.category === key.category && chatMenuOpen.id === key.id;
                            setChatMenuOpen(same ? null : key);
                          }}
                          style={{
                            flex: '0 0 auto',
                            border: 'none',
                            background: 'transparent',
                            cursor: 'pointer',
                            padding: '2px 6px',
                            borderRadius: '8px',
                            color: '#6B615B',
                            fontSize: '16px',
                            lineHeight: 1,
                            opacity: 0.75
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'rgba(42, 37, 35, 0.06)';
                            e.currentTarget.style.opacity = 1;
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.opacity = 0.75;
                          }}
                          title="更多操作"
                        >
                          <MoreIcon />
                        </button>
                        )}

                        {canEdit && chatMenuOpen && chatMenuOpen.category === category && chatMenuOpen.id === chat.id && (
                          <div
                            ref={chatMenuRef}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                            style={{
                              position: 'absolute',
                              right: '10px',
                              top: '100%',
                              marginTop: '6px',
                              zIndex: 50,
                              background: '#FFFFFF',
                              border: '1px solid #E5E0DB',
                              borderRadius: '12px',
                              boxShadow: '0 10px 30px rgba(42, 37, 35, 0.12)',
                              padding: '8px',
                              minWidth: '150px'
                            }}
                          >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (typeof onChatRename === 'function') onChatRename(chat.id, category, chat.title);
                                setChatMenuOpen(null);
                              }}
                              style={{
                                width: '100%',
                                border: '1px solid #E9E3DC',
                                cursor: 'pointer',
                                padding: '9px 11px',
                                borderRadius: '10px',
                                background: '#FFFFFF',
                                color: '#2A2523',
                                fontWeight: '560',
                                fontSize: '13.5px',
                                textAlign: 'left',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = '#F7F3EE';
                                e.currentTarget.style.borderColor = '#DDD3C8';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = '#FFFFFF';
                                e.currentTarget.style.borderColor = '#E9E3DC';
                              }}
                              title="重命名"
                            >
                              <span style={{ width: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><RenameIcon color="#6B615B" /></span>
                              <span>重命名</span>
                            </button>

                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (typeof onChatDelete === 'function') onChatDelete(chat.id, category);
                                setChatMenuOpen(null);
                              }}
                              style={{
                                width: '100%',
                                border: '1px solid #F0DAD5',
                                cursor: 'pointer',
                                padding: '9px 11px',
                                borderRadius: '10px',
                                background: '#FFF9F8',
                                color: '#8B2E1F',
                                fontWeight: '560',
                                fontSize: '13.5px',
                                textAlign: 'left',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = '#FDEDE9';
                                e.currentTarget.style.borderColor = '#E9BEB6';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = '#FFF9F8';
                                e.currentTarget.style.borderColor = '#F0DAD5';
                              }}
                              title="删除"
                            >
                              <span style={{ width: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><TrashIcon /></span>
                              <span>删除</span>
                            </button>
                            </div>
                          </div>
                        )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div
        ref={profileMenuRef}
        style={{
          position: 'relative',
          borderTop: '1px solid #E5E0DB',
          padding: collapsed ? '10px 8px' : '10px',
          background: '#F8F5F1'
        }}
      >
        <button
          type="button"
          onClick={() => setProfileMenuOpen((v) => !v)}
          style={{
            width: '100%',
            border: '1px solid #DDD5CB',
            background: '#FFFFFF',
            borderRadius: '11px',
            cursor: 'pointer',
            minHeight: '40px',
            padding: collapsed ? '0' : '8px 10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'space-between',
            color: '#2A2523',
            fontSize: '13.5px',
            fontWeight: 600,
            gap: '8px'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#F7F3EE';
            e.currentTarget.style.borderColor = '#CEC3B6';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = '#FFFFFF';
            e.currentTarget.style.borderColor = '#DDD5CB';
          }}
          title="工作区菜单"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
            <WorkspaceIcon />
            {!collapsed && (
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                本地工作区
              </span>
            )}
          </span>
          {!collapsed && <ChevronIcon direction={profileMenuOpen ? 'up' : 'down'} size={10} color="#8A7F76" />}
        </button>

        {profileMenuOpen && (
          <div
            style={{
              position: 'absolute',
              left: collapsed ? 'calc(100% + 6px)' : '10px',
              right: collapsed ? 'auto' : '10px',
              bottom: 'calc(100% + 6px)',
              minWidth: collapsed ? '170px' : 'auto',
              background: '#FFFFFF',
              border: '1px solid #E5E0DB',
              borderRadius: '12px',
              boxShadow: '0 10px 30px rgba(42, 37, 35, 0.12)',
              padding: '8px',
              zIndex: 1200,
              transformOrigin: collapsed ? 'left bottom' : 'center bottom',
              animation: 'popInSoft 0.18s cubic-bezier(0.22, 1, 0.36, 1)'
            }}
          >
            <button
              type="button"
              onClick={() => {
                if (typeof onOpenSettings === 'function') onOpenSettings();
                setProfileMenuOpen(false);
              }}
              style={{
                width: '100%',
                border: '1px solid #E9E3DC',
                cursor: 'pointer',
                padding: '9px 11px',
                borderRadius: '10px',
                background: '#FFFFFF',
                color: '#2A2523',
                fontWeight: '560',
                fontSize: '13.5px',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#F7F3EE';
                e.currentTarget.style.borderColor = '#DDD3C8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#FFFFFF';
                e.currentTarget.style.borderColor = '#E9E3DC';
              }}
              title="设置"
            >
              <span style={{ width: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CogIcon />
              </span>
              <span>Settings</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default Sidebar;
