# Design: Frontend Portal Redesign

## Context

当前前端 React 19 + TypeScript + TailwindCSS v4 + Vite 7。两套配色主题：Galaxy 首页（深色太空 `#03040a`）和 Agent 页面（浅色 Indigo `#6366f1`）。路由结构单薄（`/` → 银河，`/learn/:id` → Agent），缺乏传统教学平台的仪表盘入口和课程级导航。

后端 API 能力完整（7 个 spec 覆盖的模块），前端可以基于现有端点聚合数据，无需后端大规模改动。仅需新增一条视频搜索端点。

## Goals / Non-Goals

**Goals:**
- Dashboard 门户页：课程卡片 + 进度 + CTA，让用户从"进入"开始
- 左栏导航学科页：学科首页、教学大纲、AI 学习、成长树、知识图谱可切换
- Agent 页面精简：右栏拆散，学伴提升为全局浮动组件
- 主题统一：除 Galaxy 外全部使用 Agent 浅色主题
- Galaxy 降级为功能页，Dashboard 底部保留银河预览入口

**Non-Goals:**
- 不修改后端 Agent/Task API
- 不重写 Galaxy 3D 渲染逻辑（保留复用）
- 不改变数据模型或数据库 schema
- 不新增前端状态管理库（继续 Zustand）

## Decisions

### Decision 1: Route Architecture

```
旧路由                              新路由
──────────────────────────         ──────────────────────────
/ → SubjectOverview (银河)          / → Dashboard (门户)
                                   /galaxy → FullGalaxy (全课程知识总览)
                                   
/learn/:id → AgentLayout           /learn/:id → CourseLayout (redirect → /home)
  (3栏: 左计划/中对话/右指标)         /learn/:id/home → SubjectHome
                                   /learn/:id/syllabus → SyllabusPage
                                   /learn/:id/agent → AgentChatPanel (精简)
                                   /learn/:id/tree → LearningTreePage
                                   /learn/:id/galaxy → KnowledgeGalaxy (单课程)

/admin/* (不变配色 → Agent主题)      /admin/* (路由不变)
```

**Rationale**: 传统教学平台模式（Dashboard → Course → Sub-pages），用户心智匹配。每个子页面独立路由，支持浏览器前进/后退。

**Alternatives considered**: 单页 tab 切换（无独立 URL）——被否决，因为无法深层链接和浏览器导航。

### Decision 2: Component Tree

```
App.tsx
├── <Dashboard>                          NEW
│   ├── <DashboardHeader>                (logo + user + create CTA)
│   ├── <CourseCardGrid>                 (卡片 grid + 进度条)
│   └── <GalaxyReveal>                   (scroll-triggered parallax reveal)
│
├── <CourseLayout>                       NEW
│   ├── <CourseSidebar>                  (左栏导航: 首页/大纲/AI学习/成长树/知识图谱)
│   └── <Outlet>                         (子路由渲染)
│       ├── <SubjectHome>                NEW
│       │   ├── <CourseMaterials>        (课程资料: 教学大纲 + 知识文档 — 非生成)
│       │   ├── <GeneratedResources>     (AI 生成资源: mindmap/quiz/doc/code/ppt)
│       │   └── <VideoGrid>              (B站视频, video_search API)
│       ├── <SyllabusPage>               NEW (整合)
│       │   ├── <SyllabusTimeline>       (已有)
│       │   ├── <ActivityGantt>          (已有)
│       │   └── <WeeklyStats>            (7d/30d 统计)
│       ├── <AgentChatPanel>             REFACTOR (精简)
│       │   ├── <AgentStatsBar>          (精简 stats: 掌握度/活跃/风险)
│       │   ├── <MessageList>
│       │   ├── <MiniGraphPanel>         (已有)
│       │   ├── <CollapsibleRadar>       (画像雷达, 可折叠)
│       │   └── <CollapsibleKB>          (知识库搜索, 可折叠)
│       ├── <LearningTreePage>           NEW (复用 D3GraphViewer)
│       └── <KnowledgeGalaxy>            REFACTOR (独立页, 深色)
│
├── <FullGalaxy>                         NEW (终身学习图谱, 复用 KnowledgeGalaxy)
│
├── <BuddyFAB>                           NEW (右下角小圆点, 带通知红点)
│
└── <AdminLayout>                        REFACTOR (配色 → Agent主题)
```

