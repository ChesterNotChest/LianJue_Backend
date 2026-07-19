## 发现：每类资源的点击行为已有对应组件，不得另写

| 资源卡片类型 | 数据来源 | onClick | 复用组件 |
|------------|---------|---------|---------|
| AI生成资源 (mindmap/doc/quiz/code/ppt) | `POST /api/generative_list` | `fetchResourceDetail()` → 打开 Drawer | `ResourcePreviewDrawer`（已有，5种渲染） |
| 课程资料 (知识文档) | `GET /api/knowledge/search` → `matched_sources[kind=knowledge_source]` | 文件下载/预览 | `GET /api/file/download?file_id=X` |
| 推荐探索 | `GET /api/knowledge/search` → `results[]` + `matched_sources[]` | 根据 matched_source.kind 打开对应资源 | `ResourcePreviewDrawer` 或文件下载 |
| 视频 | `POST /api/knowledge/video_search` | `window.open(video_url)` | — |
| GitHub项目 | `POST /api/knowledge/github_search` | `window.open(html_url)` | — |
| 测验 | `POST /api/generative_list (quiz)` | 打开 Drawer quiz 模式 | `ResourcePreviewDrawer.QuizPreview`（已有，含答题+提交+画像同步+"再试一次"） |
| PPT | `POST /api/generative_list (ppt)` | 打开 Drawer ppt 模式 | `ResourcePreviewDrawer.PptViewer`（已有，pptx-preview + Markdown fallback） |

## ADDED Requirements

### Requirement: SVG 设计稿存在性对照 — 每页完成时逐元素验证

SVG 设计稿定义的是**存在性约束**：每个在 SVG 中出现的元素（按钮、图标、分隔线、标注覆盖层、卡片区域、文本行）MUST 在实现中存在。具体像素尺寸、间距为设计指导而非绝对数值，但元素的**类型、层级关系、相对位置、颜色方案**必须与 SVG 一致。

每页实现完成后 SHALL 对照对应 SVG 设计稿逐元素检查存在性。任何 SVG 中存在的元素在实现中缺失 → 该页未完成。对照检查 SHALL 产出通过/未通过结论。

适用页面：Dashboard（01）、学科首页（02）、大纲页（03）、智能体页（04）、学习成长图谱（05）、知识图谱（06）、测验记录（08）、Admin 学科总览（09）、Admin 创建学科（10）、Admin 学生进度（11）、Admin 知识图谱（12）。

#### Scenario: Hard gate on every page — existence check
- **WHEN** 任一页面声称"实现完成"
- **THEN** 必须已对照对应 SVG 设计稿逐元素检查存在性
- **AND** SVG 中存在的每个元素在实现中有对应呈现（类型一致、层级正确、颜色方案匹配）
- **AND** 元素中的数据内容来自真实 API 响应
- **AND** 如有任何元素缺失，该页视为未完成，迭代继续

### Requirement: Dashboard matches SVG design — every button enumerated
Dashboard 页 SHALL 包含 01-dashboard.svg 中的全部交互元素。每个按钮的尺寸、颜色、圆角、字号必须精确匹配。数据来自真实 API。

#### Scenario: Gradient header layout
- **WHEN** Dashboard 渲染
- **THEN** 顶栏 64px 高，全宽，紫色渐变 `#4f46e5 → #6366f1`
- **AND** 左侧 "联觉 LianJue" 20px font-weight 800 white，letter-spacing 1
- **AND** 右侧用户头像圆圈 32px 直径 `rgba(255,255,255,0.2)` + 用户名 11px white + 邮箱/角色 9px `rgba(255,255,255,0.55)`

#### Scenario: Search bar and Create CTA — exact dimensions
- **WHEN** Dashboard 渲染
- **THEN** 页面标题 "我的学习" 28px bold `#0f172a` + 副标题 "继续你的学习旅程" 14px `#64748b`
- **AND** 搜索框 280×36，rounded 10px，白色背景 `stroke=#e2e8f0`，placeholder "搜索课程..." 12px `#94a3b8`，左侧放大镜图标
- **AND** `+ 创建新学科` 按钮 120×38，rounded 10px，`#6366f1` 填充，文本 13px font-weight 700 white
- **AND** 搜索框和按钮在同一行，与标题同行右对齐

