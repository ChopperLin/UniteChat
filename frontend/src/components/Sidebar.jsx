import React, { useState, useEffect, useRef } from 'react';
import './Sidebar.css';

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
    <div className={`sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      {/* 顶栏：品牌 + 侧栏开关（与主区顶栏统一高度） */}
      <div className="sidebar-topbar">
        {!collapsed && (
          <div className="sidebar-brand">UniteChat</div>
        )}
        
        <button
          className="sidebar-toggle-btn"
          onClick={onToggleCollapse}
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          <PanelToggleIcon collapsed={collapsed} />
        </button>
      </div>

      {/* 对话列表 - Claude 风格 */}
      {!collapsed && (
        <div className="sidebar-list">
          <div ref={dropdownRef} className="sidebar-folder-wrap">
            <div
              className={`sidebar-folder-trigger ${folderDropdownOpen ? 'is-open' : ''}`}
              onClick={() => setFolderDropdownOpen(!folderDropdownOpen)}
              tabIndex={0}
              title={currentFolderLabel}
            >
              <span className="sidebar-folder-icon">
                <FolderIcon />
              </span>

              <span className="sidebar-folder-label">
                {ellipsizeMiddle(currentFolderLabel, 24)}
              </span>

              <span className="sidebar-folder-chevron">
                <ChevronIcon direction={folderDropdownOpen ? 'up' : 'down'} />
              </span>
            </div>

            {folderDropdownOpen && (
              <div className="sidebar-folder-menu">
                {safeFolders.map((folder) => (
                  <div
                    key={folder.id}
                    className={`sidebar-folder-option ${currentFolder === folder.id ? 'is-active' : ''}`}
                    onClick={() => {
                      onFolderChange(folder.id);
                      setFolderDropdownOpen(false);
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
              <div key={category} className="sidebar-category">
                {/* 分类标题 - Claude风格 */}
                <div
                  className={`sidebar-category-header ${selectedCategory === category ? 'is-active' : ''}`}
                  onClick={() => {
                    toggleCategory(category, isExpanded);
                    onCategoryChange(category);
                  }}
                >
                  <span>{category}</span>
                  <span className="sidebar-category-meta">
                    <ChevronIcon direction={isExpanded ? 'down' : 'right'} size={10} color="#8A7F76" />
                    {chatList.length}
                  </span>
                </div>

                {/* 对话列表 - Claude风格 */}
                {isExpanded && (
                  <div className="sidebar-chat-list">
                    {chatList.map(chat => {
                      const canEdit = (chat?.can_edit !== false);
                      return (
                        <div
                          key={chat.id}
                          className={`sidebar-chat-item ${selectedChat === chat.id ? 'is-active' : ''}`}
                          onClick={() => onChatSelect(chat.id)}
                        >
                        <span className="sidebar-chat-title">
                          {chat.title}
                        </span>

                        {canEdit && (
                        <button
                          className="sidebar-chat-more-btn"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            const key = { category, id: chat.id };
                            const same = chatMenuOpen && chatMenuOpen.category === key.category && chatMenuOpen.id === key.id;
                            setChatMenuOpen(same ? null : key);
                          }}
                          title="更多操作"
                        >
                          <MoreIcon />
                        </button>
                        )}

                        {canEdit && chatMenuOpen && chatMenuOpen.category === category && chatMenuOpen.id === chat.id && (
                          <div
                            ref={chatMenuRef}
                            className="sidebar-context-menu"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                          >
                            <div className="sidebar-context-inner">
                            <button
                              className="sidebar-context-btn"
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (typeof onChatRename === 'function') onChatRename(chat.id, category, chat.title);
                                setChatMenuOpen(null);
                              }}
                              title="重命名"
                            >
                              <span className="sidebar-context-icon"><RenameIcon color="#6B615B" /></span>
                              <span>重命名</span>
                            </button>

                            <button
                              className="sidebar-context-btn is-danger"
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (typeof onChatDelete === 'function') onChatDelete(chat.id, category);
                                setChatMenuOpen(null);
                              }}
                              title="删除"
                            >
                              <span className="sidebar-context-icon"><TrashIcon /></span>
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

      <div ref={profileMenuRef} className="sidebar-bottom">
        <button
          type="button"
          className="sidebar-workspace-btn"
          onClick={() => setProfileMenuOpen((v) => !v)}
          title="工作区菜单"
        >
          <span className="sidebar-workspace-content">
            <WorkspaceIcon />
            {!collapsed && (
              <span className="sidebar-workspace-label">
                本地工作区
              </span>
            )}
          </span>
          {!collapsed && <ChevronIcon direction={profileMenuOpen ? 'up' : 'down'} size={10} color="#8A7F76" />}
        </button>

        {profileMenuOpen && (
          <div className="sidebar-workspace-popup">
            <button
              type="button"
              className="sidebar-context-btn"
              onClick={() => {
                if (typeof onOpenSettings === 'function') onOpenSettings();
                setProfileMenuOpen(false);
              }}
              title="设置"
            >
              <span className="sidebar-context-icon">
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
