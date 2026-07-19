# Tasks: Portal Phase 12 — 资源预览跳转全量补齐

> ⛔ **硬性门禁**: 禁假数据。每个 onClick 的数据源必须来自已存在的 API 返回值。每个交互必须有明确的 API 数据通路。

---

## Phase 1: 核心基础设施 — Store + NodeDetailPanel + CourseLayout 集成

### 1.1 resourcePreviewStore (新增)

- [x] 1.1.1 创建 `src/stores/resourcePreviewStore.ts`
- [x] 1.1.2 定义 `NodeDetailData` 类型：`{nodeId, title, summary?, mastery?: {label, score}, group?, growth_stage?, meta?}`
- [x] 1.1.3 实现 `openResource(userId, resourceId)`: 调用 `fetchResourceDetail` → 写入 `drawerResource` → `drawerOpen = true`
- [x] 1.1.4 实现 `openNodeDetail(data: NodeDetailData)`: 直接写入 state
- [x] 1.1.5 实现 `closeDrawer()`, `closeNodeDetail()`, `closeAll()`
- [x] 1.1.6 实现 `setSearchQuery(q)`, `setNodeHighlightTarget(label)`
- [x] 1.1.7 Store 验收: 无 mock 数据、无硬编码 resource_id

### 1.2 NodeDetailPanel (新增)

- [x] 1.2.1 创建 `src/components/resource/NodeDetailPanel.tsx`
- [x] 1.2.2 从 store 读取 `{nodeDetailOpen, nodeDetailData}` → 无数据时 return null
- [x] 1.2.3 渲染右侧滑出面板 (~320px 宽, rx=12, shadow)
- [x] 1.2.4 标题区域: title (16px/700) + growth_stage icon (seed→🌱 / sprout→🌿 / fruit→🍎)
- [x] 1.2.5 描述区域: summary (12px 多行)
- [x] 1.2.6 掌握度区域: mastery.label badge (color-coded) + score 进度条
- [x] 1.2.7 图谱分组: group 颜色圆点 (mastered=green, learning=indigo, weak=red, buddy_hint=purple)
- [x] 1.2.8 操作按钮: "在图谱中定位" (→ store.setNodeHighlightTarget) + "和智能体讨论" (→ navigate)
- [x] 1.2.9 关闭按钮: store.closeNodeDetail()
- [x] 1.2.10 验收: 无硬编码数据，所有字段来自 store

### 1.3 CourseLayout 集成

- [x] 1.3.1 在 CourseLayout 中导入 ResourcePreviewDrawer + NodeDetailPanel
- [x] 1.3.2 从 store 读取 `drawerOpen`, `drawerResource` → 渲染 `<ResourcePreviewDrawer>`
- [x] 1.3.3 渲染 `<NodeDetailPanel />` (自身从 store 读取 state)
- [x] 1.3.4 验收: Drawer/DetailPanel 渲染不影响已有布局

---

## Phase 2: SubjectHome 资源卡片 → ResourcePreviewDrawer

### 2.1 GeneratedResources

- [x] 2.1.1 卡片从 `<div>` 改为 `<button>` (或 div+onClick)
- [x] 2.1.2 添加 cursor-pointer + hover:shadow-md + hover:border-accent/30 视觉反馈
- [x] 2.1.3 onClick: `store.openResource(authStore.student.userId, r.resource_id)`
- [x] 2.1.4 验收: 点击卡片 → API fetch → ResourcePreviewDrawer 打开 → 文档/导图/测验/代码/exercise 全屏预览

### 2.2 FilePreviewModal — 原始文件页内预览 (新增)

- [x] 2.2.1 在 resourcePreviewStore 中添加 `filePreviewOpen`, `filePreviewUrl`, `filePreviewTitle`, `filePreviewType` state
- [x] 2.2.2 实现 `openFilePreview(url, title)`: 从 url 后缀 (`.pdf`/`.md`/`.txt` 等) 推断 type → set state
- [x] 2.2.3 实现 `closeFilePreview()`: 重置相关 state
- [x] 2.2.4 在 CourseLayout 中渲染 `<FilePreviewModal>`: 半透明遮罩 + max-w-4xl + 顶栏 (title + 关闭 + 新窗口打开)
- [x] 2.2.5 PDF 渲染: `<iframe src={filePreviewUrl} className="w-full h-[80vh]">`
- [x] 2.2.6 文本渲染: fetch url → `<pre className="overflow-auto max-h-[80vh] p-4">{text}</pre>`
- [x] 2.2.7 验收: 打开 PDF → iframe 浏览器原生查看器 (缩放/搜索/打印 均可用)