#### Scenario: Course card banner — 对照 ref-course-thumbnails.svg 精确规格
- **WHEN** 已发布课程卡片渲染
- **THEN** Banner 区域 384×136，纯色背景 `PALETTE[hash%8]`
- **AND** Banner 内必须包含以下图层（从底到顶）：
  ① 纯色背景矩形
  ② **2 个大装饰圆**：r≈80 `rgba(255,255,255,0.06)` 偏移右上 + r≈100 `rgba(255,255,255,0.04)` 偏移左下——营造深度感
  ③ **几何图案叠加层**（`(hash>>4)%4` → 斜线交叉/矩形堆叠/同心波纹/三角重叠），使用 `rgba(255,255,255,0.05-0.08)` 粗线
  ④ **课程标题**：22px font-weight 800 white，letter-spacing 2，居中——数据来自 syllabus API 的 `title` 或 `subject_title`
  ⑤ **副标题**：10px `rgba(255,255,255,0.5)`，居中——数据来自 syllabus API 的 `graph_names[0]`
- **AND** Banner 不使用渐变遮罩——标题直接显示在几何图案之上

#### Scenario: Course card below-banner — 对照 ref-course-thumbnails.svg 精确规格
- **WHEN** 已发布课程卡片渲染
- **THEN** Banner 下方区域（白色背景）包含：
  ① **课程信息行**：左对齐 12px bold `#0f172a`（来自 syllabus API 的 weeks + semester 字段）+ 右对齐状态 badge 42×18 r5 `fill=#ede9fe` 文本 8px `#6366f1`
  ② **进度标签行**："学习进度" 10px `#64748b` 左 + 百分比 10px bold 右（进度 ≥67% → `#22c55e`，33-66% → `#f59e0b`，<33% → `#ef4444`）
  ③ **进度条**：底轨 384×5 r2.5 `fill=#f1f5f9`，填充段按百分比着色宽度=percent%
  ④ **"进入学习"按钮**：72×24 r7 `fill=#6366f1`，文本 10px font-weight 700 white，onClick → `navigate(/learn/${syllabusId}/home)`
  ⑤ **"管理"按钮**：52×26 r8 `fill=#f1f5f9`，文本 10px `#64748b`，operator 可见，onClick → navigate to admin
- **AND** 课程信息行：周次·学期 12px bold `#0f172a`（左对齐）+ 状态 badge 48×20 rounded 5px `#ede9fe` fill，文本 9px `#6366f1`（右对齐）
- **AND** "学习进度" 标签 11px `#64748b` + 百分比 11px bold（已发布=绿色 `#22c55e`，中等=琥珀 `#f59e0b`，低=红色，右对齐）
- **AND** 进度条：底色 `#f1f5f9` 352×6 rounded 3px，填充段渐变 `#22c55e→#4ade80`（或按百分比着色），宽度 = 百分比%
- **AND** 细粒度统计文本 10px `#94a3b8`："N 节点已掌握 · M 薄弱 · 时间活跃"
- **AND** "进入学习" 按钮 96×26 rounded 8px，`#6366f1` 填充，文本 12px bold white — 点击导航到 `/learn/:id/home`
- **AND** "管理" 按钮 52×26 rounded 8px，`#f1f5f9` 填充，文本 10px `#64748b` — operator 可见，点击导航到 `/admin/subject/:id`
- **AND** 两个按钮并排，左为主按钮右为次按钮

#### Scenario: Draft course card — 对照 ref-course-thumbnails.svg Banner 3
- **WHEN** 草稿课程卡片渲染
- **THEN** 卡片 384×266，`fill=#fafafa`，`stroke=#e2e8f0`，`stroke-dasharray=5,3`
- **AND** Banner 纯灰色 `#94a3b8`，仅 1 个装饰圆 r≈70 `rgba(255,255,255,0.05)`，无几何图案
- **AND** 课程名 20px font-weight 800 white 居中，副标题 "草稿 · 尚未发布" 10px `rgba(255,255,255,0.4)` 居中
- **AND** 课程信息行："课程准备中" 12px bold `#94a3b8`，无进度条，无进度百分比
- **AND** "等待中" 按钮 72×24 r7，`fill=#f1f5f9`，`stroke=#e2e8f0`，文本 10px font-weight 700 `#94a3b8`，disabled

