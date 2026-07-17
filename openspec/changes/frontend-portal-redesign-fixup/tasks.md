# Tasks: Frontend Portal Redesign Fixup

补齐首轮实施的三类差距：admin 子路由、API 层接入、SVG 视觉对齐。

> # ⛔ 刚性门禁 — 以下条件为无条件硬性要求。任意一项不满足，迭代不终止。
>
> **1. 每页逐元素对照 SVG 设计稿（存在性约束）。** SVG 中存在的每个元素（按钮、图标、分隔线、标注覆盖层、卡片区域、文本行）MUST 在实现中存在。类型一致、层级正确、颜色方案匹配。缺失 = 未完成。
>
> **2. 每个按钮/交互元素有完整追踪链。** 点击 → 调用哪个已有函数/组件 → 触发什么 API → 状态如何变化 → UI 如何响应。追踪链不明确 = 未完成。
>
> **3. 全页面零假数据。** 禁止任何 `|| "placeholder"`、禁止空数据 fallback 常量、禁止硬编码示例数据。
>
> **4. 对照产出结论。** 每页完成后必须产出"通过/未通过"结论，列出缺失元素清单。未通过则继续迭代。
>
> # 🔩 核心原则：重构而非另起炉灶
>
> 旧前端所有数据来源和交互逻辑是正确的。本轮工作是**重组布局和路由**，不是重写数据流。
>
> - 已有组件（`ResourcePreviewDrawer`、`ResourceCard`、`KnowledgeGalaxy`、`NebulaOverlay`、`DetailPanel`、`D3GraphViewer`、`GraphModal` 等）直接复用，不重写。
> - 已有 API client（`fetchResourceList`、`fetchResourceDetail`、`fetchStudyGraph`、`fetchGraphSnapshot`、`fetchNodeDetail`、`fetchBuddyMessages`、`sendBuddyMessage`、`fetchProfileDetail` 等）直接调用，不裸 fetch。
> - 已有 hooks（`useGraphMatch`、`useHeartbeat`、`useSSEStream`、`useCurrentSyllabusId`、`useRealData` 等）直接接入。
> - 已有 stores（`galaxyStore`、`authStore`、`agentStore`、`graphModalStore`）直接使用。
> - 新页面 = 已有组件的重新排列 + 布局壳。不是新逻辑。

## 1. 后端 API 缺口补齐（前置任务）

- [ ] 1.1 新增 `GET /api/study_buddy/tree?user_id=N&syllabus_id=N` — 封装 `load_buddy_tree()`，返回 `{success, tree: BuddyTree|null}`
- [ ] 1.2 新增 `GET /api/study_buddy/memory?user_id=N&syllabus_id=N` — 读取 `buddy_memory.jsonl`，返回 `{success, tags: [{tag, created_at, category}]}`

## 3. Admin 子路由拆分

- [ ] 1.1 创建 `src/layouts/AdminLayout.tsx` — 侧栏导航（学科总览/学生进度/知识图谱）+ `<Outlet/>` + `← 返回首页` 面包屑
- [ ] 1.2 创建 `src/pages/admin/AdminDashboard.tsx` — 从 AdminSubjectDetail 提取知识填充面板 + 大纲编辑面板
- [ ] 1.3 创建 `src/pages/admin/AdminStudents.tsx` — 从 AdminSubjectDetail 提取学生进度 grid（学习图谱 D3 + 画像摘要 + 学伴树）
- [ ] 1.4 创建 `src/pages/admin/AdminGraph.tsx` — 从 AdminSubjectDetail 提取知识图谱管理员视图
- [ ] 1.5 更新 `src/App.tsx` — `/admin/subject/:syllabusId` 改为 AdminLayout 包裹的三条子路由（index → AdminDashboard, students → AdminStudents, graph → AdminGraph）
- [ ] 1.6 侧栏导航高亮当前子路由（active 态：accent 背景 + 左侧竖线指示器）

## 4. 数据流修正 — 接入已有 API client 和已有组件

核心：删除所有裸 `fetch()` 和新写的展示逻辑，改用已有模块。

