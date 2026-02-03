# Claude/Gemini 导出支持实现计划（保持前端不变）

## 目标与约束
- 目标：在不修改前端 UI/接口使用方式的前提下，让应用能够浏览与搜索三种来源：ChatGPT（已支持）、Claude（data-*）、Gemini（takeout-*，含大量图片/附件）。
- 关键约束：前端现有渲染与数据结构保持不变；后端需要把不同来源统一归一化为同一种会话结构：`{ title, messages, meta }`，其中 `messages[]` 至少包含 `{ role, content }`（可选 `ts`）。

## 现状（本轮已完成）
- 后端已加入“多源探测 + 分流 + 归一化”：
  - Claude：读取 `conversations.json`，按 `uuid` 建索引，虚拟成可打开的会话列表。
  - Gemini：解析 Takeout 的 `MyActivity.html`，把每条活动记录虚拟成“会话”（一问一答），并提取附件/图片。
  - ChatGPT：保持原逻辑（每对话一个 JSON 文件）。
- 已新增附件访问端点：`/api/file?folder=...&path=...`，用于 Gemini 图片/文件在 Markdown 中直接渲染（前端无需改动）。
- 已扩展搜索索引：Claude/Gemini 也能被 `/api/search` 覆盖（基于归一化后的文本）。

## 数据格式要点
### Claude（data-*）
- 核心文件：`conversations.json`（单个大 JSON，包含会话数组）。
- 每个 conversation：`uuid/name/created_at/updated_at/chat_messages/...`
- 每条 message：`sender`（常见 human/assistant）、`content`（list，常见 `type==text`）等。

### Gemini（takeout-*）
- 核心文件：`Takeout/My Activity/Gemini Apps/MyActivity.html`
- 每条记录通常含：Prompt、时间戳、回复 HTML、附件链接 `<a href="...">`、以及预览 `<img src="...">`。

## 后端改造方案（保持前端不变）
1. **目录扫描层（scanner）**
   - 对每个数据目录做类型探测：
     - ChatGPT：默认（多 JSON 文件）。
     - Claude：存在 `conversations.json`。
     - Gemini：存在 `MyActivity.html`（或可扩展 `MyActivity.json`）。
   - 对 Claude/Gemini 返回“虚拟会话列表”：仍按现有接口返回 `category -> [ {id,title,ts,...} ]`。

2. **解析/加载层（external_sources）**
   - Claude：加载 `conversations.json` 并缓存（按 mtime 失效）。
   - Gemini：解析 `MyActivity.html` 并缓存（按 mtime 失效）。
   - 统一提供：`by_uuid/by_id` 的索引，便于 routes 快速定位记录。

3. **归一化层（normalize）**
   - Claude：把 `chat_messages` 映射到 `messages[]`（human->user，其它->assistant），抽取文本内容，带 `ts`。
   - Gemini：把每条活动记录映射成两条消息（user prompt + assistant response），并把附件/图片生成 Markdown 链接/图片语法，指向 `/api/file`。

4. **路由层（routes）**
   - `/api/chat/<id>`：根据 scanner 的 source resolve 分流到三种解析路径，最终都输出 `{title,messages,meta}`。
   - `/api/file`：安全提供 Gemini 附件文件访问（禁止路径穿越）。

5. **搜索层（search）**
   - ChatGPT：继续对 `*.json` 做索引。
   - Claude/Gemini：直接基于归一化结果构建索引文本（标题+消息内容），并建立 token/CJK posting list。

## 验证清单（建议按顺序）
- 基础浏览：
  - `GET /api/folders` 能看到 data 下所有顶层目录。
  - `GET /api/conversations?folder=...`：
    - ChatGPT 目录：维持原分类/列表。
    - Claude/Gemini 目录：能返回虚拟列表（目前统一放在“全部”分类）。
  - `GET /api/chat/<id>?folder=...&category=...`：三种来源都能打开且前端正常渲染。
- Gemini 图片：
  - 打开包含图片的记录，Markdown 中 `![](/api/file?...)` 能正常显示。
- 搜索：
  - `GET /api/search?folder=...&q=...` 能在三种来源下返回结果。

## 后续优化（非必须，但推荐）
- Claude 大文件性能：当前 Claude 采用 `json.load` 全量加载，若内存/启动耗时较高，可改为流式解析（如 `ijson`）或建立磁盘级索引缓存。
- Gemini JSON 支持：若 Takeout 同时提供 `MyActivity.json`，可补充 JSON 解析路径，作为 HTML 解析的替代/兜底。
- 分类体验：Claude/Gemini 目前统一放在“全部”分类，可基于日期（按月/按天）或标签拆分为多级分类，前端无需改动。
- 增量索引：监听文件变更时仅重建受影响目录的索引，减少全量扫描。
