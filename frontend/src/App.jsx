import React, { useState, useEffect, useMemo, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ChatView from './components/ChatView';
import SearchModal from './components/SearchModal';
import RenameModal from './components/RenameModal';
import SettingsModal from './components/SettingsModal';
import ConfirmDialog from './components/ConfirmDialog';
import axios from 'axios';

function normalizeFolders(rawFolders) {
  const input = Array.isArray(rawFolders) ? rawFolders : [];
  return input
    .map((item, index) => {
      if (typeof item === 'string') {
        return {
          id: item,
          name: item,
          kind: 'auto',
          path: item,
          order: index,
        };
      }
      if (!item || typeof item !== 'object') return null;
      const id = String(item.id || '').trim();
      if (!id) return null;
      return {
        id,
        name: String(item.name || id),
        kind: String(item.kind || 'auto'),
        path: String(item.path || ''),
        order: index,
      };
    })
    .filter(Boolean);
}

function App() {
  const [folders, setFolders] = useState([]);
  const [currentFolder, setCurrentFolder] = useState('');
  const [conversations, setConversations] = useState({});
  const [selectedCategory, setSelectedCategory] = useState('AI');
  const [selectedChat, setSelectedChat] = useState(null);
  const [chatData, setChatData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [renameState, setRenameState] = useState({ open: false, chatId: null, category: null, title: '' });
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, chatId: '', category: '' });
  const [shutdownConfirmOpen, setShutdownConfirmOpen] = useState(false);
  const [uiNotice, setUiNotice] = useState({ open: false, title: '', message: '' });
  const [deletingChat, setDeletingChat] = useState(false);
  const prewarmAllOnceRef = useRef(false);
  const folderNameById = useMemo(() => {
    const map = new Map();
    for (const f of folders) {
      map.set(f.id, f.name || f.id);
    }
    return map;
  }, [folders]);
  const currentFolderLabel = folderNameById.get(currentFolder) || currentFolder || '';

  const applyFoldersPayload = (payload, preferredFolderId = '') => {
    const foldersFromApi = normalizeFolders(payload?.folders);
    setFolders(foldersFromApi);

    const firstFolderId = foldersFromApi[0]?.id || '';
    const requested = String(preferredFolderId || '').trim();
    const fromApiCurrent = String(payload?.current || '').trim();
    const prevCurrent = String(currentFolder || '').trim();

    const exists = (id) => Boolean(id) && foldersFromApi.some((f) => f.id === id);
    const nextCurrent = exists(requested)
      ? requested
      : exists(fromApiCurrent)
        ? fromApiCurrent
        : exists(prevCurrent)
          ? prevCurrent
          : firstFolderId;

    if (nextCurrent !== currentFolder) {
      setSelectedChat(null);
      setChatData(null);
      setConversations({});
    }
    setCurrentFolder(nextCurrent || '');

    if (!prewarmAllOnceRef.current && foldersFromApi.length > 1) {
      prewarmAllOnceRef.current = true;
      const run = () => {
        axios.get('/api/search/prewarm', { params: { scope: 'all' } }).catch(() => {});
      };
      if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(run, { timeout: 1500 });
      } else {
        setTimeout(run, 400);
      }
    }
  };

  const fetchFolders = (preferredFolderId = '') => {
    axios.get('/api/folders')
      .then(response => {
        applyFoldersPayload(response?.data || {}, preferredFolderId);
        console.log('文件夹列表加载成功:', response.data);
      })
      .catch(error => {
        console.error('加载文件夹列表失败:', error);
      });
  };

  // 加载文件夹列表
  useEffect(() => {
    fetchFolders();
  }, []);

  // 当切换文件夹时，重新加载对话列表
  useEffect(() => {
    if (currentFolder) {
      loadConversations(currentFolder);
    }
  }, [currentFolder]);

  // 加载对话列表
  const loadConversations = (folder) => {
    axios.get(`/api/conversations?folder=${encodeURIComponent(folder)}`)
      .then(response => {
        setConversations(response.data);
        console.log('对话列表加载成功:', response.data);
        // 如果当前分类不存在，切换到第一个可用分类
        if (!response.data[selectedCategory]) {
          const firstCategory = Object.keys(response.data)[0];
          if (firstCategory) {
            setSelectedCategory(firstCategory);
          }
        }
      })
      .catch(error => {
        console.error('加载对话列表失败:', error);
      });
  };

  // 切换文件夹
  const handleFolderChange = (folder) => {
    axios.post(`/api/folders/${encodeURIComponent(folder)}`)
      .then(() => {
        setCurrentFolder(folder);
        setSelectedChat(null);
        setChatData(null);
      })
      .catch(error => {
        console.error('切换文件夹失败:', error);
      });
  };

  // 加载对话详情
  const loadChat = (chatId, category, folderOverride) => {
    setLoading(true);
    setSelectedChat(chatId);

    const folderParam = folderOverride || currentFolder;
    axios.get(`/api/chat/${encodeURIComponent(chatId)}?category=${encodeURIComponent(category)}&folder=${encodeURIComponent(folderParam)}`)
      .then(response => {
        setChatData(response.data);
        setLoading(false);
        console.log('对话加载成功:', response.data);
      })
      .catch(error => {
        console.error('加载对话失败:', error);
        setLoading(false);
      });
  };

  const requestDeleteChat = (chatId, category) => {
    if (!chatId || !category) return;
    setDeleteConfirm({ open: true, chatId, category });
  };

  const confirmDeleteChat = async () => {
    if (!deleteConfirm?.chatId || !deleteConfirm?.category) return;
    setDeletingChat(true);
    try {
      const folderParam = currentFolder;
      await axios.delete(
        `/api/chat/${encodeURIComponent(deleteConfirm.chatId)}?category=${encodeURIComponent(deleteConfirm.category)}&folder=${encodeURIComponent(folderParam)}`
      );
      if (selectedChat === deleteConfirm.chatId) {
        setSelectedChat(null);
        setChatData(null);
      }
      setDeleteConfirm({ open: false, chatId: '', category: '' });
      loadConversations(folderParam);
    } catch (e) {
      console.error('删除对话失败:', e);
      setUiNotice({
        open: true,
        title: '删除失败',
        message: e?.response?.data?.error || e?.message || 'unknown error',
      });
    } finally {
      setDeletingChat(false);
    }
  };

  const openRename = (chatId, category, currentTitle) => {
    if (!chatId || !category) return;
    setRenameState({ open: true, chatId, category, title: String(currentTitle || '') });
  };

  const submitRename = async (newTitle) => {
    const chatId = renameState?.chatId;
    const category = renameState?.category;
    if (!chatId || !category) return;

    const folderParam = currentFolder;
    let res;
    try {
      res = await axios.patch(
        `/api/chat/${encodeURIComponent(chatId)}?category=${encodeURIComponent(category)}&folder=${encodeURIComponent(folderParam)}`,
        { title: newTitle }
      );
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || 'unknown error';
      throw new Error(msg);
    }

    if (selectedChat === chatId) {
      setChatData((prev) => (prev ? { ...prev, title: res?.data?.title || newTitle } : prev));
    }

    loadConversations(folderParam);
  };

  // 快捷键：Ctrl+K 打开搜索
  useEffect(() => {
    const onKeyDown = (e) => {
      const key = (e.key || '').toLowerCase();
      const isCtrl = e.ctrlKey || e.metaKey;
      if (!isCtrl) return;
      
      // 只处理 Ctrl+K，让 Ctrl+F 保持浏览器默认的页面搜索功能
      if (key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleShutdown = () => {
    setShutdownConfirmOpen(true);
  };

  const confirmShutdown = () => {
    setShutdownConfirmOpen(false);
    setShuttingDown(true);
    axios.post('/api/shutdown')
      .then(() => {
        console.log('服务关闭请求已发送');
        setTimeout(() => {
          try {
            window.open('', '_self');
            window.close();
          } catch (e) {
            console.error('关闭标签页失败:', e);
          }
        }, 600);
      })
      .catch((error) => {
        console.error('关闭服务失败:', error);
        setShuttingDown(false);
        setUiNotice({
          open: true,
          title: '退出失败',
          message: error?.response?.data?.error || error?.message || 'unknown error',
        });
      });
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <Sidebar
        folders={folders}
        currentFolder={currentFolder}
        onFolderChange={handleFolderChange}
        conversations={conversations}
        selectedCategory={selectedCategory}
        onCategoryChange={setSelectedCategory}
        selectedChat={selectedChat}
        onChatSelect={(chatId) => loadChat(chatId, selectedCategory)}
        onChatDelete={(chatId, category) => requestDeleteChat(chatId, category)}
        onChatRename={(chatId, category, currentTitle) => openRename(chatId, category, currentTitle)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <ChatView
        chatData={chatData}
        loading={loading}
        onOpenSearch={() => setSearchOpen(true)}
        onShutdown={handleShutdown}
        shuttingDown={shuttingDown}
      />

      <SearchModal
        open={searchOpen}
        folder={currentFolder}
        folderLabel={currentFolderLabel}
        onClose={() => setSearchOpen(false)}
        onSelect={async (r) => {
          if (!r?.id || !r?.category) return;
          const targetFolder = r.folder || currentFolder;
          if (targetFolder && targetFolder !== currentFolder) {
            try {
              await axios.post(`/api/folders/${encodeURIComponent(targetFolder)}`);
              setCurrentFolder(targetFolder);
            } catch (e) {
              console.error('切换文件夹失败:', e);
            }
          }
          setSelectedCategory(r.category);
          loadChat(r.id, r.category, targetFolder);
        }}
      />

      <RenameModal
        open={Boolean(renameState?.open)}
        initialTitle={renameState?.title || ''}
        onClose={() => setRenameState({ open: false, chatId: null, category: null, title: '' })}
        onSubmit={submitRename}
      />

      <SettingsModal
        open={settingsOpen}
        currentFolder={currentFolder}
        onClose={() => setSettingsOpen(false)}
        onSaved={(data) => {
          applyFoldersPayload(data || {}, data?.current || currentFolder);
          if (!data?.keep_open) {
            setSettingsOpen(false);
          }
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteConfirm?.open)}
        title="删除对话？"
        message="删除后不可恢复，将从磁盘中移除这条聊天记录。"
        confirmLabel="删除"
        cancelLabel="取消"
        danger
        busy={deletingChat}
        onCancel={() => setDeleteConfirm({ open: false, chatId: '', category: '' })}
        onConfirm={confirmDeleteChat}
      />

      <ConfirmDialog
        open={shutdownConfirmOpen}
        title="停止服务并退出？"
        message="这会停止后端与前端服务。下次使用需要重新启动。"
        confirmLabel="退出"
        cancelLabel="取消"
        danger
        busy={shuttingDown}
        onCancel={() => setShutdownConfirmOpen(false)}
        onConfirm={confirmShutdown}
      />

      <ConfirmDialog
        open={Boolean(uiNotice?.open)}
        title={uiNotice?.title || '提示'}
        message={uiNotice?.message || ''}
        confirmLabel="知道了"
        cancelLabel=""
        busy={false}
        onCancel={() => setUiNotice({ open: false, title: '', message: '' })}
        onConfirm={() => setUiNotice({ open: false, title: '', message: '' })}
      />
    </div>
  );
}

export default App;