#### Scenario: Recent Resources section — full spec
- **WHEN** 最近资源区域渲染且有数据
- **THEN** 区域标题 "最近资源" 16px bold `#0f172a` + 副标题 "跨课程最近生成的学习材料" 12px `#94a3b8`
- **AND** 刷新按钮 60×24 rounded 6px，`fill=#f1f5f9`，文本 "刷新" 10px `#64748b`，右侧刷新图标（圆圈+三角箭头），与标题同行右对齐
- **AND** 每张资源卡片 296×160 rounded 10px，白色背景，`stroke=#e2e8f0`，投影 `filter="url(#ts)"`
- **AND** 卡片上半 296×100：按资源类型色背景（mindmap=`#ecfdf5`，quiz=`#fffbeb`，ppt=`#fef2f2`，code=`#1e293b`）+ 类型专属 SVG 图标
- **AND** 卡片下半 296×60 白色：标题 12px bold `#0f172a`，类型标签行 10px `#64748b`（如"思维导图 · 大数据概论"），时间·匹配度 9px `#94a3b8`
- **AND** mindmap 卡片显示中心节点+分支连线+叶子节点的 SVG 图标（`stroke=#059669`，opacity 渐变）
- **AND** quiz 卡片显示 "?" 水印 28px `#d97706` opacity 0.12 + 两个选项框（灰色+琥珀色选中态）
- **AND** ppt 卡片显示幻灯片缩略 SVG（白色矩形 116×64 + "Slide Title" 12px `#dc2626` + 横线模拟）
- **AND** code 卡片显示深色编辑器背景 `#1e293b` + 语法着色代码行（`def` purple, `solve` blue, 其余 gray）

#### Scenario: Recommended Exploration section
- **WHEN** 推荐探索区域渲染且有数据
- **THEN** 区域标题 "推荐探索" 16px bold `#0f172a` + 副标题 "基于薄弱点 · knowledge/search · 匹配度排序" 12px `#94a3b8`
- **AND** 每张卡片 296×160 rounded 10px，白色背景，`stroke=#e2e8f0`，投影 `filter="url(#ts)"`
- **AND** 上半 296×100：蓝色文档背景 `#eff6ff` + 文档 SVG（折角+文字行）+ 匹配度 badge 20×20 rounded 6px `#3b82f6` opacity 0.15 右下角，文本 9px bold `#3b82f6`
- **AND** 下半 296×60 白色：标题 12px bold `#0f172a`，推荐理由 10px `#64748b`（如"你目前最薄弱的点，覆盖三大策略对比"）
- **AND** mindmap 类型卡片使用绿色主题（`#ecfdf5` 背景，`#059669` badge）

#### Scenario: GitHub Projects section
- **WHEN** 实训项目区域渲染且有数据
- **THEN** 区域标题 "实训项目" 16px bold `#0f172a` + 副标题 "GitHub 开源项目 · 按相关度与 Star 数检索" 12px `#94a3b8`
- **AND** 刷新按钮 60×24 rounded 6px，与 Recent Resources 同款，与标题同行右对齐
- **AND** 每张卡片 296×160 rounded 10px，白色背景，`stroke=#e2e8f0`，投影 `filter="url(#ts)"`
- **AND** 上半 296×100：深色代码背景 `#1e293b` + `{ }` 水印 18px monospace white opacity 0.15 + 语言色标条（如 Java `#b07219`，Scala `#c22d40`）+ 语言名 9px monospace
- **AND** 下半 296×60 白色：repo 名 10px monospace `#6366f1`（如 `apache/hbase`），描述 11px bold `#0f172a`，语言·License 9px `#94a3b8`，Star 数 10px bold `#f59e0b` 右对齐

#### Scenario: Section divider
- **WHEN** Dashboard 滚动到内容区底部、GlaxyReveal 之上
- **THEN** 显示分隔元素："向下滚动探索更多" 12px `#94a3b8` 居中 + 下方短横线 + 向下三角箭头 `#94a3b8`

#### Scenario: Lifelong Learning Graph section
- **WHEN** 终身学习图谱区域渲染（在 GalaxyReveal 之前）
- **THEN** 区域标题 "终身学习图谱" 16px bold `#0f172a` + 副标题描述
- **AND** D3 力导向图嵌入白底圆角卡片中
- **AND** 多个课程的节点以不同颜色区分（课程标签框标注）

#### Scenario: Galaxy reveal is scroll parallax — NOT a click-to-navigate button
- **WHEN** Dashboard 渲染完毕且用户尚未滚动到银河区域
- **THEN** 银河区域不可见，页面背景为标准 `#f8fafc` 浅色
- **AND** 页面顶部仅显示课程卡片区域（viewport 内可见）
- **WHEN** 用户向下滚动越过课程卡片区域（触发 `IntersectionObserver`，threshold 0.2）
- **THEN** 页面背景从 `#f8fafc` 分 4 段渐变过渡到深色太空背景（`#f8fafc → #e2e8f0 → #334155 → #03040a`）
- **AND** 2D SVG 星空 canvas 随滚动距离 opacity 从 0 渐显到 1（非 3D rendering，保证低端设备性能）
- **AND** 星空包含 ≥40 个随机定位的白色星点（半径 0.4–1.8，opacity 0.2–0.8）+ ≥8 条低透明度星座连线 `stroke="rgba(255,255,255,0.12)"`
- **AND** 星空区域中央显示标题 "知识全景总览"（white bold）+ 描述文本（slate-400）
- **AND** 最底部仅有 subtle text link "进入全屏知识总览 →"（`text-sky-300`，`bg-sky-500/20`，`border-sky-500/30`），点击导航到 `/galaxy`
- **AND** 该 link 为文字链接风格，不是按钮（`rounded-xl` 可接受，但不可是 `bg-accent` 实心按钮）
- **AND** 整个银河区域不是卡片式入口——不可以通过点击卡片区域跳转

