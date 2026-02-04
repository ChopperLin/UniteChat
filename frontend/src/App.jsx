import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatView from './components/ChatView';
import SearchModal from './components/SearchModal';
import RenameModal from './components/RenameModal';
import axios from 'axios';

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
  const [shuttingDown, setShuttingDown] = useState(false);
  const [renameState, setRenameState] = useState({ open: false, chatId: null, category: null, title: '' });

  // 加载文件夹列表
  useEffect(() => {
    axios.get('/api/folders')
      .then(response => {
        const foldersFromApi = Array.isArray(response?.data?.folders) ? response.data.folders : [];
        setFolders(foldersFromApi);
        setCurrentFolder(response?.data?.current || foldersFromApi[0] || '');
        console.log('文件夹列表加载成功:', response.data);
      })
      .catch(error => {
        console.error('加载文件夹列表失败:', error);
      });
  }, []);

  // 当切换文件夹时，重新加载对话列表
  useEffect(() => {
    if (currentFolder) {
      loadConversations(currentFolder);
    }
  }, [currentFolder]);

  // 加载对话列表
  const loadConversations = (folder) => {
    axios.get(`/api/conversations?folder=${folder}`)
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
    axios.post(`/api/folders/${folder}`)
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
    axios.get(`/api/chat/${chatId}?category=${category}&folder=${folderParam}`)
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

  const deleteChat = async (chatId, category) => {
    if (!chatId || !category) return;

    const ok = window.confirm('确定要删除这条对话记录吗？（不可恢复）');
    if (!ok) return;

    try {
      const folderParam = currentFolder;
      await axios.delete(`/api/chat/${chatId}?category=${encodeURIComponent(category)}&folder=${encodeURIComponent(folderParam)}`);
      if (selectedChat === chatId) {
        setSelectedChat(null);
        setChatData(null);
      }
      loadConversations(folderParam);
    } catch (e) {
      console.error('删除对话失败:', e);
      window.alert(`删除失败：${e?.response?.data?.error || e?.message || 'unknown error'}`);
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
        `/api/chat/${chatId}?category=${encodeURIComponent(category)}&folder=${encodeURIComponent(folderParam)}`,
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
    const ok = window.confirm('确定要退出并停止服务吗？');
    if (!ok) return;
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
      });
  };

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'sans-serif' }}>
      <Sidebar
        folders={folders}
        currentFolder={currentFolder}
        onFolderChange={handleFolderChange}
        conversations={conversations}
        selectedCategory={selectedCategory}
        onCategoryChange={setSelectedCategory}
        selectedChat={selectedChat}
        onChatSelect={(chatId) => loadChat(chatId, selectedCategory)}
        onChatDelete={(chatId, category) => deleteChat(chatId, category)}
        onChatRename={(chatId, category, currentTitle) => openRename(chatId, category, currentTitle)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
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
        onClose={() => setSearchOpen(false)}
        onSelect={async (r) => {
          if (!r?.id || !r?.category) return;
          const targetFolder = r.folder || currentFolder;
          if (targetFolder && targetFolder !== currentFolder) {
            try {
              await axios.post(`/api/folders/${targetFolder}`);
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
    </div>
  );
}

export default App;