- [ ] 4.1 Dashboard.tsx — 删除裸 `fetch("/api/syllabus_list")`，改用 `apiUrl()`；资源区域调用 `fetchResourceList()`；图谱调用 `fetchStudyGraph()`；推荐探索调用 `apiUrl("/api/knowledge/search")` + `matched_sources` 映射到真实文档
- [ ] 4.2 Dashboard.tsx — 资源卡片点击 → `fetchResourceDetail()` → 打开已有 `ResourcePreviewDrawer` 组件（不复写预览逻辑）
- [ ] 4.3 Dashboard.tsx — 推荐探索卡片点击 → 根据 `matched_sources[].kind` 打开对应资源（generated_resource → ResourcePreviewDrawer，knowledge_source → 文件下载/预览）
- [ ] 4.4 SubjectHome.tsx — 资源卡片点击 → 同上 ResourcePreviewDrawer；视频卡片 → `window.open(video_url)`
- [ ] 4.5 SyllabusPage.tsx — 接入 `fetchProfileDetail()` 获取真实 profile，传入 `ActivityGantt`；weeks 数据从真实 syllabus API 获取
- [ ] 4.6 LearningTreePage.tsx — 图谱用 `fetchStudyGraph()`；BuddyTree 用新增的 `GET /api/study_buddy/tree`；Memory 用新增的 `GET /api/study_buddy/memory`；Synthesis 用已有的 `GET /api/study_buddy/synthesis`
- [ ] 4.7 QuizAttempts.tsx — 资源列表用 `fetchResourceList(userId, syllabusId, "quiz")`；每个 quiz 的 attempt 用 `GET /api/quiz_attempts?user_id=N&resource_id=X`；点击 → 已有 `ResourcePreviewDrawer` 的 `QuizPreview` 模式（含"再试一次"按钮 + 历史结果显示）
- [ ] 4.8 Buddy 组件 — 消息用 `fetchBuddyMessages()`，发送用 `sendBuddyMessage()`；删除裸 fetch
- [ ] 4.9 CourseLayout.tsx — 课程信息用 `apiUrl("/api/syllabus_list")` POST 获取；删除所有硬编码 fallback

## 5. Galaxy 页面 — 完整恢复全部可视化组件

- [ ] 3.1 FullGalaxy.tsx — 完整接入原 SubjectOverview 的数据流：① `apiUrl("/api/syllabus_list")` 获取 graph_ids → ② `fetchGraphSnapshot(graphIds)` → `galaxyStore.setSnapshot()` → ③ `fetchStudyGraph()` → `treeResponseToGraph()` → `useGraphMatch()` → ④ `useHeartbeat()` 自动刷新
- [ ] 3.2 FullGalaxy.tsx — 渲染全部可视化组件：`KnowledgeGalaxy` + `NebulaOverlay` + `DetailPanel` + `GalaxyRotator` + `EdgeLayer` + `KnowledgePoints` + `GalaxyBackground`
- [ ] 3.3 FullGalaxy.tsx — 银河/平面视图切换 toggle（`kg-segmented`）；节点点击 → `fetchNodeDetail()` → `DetailPanel` 展示；`getRelatedParas` 关联段落
- [ ] 3.4 KnowledgeGalaxyPage.tsx — 同上全部可视化组件，嵌入 CourseLayout 深色子窗口（`rounded-xl border border-white/10 bg-[#03040a]`）
- [ ] 3.5 KnowledgeGalaxyPage.tsx — 底部 bar："当前: X课程图谱" / "终身学习图谱" toggle（链接到 `/galaxy`）
- [ ] 3.6 Galaxy 页面去除项确认：仅去除左侧课程卡片列表和管理入口按钮，其他一律保留
- [ ] 3.7 Galaxy 页面深色主题标记（subtle indicator badge "深色主题"）

## 6. Dashboard 页 SVG 视觉对齐