### Requirement: Course Home matches SVG design
学科首页 SHALL 包含以下来自 02-course-home.svg 的视觉元素：

#### Scenario: Course materials cards
- **WHEN** 课程资料区域渲染
- **THEN** 每张文档卡片为 252×135 尺寸
- **AND** 顶部有 3px 灰色条（documents 类型色标）
- **AND** 卡片内有折角文档 SVG（右上角折叠效果 + 文字行模拟）

#### Scenario: AI generated resource cards
- **WHEN** AI 生成资源区域渲染
- **THEN** 每张卡片为 252×124 尺寸
- **AND** 顶部有 3px 类型色标（绿=思维导图 `#22c55e`、琥珀=测验 `#f59e0b`、紫=课件 `#6366f1`）
- **AND** 卡片左侧有类型图标（思维导图=中心节点+分支、测验=?+选项框、PPT=幻灯片缩略）
- **AND** 右侧显示标题、类型标签、匹配度 %、描述文本（2行）

### Requirement: All pages have breadcrumb header
所有课程子页面和 admin 页面 SHALL 在顶栏显示三级面包屑导航 `联觉 LianJue / 课程名 / 子页名`。

#### Scenario: Breadcrumb on tree page
- **WHEN** 用户在学习成长图谱页
- **THEN** 顶栏显示 `联觉 LianJue / 算法设计与分析 / 学习成长图谱`
- **AND** "联觉 LianJue" 为可点击链接，导航到 `/`
- **AND** "算法设计与分析" 为可点击链接，导航到 `/learn/:id/home`

### Requirement: Learning Tree page matches SVG design
学习成长图谱页 SHALL 包含以下来自 05-learning-tree.svg 的视觉元素：

#### Scenario: Stats bar layout
- **WHEN** 学习成长图谱页渲染
- **THEN** D3 图谱上方显示 stats bar——白色圆角容器（880×46），包含 5 个统计项：学习记录 / 薄弱点 / 掌握度 / 辍学风险 / 小觉提示
- **AND** 每项有标签（灰色 9px）+ 数值（深色 16px bold）+ 竖线分隔

#### Scenario: D3 graph overlay annotations
- **WHEN** D3 力导向图渲染且有当前步骤数据
- **THEN** 当前步骤节点上方显示紫色 pill 标签 "当前步骤" + 向下虚线指示器
- **AND** 薄弱点集群外围显示红色虚线矩形框 "薄弱集群 · N 节点"
- **AND** 学伴提示节点以紫色虚线圆圈渲染（`fill=#ede9fe, stroke=#7c3aed, stroke-dasharray=3,3`），有紫色发光滤镜

#### Scenario: View toggle bar
- **WHEN** 图谱渲染
- **THEN** 顶栏显示 4 个视图切换按钮：力导向 / 树状 / 层级 / 学伴视角
- **AND** 活跃按钮为 accent 色填充或紫色描边（学伴视角）
- **AND** 默认激活 "学伴视角"

### Requirement: Galaxy pages preserve ALL original visualization components
KnowledgeGalaxyPage（`/learn/:id/galaxy`）和 FullGalaxy（`/galaxy`）SHALL 完整保留原 `SubjectOverview` 的全部可视化组件和数据流，仅去除左侧栏课程卡片和管理入口 UI。以下组件 MUST 全部接入并正常工作：