### 2.3 CourseMaterials — 接线

- [x] 2.3.1 每个材料卡片添加 onClick
- [x] 2.3.2 从 path/filename 提取文件扩展名，判断预览能力
- [x] 2.3.3 pdf/md/txt: `store.openFilePreview(url, title)`
- [x] 2.3.4 pptx/zip/其他: `window.open(download_url, '_blank')` 直接下载
- [x] 2.3.5 无 url: 保持静态卡片
- [x] 2.3.6 添加 cursor-pointer + hover:shadow-md 视觉反馈
- [x] 2.3.7 验收: 点击 PDF 卡片 → FilePreviewModal 页内预览；点 PPTX → 下载

---

## Phase 3: D3 图谱节点 → NodeDetailPanel

### 3.1 LearningTreePage

- [x] 3.1.1 实现 `handleNodeClick(node: GraphNode)`: 从 node.meta 提取 mastery_score/summary/growth_stage → `store.openNodeDetail(...)`
- [x] 3.1.2 group → mastery.label 映射: mastered→"mastered", weak→"weak", 其他→"learning"
- [x] 3.1.3 D3GraphViewer 传入 `onNodeClick={handleNodeClick}`
- [x] 3.1.4 `useEffect` 监听 `store.nodeHighlightTarget` 变化 → graph 滚动+高亮对应节点（"在图谱中定位" 联动）
- [x] 3.1.5 验收: 点击图谱中任意节点 → NodeDetailPanel 打开 → 显示该节点详情

### 3.2 RightSidebar KnowledgeBase 关联图谱

- [x] 3.2.1 替换 `KB_MOCK_GRAPH` → 从 `matchedSources` + `reasoningEdges` 构建真实图谱数据
- [x] 3.2.2 节点: id=source_id, label=title, group 按 kind 区分
- [x] 3.2.3 边: reasoningEdges 中 source→target 关系
- [x] 3.2.4 传入 `onNodeClick` → `store.openNodeDetail(...)`
- [x] 3.2.5 验收: KB 搜索后关联图谱使用真实数据；点击节点 → NodeDetailPanel

### 3.3 App.tsx GraphModal

- [x] 3.3.1 实现 `handleGraphNodeClick` → `store.openNodeDetail(...)`
- [x] 3.3.2 GraphModal 传入 `onNodeClick={handleGraphNodeClick}`
- [x] 3.3.3 验收: 推荐路径图谱中点击节点 → NodeDetailPanel

### 3.4 KnowledgeGalaxyPage (如适用)

- [x] 3.4.1 如有 D3GraphViewer → 传入 `onNodeClick`
- [x] 3.4.2 验收: Galaxy 图谱中点击节点 → NodeDetailPanel

---

## Phase 4: Tree 子组件 → 跳转

### 4.1 WeaknessAnalysis

- [x] 4.1.1 每个 item `<div>` 改为 `<button>` (或添加 onClick)
- [x] 4.1.2 添加 cursor-pointer + hover:bg-red-50
- [x] 4.1.3 onClick: `store.openNodeDetail({title: n.title, mastery: {label:"weak", score: n.mastery_score}, summary: n.problem || n.comment})`
- [x] 4.1.4 验收: 点击薄弱项 → NodeDetailPanel 显示

### 4.2 ExploreGapList

- [x] 4.2.1 每个 gap item `<div>` 改为 `<button>`
- [x] 4.2.2 添加 cursor-pointer + hover:bg-purple-50
- [x] 4.2.3 onClick: `store.openNodeDetail({nodeId: n.node_id, title: n.title, summary: n.summary, group: "buddy_hint"})`
- [x] 4.2.4 底部 "和智能体对话" 按钮保持不变
- [x] 4.2.5 验收: 点击待探索项 → NodeDetailPanel

### 4.3 BuddyObservations