- [ ] 4.1 Header 改为紫色渐变（`#4f46e5 → #6366f1`），白色 logo + 用户头像圆圈 + 用户名
- [ ] 4.2 搜索框 "搜索课程..."（`w-[280px] h-[36px] rounded-[10px]`）+ `+ 创建新学科` 按钮与搜索框同行
- [ ] 4.3 课程卡片细粒度统计文本："N 节点已掌握 · M 薄弱 · 时间活跃"（10px 灰色）
- [ ] 4.4 草稿卡片虚线边框（`border-dashed`）+ 灰色封面 + "等待中" 禁用按钮
- [ ] 4.5 最近资源区域：副标题 "跨课程最近生成的学习材料" + 刷新按钮；资源卡片匹配度 % 标签
- [ ] 4.6 GalaxyReveal 确保与设计一致的渐变色过渡（`#f8fafc → #e2e8f0 → #334155 → #03040a`）

## 7. 学科首页 SVG 视觉对齐

- [ ] 5.1 课程资料卡片尺寸对齐（252×135），含折角文档 SVG 细节 + 灰色顶边色标
- [ ] 5.2 AI 资源卡片尺寸对齐（252×124），含类型色顶边（绿 `#22c55e` / 琥珀 `#f59e0b` / 紫 `#6366f1` + 左图标 + 匹配度 %
- [ ] 5.3 视频网格卡片按 SVG 视觉规格排列（缩略图比例、播放按钮叠加、时长角标、来源标签）

## 8. 学习成长图谱页 SVG 视觉对齐

- [ ] 6.1 Stats bar 精确布局（880×46 白色圆角容器，5 项统计 + 竖线分隔）→ 改为逐项 `<div>` + `border-r` 分隔
- [ ] 6.2 D3 图上方叠加 "当前步骤" 紫色 pill 标签 + 向下虚线指示器（位于 D3GraphViewer 容器外部，跟随 zoom/pan 变换）
- [ ] 6.3 D3 图上方叠加 "薄弱集群 · N 节点" 红色虚线矩形框标注
- [ ] 6.4 视图切换按钮样式对齐：活跃项 accent/紫色，默认 "学伴视角" 激活
- [ ] 6.5 面包屑三级："联觉 LianJue / 课程名 / 学习成长图谱"

## 9. 全局视觉对齐

- [ ] 7.1 所有课程子页面顶栏显示 `联觉 LianJue / 课程名 / 子页名` 面包屑（可点击前两级）
- [ ] 7.2 卡片投影统一：课程卡片 `shadow-md`，资源卡片 `shadow-sm`
- [ ] 7.3 Admin 页面侧栏导航 active 态指示器 + `← 返回首页` 面包屑

## 10. 刚性门禁 — SVG 逐元素对照（每项必须通过，否则迭代不终止）

### 门禁 A: Dashboard (01-dashboard.svg, viewBox 1440×2450)
- [ ] 8A.1 顶栏紫色渐变 (`#4f46e5→#6366f1`) + 白色 logo + 用户头像圆圈 + 用户名 + 邮箱
- [ ] 8A.2 搜索框 "搜索课程..." (280×36, rounded 10px) + `+ 创建新学科` 按钮同行
- [ ] 8A.3 课程卡片 384×266：banner 360×136、标题 28px white bold、副标题 12px、周次·学期 12px bold、状态 badge 48×20 rounded 5px、进度条（灰色底色+渐变填充+百分比）、细粒度统计 "N 节点已掌握 · M 薄弱 · 时间活跃" 10px、主按钮"进入学习"96×26 + 次按钮"管理"52×26
- [ ] 8A.4 草稿卡片：灰色背景 `#fafafa`、虚线边框 `stroke-dasharray="6,3"`、灰色封面 `#94a3b8`、无几何图案、"课程准备中"文本、"等待中"禁用按钮
- [ ] 8A.5 最近资源区域：标题 "最近资源" 16px bold + 副标题 "跨课程最近生成的学习材料" 12px + 刷新按钮 (60×24)；每张资源卡片 296×160，类型色背景 + 类型图标 + 标题 12px bold + 类型·课程名 + 时间·匹配度 %
- [ ] 8A.6 GalaxyReveal 渐变过渡 4 段色 `#f8fafc→#e2e8f0→#334155→#03040a`，2D SVG 星空（≥40 随机星点 + ≥5 星座连线），"进入全屏知识总览 →" 链接