### Decision 2b: UI Icon Strategy

全平台使用 **lucide-react 图标库**（项目已引入：`Plus`, `LogOut`, `Shield`, `Activity`, `Database`, `GitBranch`, `Sparkles`, `Loader2` 等）。不使用 emoji 字符作为界面图标。参考成熟教学平台（Coursera、edX）的专业风格——SVG 矢量图标、图文卡片、克制配色。

### Decision 3: Agent 页面精简与内容分配

```
旧 RightSidebar (6 tab)          新位置
─────────────────────────       ─────────────────────
总览 (指标/风险/风格)    → AgentStatsBar (Agent 页顶部 4-5 个关键数字)
活跃 (甘特图/7d/30d)     → SyllabusPage 底部
画像 (雷达图/维度分)     → Agent 页右侧可折叠面板 (默认收起)
日历 (教学大纲/周进度)   → SyllabusPage 主体
文件 (资源仓库)          → SubjectHome "AI 生成资源" 区域
知识库 (RAG 搜索)        → Agent 页右侧可折叠面板 (默认收起)
学伴 (BuddyPanel)        → BuddyFAB (右下角 56px 圆形按钮, 带未读红点)
```

BuddyFAB 点击后弹出**悬浮客服式聊天窗口**（~340×420，固定右下位置，不可拖拽），浮在主内容区上方，不阻断页面操作，可最小化回 FAB。FAB 为全域组件——在任意课程页点击均弹出同一悬浮窗，不导航到 Agent 页。

**自动弹出气泡**：FAB 收到新的主动推送消息时自动弹出气泡展示消息内容（5 秒后自动消失，FAB 保留红点），无需用户 hover。气泡包含消息摘要和指向 FAB 的视觉指示器。

**04-agent SVG 表达**：悬浮窗展开态 + 自动弹出气泡同时可见，展示完整对话流（主动提醒→用户回复→学伴回复→记忆标签写入）。

### Decision 4: Theme Strategy

```
页面                    背景           Accent      Surface     例外
──────────────────────  ────────────  ─────────  ──────────  ──────
Dashboard               slate-50      #6366f1    white       —
CourseLayout (全部子页)  slate-50      #6366f1    white       —
AdminLayout              slate-50      #6366f1    white       —
Galaxy (/galaxy, /:id/galaxy)  #03040a  #38bdf8  rgba(…)   深色太空主题 (唯一例外)
```

Admin 页面的 `.app-shell`、`.space-background` 从深色改为浅色。Galaxy 是全平台唯一使用深色主题的页面，顶部有 subtle indicator 标注。

### Decision 5: Galaxy — 去导航，保留全部可视化

Galaxy 仅去除其导航枢纽角色（左侧课程卡片、管理入口），**全部可视化组件原封保留**：

| 保留 | 说明 |
|------|------|
| KnowledgeGalaxy (3D) | Three.js 星系主体 |
| NebulaOverlay | 学习节点匹配高亮 + 闪烁 (stardust boost) |
| DetailPanel | 右侧节点详情浮窗 |
| GalaxyRotator | 自动旋转 |
| EdgeLayer / KnowledgePoints | 边渲染 / 节点球体 |
| 银河/平面视图切换 | 顶栏 toggle |
| GalaxyBackground | 26K 星场粒子 |

终身学习图谱 (D3 study_graph/detail) 迁移至 Dashboard 滚动流中，不作为独立页面。

路由：
- `/learn/:id/galaxy` — 单课程知识域 (3D, 深色)，底部链接可切换查看全部 graph_ids
- 终身图谱不再独立路由，嵌入 `/` Dashboard 滚动流

