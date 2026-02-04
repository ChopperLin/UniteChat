#  UniteChat

一个优雅的本地 Web 应用，用于浏览和管理 ChatGPT 导出的对话记录。支持按文件夹/分类浏览、Markdown/LaTeX 公式/代码高亮渲染，以及 ChatGPT 风格的引用系统。

##  核心特性

-  **智能组织**：自动扫描并按文件夹和分类组织对话记录
-  **富文本渲染**：完整支持 Markdown、LaTeX 数学公式、代码语法高亮
-  **引用系统**：解析并美化 ChatGPT 导出中的引用标记，点击查看引用卡片并左右切换
-  **便捷浏览**：清晰的对话树结构，轻松回溯完整上下文
-  **性能优化**：前后端分离架构，快速响应

##  技术栈

**前端**
- React 18 + Vite
- React Markdown + KaTeX + Highlight.js
- Axios + 现代化 CSS

**后端**
- Flask 3.0 + Python 3.10+
- 对话树解析与引用处理
- RESTful API 设计

##  项目结构

```
GPT_Chat_Browser/
 data/                           # 数据目录（.gitignore）
    chatgpt_team_chat_1231/     # ChatGPT 导出数据
        AI/                     # 分类文件夹
        CS/
        GameDev/
        ...
 backend/                        # Flask 后端
    run.py                      # 启动入口
    config.py                   # 配置管理
    requirements.txt            # Python 依赖
    audit_citations.py          # 引用审计工具
    app/
        routes.py               # API 路由
        scanner.py              # 目录扫描
        parser.py               # 对话解析 & 引用处理
        search.py               # 搜索功能
        utils.py                # 工具函数
 frontend/                       # React 前端
    index.html
    package.json
    vite.config.js
    src/
        App.jsx                 # 主应用
        main.jsx
        components/             # React 组件
 setup.bat                       # 环境配置脚本
 start.bat                       # 一键启动脚本
 stop.bat                        # 停止服务脚本
```

##  快速开始

### 一、环境配置（首次使用）

**前置要求**
- Node.js 18+ ([下载](https://nodejs.org/))
- Python 3.10+ ([下载](https://www.python.org/downloads/))

**自动安装（推荐）**
```bash
.\setup.bat
```

setup.bat 会自动完成：
-  检查 Python 和 Node.js 环境
-  创建 Python 虚拟环境
-  安装所有后端依赖
-  安装所有前端依赖

**手动安装（可选）**
```bash
# 后端环境
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 前端环境
cd frontend
npm install
```

### 二、准备数据

将 ChatGPT 导出的对话数据放入 `data/` 目录：

```
data/
 chatgpt_team_chat_1231/          # 导出文件夹
     AI/                          # 分类子文件夹
        神经网络核心思想_bbbac7f9f93c.json
        Transformer工作原理解释_ee80e43e5561.json
     CS/
     GameDev/
```

### 三、启动应用

```bash
# 一键启动前后端服务
.\start.bat

# 停止所有服务
.\stop.bat
```

启动后访问：
-  **前端界面**：http://localhost:3847
-  **后端 API**：http://127.0.0.1:5847/api/health

> 说明：端口可通过环境变量覆盖：`BACKEND_HOST`、`BACKEND_PORT`。前端端口可通过 `VITE_PORT` 覆盖。

## Gemini 导出支持（普通对话 / Deep Research）

本项目支持解析 `data/gemini_export_*/*.json`（Google Gemini Web 导出的 `batchexecute_raw`）。

**前端依赖的字段契约**
- `messages[].content`：主展示正文（最终回答/报告，永远优先展示）
- `messages[].thinking`（可选）：思考过程步骤数组（用于 `ThinkingBlock` 展示；不会把最终回答误放进去）

**回归校验（推荐）**
```bash
D:/UGit/UniteChat/.venv/Scripts/python.exe scripts/verify_gemini_parsing.py
D:/UGit/UniteChat/.venv/Scripts/python.exe scripts/smoke_gemini_exports.py --limit 80
```

### 四、单独启动（开发调试）

**后端**
```bash
cd backend
venv\Scripts\python run.py
```

**前端**
```bash
cd frontend
npm run dev
```

##  核心概念

### 数据结构

后端扫描路径：`data/<folder>/<category>/*.json`

- **folder**：ChatGPT 导出目录（如 `chatgpt_team_chat_1231`）
- **category**：分类文件夹（如 `AI`、`CS`、`GameDev`）
- **文件**：格式为 `标题_<id>.json` 的对话记录

### 引用系统（Citations）

ChatGPT 导出中的引用标记有多种形式：
- **私有区字符**：`citeturn0...`（Unicode `\ue200/\ue202/\ue201`）
- **Unicode 变体**：`citeturn0...`
- **纯文本形式**：`citeturn0...`

**处理机制**
- 自动识别并转换为可点击的引用标记（citation pill）
- 链接到实际 URL（从 `metadata.content_references` 提取）
- 引用数据以 JSON 格式存储在 Markdown `title` 属性中
- 前端渲染为可切换的引用卡片

**已知限制**
- 部分导出数据中的引用缺少可用 URL（`items.url/safe_urls` 为空）
- 此类情况会降级处理或清除标记

##  开发指南

### API 端点

```
GET  /api/health              # 健康检查
GET  /api/folders             # 获取所有文件夹列表
GET  /api/conversations       # 获取指定文件夹下的对话列表
GET  /api/conversation/<id>   # 获取单个对话详情
```

### 关键模块

| 模块 | 文件路径 | 说明 |
|------|---------|------|
| API 路由 | `backend/app/routes.py` | RESTful API 端点 |
| 对话解析 | `backend/app/parser.py` | 解析对话树结构 |
| 引用处理 | `backend/app/parser.py::_process_citations()` | Citations 解析与转换 |
| 目录扫描 | `backend/app/scanner.py` | 扫描数据文件夹 |
| 前端组件 | `frontend/src/components/` | React 组件库 |

### 引用审计工具

验证引用标记的完整性和一致性：

```bash
cd backend
venv\Scripts\python audit_citations.py --root ../data/chatgpt_team_chat_1231 --out audit_report.json
```

**输出内容**
- 控制台统计摘要
- 问题最多的对话列表（Top offenders）
- 详细审计报告（`audit_report.json`）

### 前端代理配置

Vite 开发服务器已配置 API 代理（`vite.config.js`）：
```javascript
proxy: {
  '/api': {
      target: `http://${process.env.BACKEND_HOST || '127.0.0.1'}:${process.env.BACKEND_PORT || '5847'}`,
    changeOrigin: true
  }
}
```

##  功能路线图

-  基础对话浏览
-  引用系统
-  Markdown 渲染
-  代码高亮
-  LaTeX 公式支持
-  全文搜索
-  收藏与标签
-  导出功能
-  主题切换

##  贡献

欢迎提出建议和改进！如果你想添加新功能（UI 优化/搜索/索引/标签系统等），请：

1. Fork 本项目
2. 创建特性分支
3. 提交 Pull Request

##  许可证

MIT License

---

**提示**：首次使用请运行 `setup.bat` 安装依赖，之后使用 `start.bat` 启动，`stop.bat` 停止服务。