| 组件 | 说明 | 来源 |
|------|------|------|
| `KnowledgeGalaxy` | Three.js 3D 星系主体渲染 | `src/components/galaxy/KnowledgeGalaxy.tsx` |
| `NebulaOverlay` | 学习节点匹配高亮叠加层（含 stardust boost 闪烁） | `src/components/galaxy/NebulaOverlay.tsx` |
| `DetailPanel` | 右侧节点详情浮窗（含 `getRelatedParas` 关联段落） | `src/components/galaxy/DetailPanel.tsx` |
| `GalaxyRotator` | 自动旋转控制 | `src/components/galaxy/GalaxyRotator.tsx` |
| `EdgeLayer` | 3D 边渲染 | `src/components/galaxy/EdgeLayer.tsx` |
| `KnowledgePoints` | 3D 节点球体渲染 | `src/components/galaxy/KnowledgePoints.tsx` |
| `GalaxyBackground` | 26K 星场粒子背景 | `src/components/galaxy/GalaxyBackground.tsx` |
| 银河/平面视图切换 | 顶栏 toggle（`kg-segmented`） | `layoutMode` + `setLayoutMode` |
| `useGraphMatch` | 学习节点→银河节点的子串匹配，计算 `matchedNodeIds` + `nodeColors` | `src/hooks/useGraphMatch.ts` |
| `useHeartbeat` | 后端数据变更时自动刷新 galaxy 快照 | `src/hooks/useHeartbeat.ts` |
| `galaxyStore` | Zustand store：snapshot, selectedNode, hoveredNodeId, showEdges, layoutMode | `src/stores/galaxyStore.ts` |
| `fetchGraphSnapshot` | 从 graph IDs 加载星系快照 | `src/api/knowledgeGraphApi.ts` |
| `fetchNodeDetail` | 加载选中节点详情 | `src/api/knowledgeGraphApi.ts` |

#### Scenario: FullGalaxy preserves all visual components
- **WHEN** 用户访问 `/galaxy`（终身学习图谱）
- **THEN** 页面使用与原 `SubjectOverview` 相同的 `bg-[#03040a]` 深色背景
- **AND** `KnowledgeGalaxy` 渲染 3D 星系节点和边
- **AND** `NebulaOverlay` 在学习匹配节点上叠加掌握度颜色（绿=mastered, indigo=learning, red=weak），含 stardust boost 闪烁
- **AND** 右侧 `DetailPanel` 在选中节点时滑入，显示节点详情、关联段落、邻居节点
- **AND** `GalaxyRotator` 缓慢自动旋转
- **AND** 顶栏有银河/平面视图 toggle
- **AND** 仅去除：左侧课程卡片列表、管理入口按钮
- **AND** 数据通过 `fetchGraphSnapshot(graphIds)` → `galaxyStore.setSnapshot()` 加载
- **AND** 学习匹配通过 `useGraphMatch(studyNodes, snapshot.nodes)` 计算并传入 `NebulaOverlay`

#### Scenario: KnowledgeGalaxyPage preserves all visual components
- **WHEN** 用户访问 `/learn/:id/galaxy`（单课程知识图谱）
- **THEN** 深色 3D 视图区嵌入 CourseLayout 主内容区（带圆角边框 `rounded-xl border border-white/10`）
- **AND** 全部可视化组件与 FullGalaxy 相同（`KnowledgeGalaxy`, `NebulaOverlay`, `DetailPanel`, `GalaxyRotator`, `EdgeLayer`, `KnowledgePoints`, `GalaxyBackground`）
- **AND** 视图区底部显示 "当前: X课程图谱" / "终身学习图谱" toggle
- **AND** 数据通过 `fetchGraphSnapshot([courseGraphId])` 加载

#### Scenario: Galaxy data flow is complete
- **WHEN** Galaxy 页面挂载
- **THEN** ① `fetch(apiUrl("/api/syllabus_list"), ...)` 获取课程列表 → 提取 `graph_names[]` 去重为 `graphIds`
- **AND** ② `fetchGraphSnapshot(graphIds)` 获取星系快照 → `galaxyStore.setSnapshot(snapshot)`
- **AND** ③ `fetch(apiUrl("/api/study_graph/detail?..."))` 获取学习图谱 → `treeResponseToGraph()` → `useGraphMatch(studyNodes, snapshot.nodes)` 计算匹配
- **AND** ④ `useHeartbeat(userId, undefined, !!snapshot, callback)` 监听数据变更，自动刷新快照
- **AND** ⑤ 节点点击 → `fetchNodeDetail(nodeId, snapshot)` → `galaxyStore.setSelectedDetail(detail)` → `DetailPanel` 展示

### Requirement: Card shadows match SVG filters
所有卡片组件 SHALL 使用与 SVG `filter="url(#cs)"`（`0 2px 8px rgba(15,23,42,0.06)`）和 `filter="url(#ts)"`（`0 1px 3px rgba(15,23,42,0.05)`）等效的投影。

#### Scenario: Card shadow consistency
- **WHEN** 课程卡片、资源卡片、文档卡片渲染
- **THEN** 使用 `shadow-sm` 对应 `filter="url(#ts)"`
- **AND** 使用 `shadow-md` 对应 `filter="url(#cs)"`
- **AND** hover 时加深阴影