### Decision 6: Dashboard Galaxy Scroll-Reveal

Dashboard 底部的银河预览采用 **scroll-triggered parallax reveal** 模式（参考 Apple 产品页的滚动揭示效果）：

- 用户正常看到课程卡片 grid（viewport 内）
- 向下滚动越过卡片区域后，背景从浅色渐变过渡到深色太空背景
- 银河星图（2D Canvas/SVG 静态渲染，非 3D）渐显
- 最底部提供 subtle text link "进入全屏知识总览 →"
- **不是**点击卡片式入口、不是按钮，是滚动浏览的自然延续

实现：`IntersectionObserver` + CSS `background` transition + opacity animation。非 3D 渲染以保证低端设备性能。

### Decision 7: Algorithmic Course Banner Covers

课程卡片封面使用算法生成的 **360×136 横幅图**（非小图标/头像），取代传统的外部图片 URL：

- **输出**: 360×136 SVG 封面横幅，置于课程卡片顶部（类似 eduplus.net 的 `h-136px object-cover` 课程封面）
- **输入**: 课程标题字符串 (e.g. "大数据概论")
- **哈希**: `djb2(title)` → 32-bit uint
- **配色**: `PALETTE[hash % 8]` = {#4f46e5, #0f766e, #b91c1c, #92400e, #1e40af, #6b21a8, #9d174d, #166534}
- **几何背景**: `(hash >> 4) % 4` → {斜线交叉, 矩形堆叠, 同心波纹, 三角重叠} — 半透明白色叠加在纯色背景上
- **排版**: 课程名居中大字（20-24px bold white）+ 副标题（12px semi-transparent white）
- **草稿状态**: 灰色背景 + 无几何图案

每个课程卡片渲染为独立 `<svg>` 组件，零外部依赖。替换旧的 56×56 小图标方案。

### Decision 8: Document Type Thumbnails

资源列表中的缩略图按 `resource_type` 匹配固定 SVG 模板：

| Type | 视觉特征 | 配色 |
|------|---------|------|
| `documents` | 文字行模拟 + 折角 | 蓝 #2563eb |
| `mindmap` | 节点-连线图 | 翠绿 #059669 |
| `quiz` | 问号 + 选项框 | 琥珀 #d97706 |
| `coding_practice` | 代码编辑器窗 (深色) | 紫罗兰 #7c3aed |
| `ppt` | 幻灯片缩略 + 图表 | 红 #dc2626 |

每种类型一个 136×172 SVG 模板，标题和元数据叠加在缩略图下方。

### Decision 9: Dashboard Enrichment

在课程卡片和银河滚动区之间，增加两个内容区块：

- **最近资源** (Recent Resources): 调用 `POST /api/generative_list`（不传 syllabus_id，跨课程），按 `created_at` 倒序取前 4 个。横向排列，每项显示类型缩略图 + 标题 + 课程来源 + 时间。零新增 API 成本。
- **推荐探索** (Recommended): 调用 `POST /api/knowledge/search`（query = profile 薄弱点），取 top 2 结果。显示匹配度和基于薄弱点的理由。

两块均为前端聚合，不新增后端端点。如果数据为空则整块不展示。

### Decision 9b: GitHub Project Search

Dashboard 新增"实训项目"区块，后端封装 GitHub API：

- **端点**: `POST /api/knowledge/github_search`
- **参数**: `{query, topic?, max_results: 6, min_stars?: 50}`
- **后端**: 封装 `api.github.com/search/repositories?q={query}+topic:{topic}&sort=stars`
- **返回**: `{repos: [{full_name, description, html_url, stars, language, license}]}`

### Decision 9c: Agent Video Search Tool

Agent 拥有 `search_learning_videos(state, query, max_results=3)` 工具，薄封装 `POST /api/knowledge/video_search`。

不设硬性规则，通过 system prompt 引导 Agent 的判断：

> 你有一个 search_learning_videos 工具，检索 B站教学视频。通常在两种场景自然使用：(1) 生成学习资源时，顺带提供 1-2 个相关视频作为补充材料；(2) 学生反复表示困惑时，用它找替代讲解方式。其他时候不必主动调用。不持久化，每次实时检索。

- **展示**: Agent 回复中内联视频卡片（缩略图 + 标题 + 时长 + 来源），用户点击跳转 B站
- **数据**: 不持久化。每次实时检索，始终返回最新结果

### Decision 10: Galaxy — 嵌入模式, 保留侧栏

Galaxy 不再全屏独立页面，而是嵌入课程布局的子窗口：页面保持浅色顶栏 + 左侧导航栏，深色 3D 银河作为主内容区的"子窗口"渲染。避免"二次跳转"的割裂感。

| 页面元素 | 主题/状态 |
|---------|----------|
| 顶栏 + 侧栏 | Agent 浅色主题（与其他课程页一致） |
| 银河 3D 视图区 | 深色太空主题（带圆角边框, 嵌入主内容区） |
| 视图切换 | 银河/平面 toggle 在深色区内 |
| NebulaOverlay | 保留（匹配高亮在深色区内） |
| DetailPanel | 保留（右侧浮窗在深色区内） |
| GalaxyRotator / EdgeLayer / KnowledgePoints | 全部保留 |

仅去除的：左侧栏课程卡片、管理工具 UI（这些已迁至 Dashboard）。全部可视化组件原封保留。

### Decision 11: Sidebar Quick Links

侧栏"快捷入口"区块提供课程内高频操作的快速跳转：

| 入口 | 数据源 | 说明 |
|------|--------|------|
| **课程进度** | `study_graph/features?syllabus_id=N` | 跳转大纲页并定位到当前周次 |
| **我的测验** | `GET /api/quiz_attempts?user_id=N&resource_id=X` (跨资源聚合) | 列出该课程所有测验资源及其提交记录 |

"我的测验" 页面聚合该课程下所有 `resource_type=quiz` 的生成资源，对每个资源展示最近一次提交（得分、正确数、薄弱知识点）。未作答的测验显示为灰色待完成状态。

### Decision 12: Content Thumbnail Strategy

不同内容区块根据内容特性选用不同缩略图策略（因地制宜）：

| 内容类型 | 缩略图策略 | 示例 |
|---------|-----------|------|
| 课程卡片 | 算法 banner 封面 (360×136, 纯色+几何+艺术字) | `ref-course-thumbnails.svg` |
| 最近资源 | 按 resource_type 选模板 (doc/mindmap/quiz/code/ppt) | `ref-doc-thumbnails.svg` |
| GitHub 实训项目 | 编程语言色标条 + repo 名缩写 | 语言色: Java=#b07219, Python=#3572A5, Scala=#c22d40 |
| B站视频 | 视频缩略图 URL (外链, 服务端返回) | video_search API |

所有缩略图统一为卡片宽度，保持视觉一致性但不强求相同尺寸。

### Decision 13: Admin Create Subject Wizard

创建新学科使用**弹窗向导**模式（非独立页面），以"是否产生持久化的大纲草稿"为边界：

- **向导阶段**（弹窗, 4 步）：基本信息（名称/描述/周数/目标模板）→ 上传教学日历（必须，提供 build_draft 所需的 file_id）→ 选择知识图谱 → 确认创建。确认后依次调用 `POST /api/file_upload_calendar`（已有端点，新增可选 `title` 参数）和 `POST /api/syllabus_build_draft`（已有端点），生成大纲草稿，不立即发布。
- **编辑阶段**（09-admin-dashboard 页面）：大纲草稿产生后，进入完整学科管理页——填充知识、编辑大纲、管理文件、查看学生进度。

**Rationale**: 向导降低创建门槛——收集最小必要信息即可生成草稿。大纲的详细编辑（周次内容、增强材料）放在管理页面而非向导中，保持向导简洁。弹窗模式让用户不离开 Dashboard 就能完成创建。

## Risks / Trade-offs

- **Galaxy scroll-reveal 性能**: Dashboard 底部银河预览不使用 3D 渲染，用 2D Canvas/SVG 静态星图 + CSS 渐变过渡 → 低端设备友好
- **路由迁移**: `/` 语义从银河变更为 Dashboard，已有书签失效 → 旧用户需适应，可在银河页添加"设为首页"提示
- **Agent 右栏拆分**: 用户若习惯一边对话一边看指标 → AgentStatsBar 保留关键数字；画像/知识库可一键展开；BuddyFAB 随时可达
- **聚合性能**: 课程进度聚合在前端计算 → 课程数通常 < 20，每门课 1-2 个 API 请求，总耗时 < 2s
- **终身 vs 单课程 Galaxy**: 两页数据源不同但组件相同 → 通过 props 控制 `graphIds` 数组，维护成本低

## Open Questions

- Galaxy 预览在 Dashboard 用纯 SVG 星空还是轻量 Canvas？（建议先用 SVG，后续可替换为 lottie/particles.js）
- 学伴悬浮窗移动端适配：桌面端为固定右下悬浮窗（~340×420），移动端（<768px）可考虑底部 sheet 或全屏覆盖。待移动端 mockup 阶段决策
- 气泡自动消失时长：当前设定 5 秒，后续可根据用户反馈调整

## Mockup Reference

按导航拓扑顺序排列：

| 文件 | 页面 | 说明 |
|------|------|------|
| `mockups/00-login.svg` | 登录页 (Agent 浅色主题) | `/login` |
| `mockups/01-dashboard.svg` | Dashboard — 课程卡片 + 最近资源 + 推荐探索 + GitHub实训 + 终身学习图谱 + 知识全景揭示 | `/` |
| `mockups/02-course-home.svg` | 学科首页 (课程资料 + AI资源 + 视频) | `/learn/:id/home` |
| `mockups/03-syllabus.svg` | 教学大纲 (时间线 + 活跃度) | `/learn/:id/syllabus` |
| `mockups/04-agent.svg` | 智能体 (精简对话 + 学习计划 + 悬浮学伴窗 + 自动弹出气泡) | `/learn/:id/agent` |
| `mockups/05-learning-tree.svg` | 学习成长图谱 — D3 + 薄弱点分析 + 待探索列表 + 学伴观察/记忆/建议 | `/learn/:id/tree` |
| `mockups/06-galaxy.svg` | 知识图谱 — 保留侧栏, 银河嵌入子窗口 3D 深色区 | `/learn/:id/galaxy` |
| `mockups/08-quiz-attempts.svg` | 我的测验 — 该课程所有测验提交记录 | `/learn/:id/quizzes` |
| `mockups/09-admin-dashboard.svg` | 管理 — 学科总览 (知识填充 + 大纲编辑 + 文件管理) | `/admin/:id` |
| `mockups/10-admin-create-subject.svg` | 管理 — 创建新学科向导 (弹窗, 3 步: 基本信息→选择图谱→确认) | 从 Dashboard "+" 触发 |
| `mockups/11-admin-students.svg` | 管理 — 学生进度 (D3 + 学伴树并列) | `/admin/:id/students` |
| `mockups/12-admin-graph.svg` | 管理 — 知识图谱 (管理员视角) | `/admin/:id/graph` |
| `mockups/ref-doc-thumbnails.svg` | 文档类型缩略图 (5种模板, 优化配色) | — |
| `mockups/ref-course-thumbnails.svg` | 课程封面横幅算法 | — |
| `mockups/ref-graph-modal.svg` | GraphModal 全屏图谱弹窗参考 (玻璃遮罩 + D3 图 + 候选分支 + 快捷键) | 从 04 "查看全屏图谱" 触发 |

**关键区分**: 
- 01-dashboard 嵌入终身学习图谱 (D3, study_graph/detail) 在滚动流中
- 06-galaxy 是 3D 知识域可视化 (knowledge-graph/snapshot, Three.js)，仅去除导航组件，**保留** NebulaOverlay 高亮闪烁、DetailPanel、视图切换等全部可视化能力