- [x] 4.3.1 每个 ObsCard `<div>` 改为 `<button>`
- [x] 4.3.2 添加 cursor-pointer + hover:bg-slate-100
- [x] 4.3.3 onClick: `store.setNodeHighlightTarget(note.node_title)` → 滚动 D3 图 + 高亮节点
- [x] 4.3.4 验收: 点击观察卡片 → 图谱自动滚动并高亮对应节点

### 4.4 BuddyMemoryCloud

- [x] 4.4.1 每个 tag pill `<span>` 改为 `<button>`
- [x] 4.4.2 添加 cursor-pointer + hover:opacity-80
- [x] 4.4.3 onClick: `store.setSearchQuery(tag.tag)` → KnowledgeBase 面板展开 + 自动填入搜索词
- [x] 4.4.4 验收: 点击标签 → KnowledgeBase 自动搜索该 tag

---

## Phase 5: Agent 页 → 跳转

### 5.1 KnowledgeBasePanel — 搜索结果

- [x] 5.1.1 搜索结果条目 onClick 扩展: 判断 matchedSources 中对应条目的 kind
- [x] 5.1.2 generated_resource: `store.openResource(userId, resource_id)`
- [x] 5.1.3 knowledge_source (有 download_url): `window.open(url)` (保持现有)
- [x] 5.1.4 其他/纯文本: `store.openNodeDetail({title, ...})`
- [x] 5.1.5 验收: 搜索结果可点击并正确路由

### 5.2 KnowledgeBasePanel — 生成资源条目

- [x] 5.2.1 genFiles 每项从 `<div>` 改为 `<button>`
- [x] 5.2.2 添加 cursor-pointer + hover:bg-slate-50
- [x] 5.2.3 onClick: `store.openResource(userId, f.resource_id)`
- [x] 5.2.4 验收: 点击生成资源条目 → ResourcePreviewDrawer

### 5.3 KnowledgeBasePanel — 知识源文件条目

- [x] 5.3.1 保持现有 `<a href={download_url}>` 行为不变
- [x] 5.3.2 验收: 文件下载链接正常工作

### 5.4 ProfilePanel — 瓶颈知识点标签

- [x] 5.4.1 瓶颈标签从 `<span>` 改为 `<button>`
- [x] 5.4.2 添加 cursor-pointer + hover:opacity-80
- [x] 5.4.3 onClick: `store.openNodeDetail({title: t, mastery: {label:"weak", score: 0}})`
- [x] 5.4.4 验收: 点击瓶颈标签 → NodeDetailPanel

### 5.5 InlineRecommendationCard — 路径节点

- [x] 5.5.1 路径可视化区域的节点圆形从 `<div>` 改为 `<button>`
- [x] 5.5.2 添加 cursor-pointer + hover:scale-110 transition
- [x] 5.5.3 onClick: 从 displayNodes 中取 title/mastery → `store.openNodeDetail(...)`
- [x] 5.5.4 验收: 点击路径节点 → NodeDetailPanel

### 5.6 SubagentCard — 资源生成事件

- [x] 5.6.1 先在 `agent_tools.py` 或 SSE event 日志中确认 `resource_id` 字段的实际名称
- [x] 5.6.2 资源生成完成事件 (`status==="completed"` + `resource_type`) 底部添加 "→ 查看此资源" 按钮
- [x] 5.6.3 onClick: `store.openResource(userId, resourceId)` (resourceId 从 event 中提取)
- [x] 5.6.4 验收: 资源生成完成后点击 → ResourcePreviewDrawer

---

## Phase 6: 构建验证

- [ ] 6.1 TypeScript 编译：`npm run build` 无错误
- [ ] 6.2 Store API 通路验证：`openResource` → `fetchResourceDetail` → `drawerResource` → ResourcePreviewDrawer 渲染
- [ ] 6.3 NodeDetailPanel 验证：从 D3/WeaknessAnalysis/ExploreGapList/ProfilePanel 各路径打开，内容正确
- [ ] 6.4 图谱联动验证：BuddyObservations click → D3 图高亮 + 滚动
- [ ] 6.5 KnowledgeBase 搜索联动验证：MemoryCloud tag click → KB 搜索填充
- [ ] 6.6 零假数据验证：所有 display 的数据字段都有明确 API 来源