### 门禁 B: 学科首页 (02-course-home.svg, viewBox 1440×1000)
- [ ] 8B.1 课程资料卡片 252×135：灰色 3px 顶边 `#64748b`、折角文档 SVG（右上角折叠 `polygon` + 文字行 `rect` 模拟）、标题 12px bold + 类型标签 10px
- [ ] 8B.2 AI 资源卡片 252×124：类型色 3px 顶边（绿/琥珀/紫）、左侧类型图标 SVG、标题 13px bold + 类型标签 10px + 匹配度 %、描述文本 2 行 11px
- [ ] 8B.3 视频网格卡片：缩略图 16:9 + 播放按钮叠加 + 时长角标 + 标题 + 来源标签

### 门禁 C: 学习成长图谱 (05-learning-tree.svg, viewBox 1440×1080)
- [ ] 8C.1 顶栏面包屑 "联觉 LianJue / 课程名 / 学习成长图谱" 三级
- [ ] 8C.2 视图切换：4 按钮（力导向/树状/层级/学伴视角），学伴视角紫色描边 `#c4b5fd` + `#ede9fe` 背景，默认激活
- [ ] 8C.3 Stats bar 880×46：5 项统计（学习记录/薄弱点/掌握度/辍学风险/小觉提示），每项有标签 9px gray + 数值 16px bold + 竖线 `#f1f5f9` 分隔
- [ ] 8C.4 D3 力导向图：学生节点（绿=mastered `#22c55e`、indigo=learning `#6366f1`、红=weak `#ef4444`）+ 标签 + score 副标题
- [ ] 8C.5 学伴提示节点：紫色虚线圆圈 `fill=#ede9fe, stroke=#7c3aed, stroke-dasharray=3,3` + glow filter + 紫色虚线边 `stroke-dasharray=2,3, opacity=0.3-0.5`
- [ ] 8C.6 "当前步骤" 覆盖层：紫色 pill 标签 `bg=#6366f1` + 向下虚线 2,2 + 指向对应节点
- [ ] 8C.7 "薄弱集群 · N 节点" 覆盖层：红色虚线矩形框 `stroke=#fecaca, fill=#fef2f2`

### 门禁 D: Galaxy (06-galaxy.svg, viewBox 1440×1080)
- [ ] 8D.1 深色主题：`bg-[#03040a]`、所有 `.kg-*` 类可用
- [ ] 8D.2 KnowledgeGalaxy (Three.js 3D) 渲染节点球体和边
- [ ] 8D.3 NebulaOverlay 渲染学习节点匹配高亮（`useGraphMatch` 输出 → `matchedNodeIds` + `nodeColors` → 节点颜色叠加），stardust boost 闪烁
- [ ] 8D.4 DetailPanel 选中节点时滑入：标题、理由框 `.kg-reason`、证据段 `.kg-evidence`、邻居按钮 `.kg-neighbors`
- [ ] 8D.5 顶栏：银河/平面视图 toggle `.kg-segmented`、图谱名 label
- [ ] 8D.6 GalaxyRotator 缓慢自动旋转（不抖动）
- [ ] 8D.7 数据流完整：`syllabus_list → graph_ids → fetchGraphSnapshot → galaxyStore → useGraphMatch → NebulaOverlay`

### 门禁 E: Admin 页 (09/11/12-admin SVG)
- [ ] 8E.1 Admin 侧栏：学科名称 15px bold + 状态 badge 52×20 rounded 5px + 三个导航链接（学科总览/学生进度/知识图谱）+ active 态左侧 3px accent 竖线 + `← 返回首页` 面包屑
- [ ] 8E.2 AdminDashboard 面板：文件上传 input + "创建填充任务" 按钮 + JSON textarea + "保存大纲" 按钮
- [ ] 8E.3 AdminStudents：学生卡片 grid（每个含 D3 图谱 + 画像摘要 + 学伴树）

### 构建门禁
- [ ] 8F.1 TypeScript 编译零错误（`tsc --noEmit`，允许 pre-existing 错误）
- [ ] 8F.2 Vite build 成功（`vite build`）
- [ ] 8F.3 后端测试 12/12 通过（`pytest -k "not mysql"`）
