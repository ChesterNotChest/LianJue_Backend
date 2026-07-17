## Why

当前前端只有两个核心页面——银河 3D 可视化（`/`）和 Agent 对话（`/learn/:id`）——且使用两套割裂的配色主题。审稿人反馈"像工具，不像完整软件，缺少门户，构建割裂"。需要在课程体系成型前，将前端重构为有门户感的教学平台。

## What Changes

- **BREAKING**: 路由重建——`/` 从银河首页改为 Dashboard，银河迁至 `/galaxy`（全课程总览）和 `/learn/:id/galaxy`（单课程知识图谱）
- 新增 Dashboard 门户页：课程卡片 grid + 进度条 + 创建 CTA + 可滚动到银河预览
- 新增学科页左栏导航（CourseLayout）：学科首页、教学大纲、AI 学习、学习成长树、知识图谱
- Agent 页面精简：原有右栏 6 个 tab 拆散到对应子页面；学伴提升为全局浮动组件
- 主题统一：全部页面使用 Agent 页面浅色主题（Indigo token），仅 Galaxy 保留深色太空主题
- 管理页配色同步为 Agent 主题
- 后端新增 `POST /api/knowledge/video_search` 端点，对接 B站搜索

## Capabilities

### New Capabilities
- `video-search`: 后端视频搜索 API，封装 B站检索，返回归一化结果（标题、缩略图、链接、时长、来源、作者）
- `dashboard`: 前端门户仪表盘，课程卡片展示、进度聚合、银河预览入口

### Modified Capabilities
<!-- No existing spec requirements change — backend APIs remain the same, only frontend arrangement changes -->

## Impact

- **前端路由**: `src/App.tsx` 重构，新增 5 条路由，`/` 和 `/learn/:id` 语义变更
- **前端组件**: 新增 `Dashboard`、`SubjectHome`、`SyllabusPage`、`LearningTreePage`；`AgentLayout` 精简为 2 栏；`SubjectOverview` 拆分
- **后端新增**: `blueprint/learning_api.py` 新增 `/api/knowledge/video_search`
- **主题**: `index.css` 主题 token 不变；`lianjue.css` 的 `.kg-*` 类仅用于 Galaxy 页面
- **不受影响**: 管理页路由结构不变，仅配色调整；所有后端 Agent/Task API 不变
