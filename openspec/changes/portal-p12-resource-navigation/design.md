## Context

当前前端「资源展示」和「点击交互」之间存在系统性断连。`ResourcePreviewDrawer`（全屏预览文档/导图/测验/练习/PPT）和 `D3GraphViewer.onNodeClick`（图谱节点点击回调）两大基础设施已完全可用，但从未被接线。

本设计建立一套轻量的 **Zustand store → 组件回调 → API fetch → 预览/详情面板** 统一通路，在不重构现有组件结构的前提下，补齐所有缺失的点击→跳转→预览闭环。

## Goals / Non-Goals

**Goals:**
- 建立 `resourcePreviewStore` 统一管理 ResourcePreviewDrawer 开闭 + 资源数据获取
- 新建 `NodeDetailPanel` 侧栏展示知识点详情（有 API 数据源的完整展示）
- 补齐 SubjectHome 资源卡片 → ResourcePreviewDrawer 通路
- 补齐 D3 图谱 4 个使用点的 `onNodeClick` → NodeDetailPanel
- 补齐 Tree 子组件（WeaknessAnalysis/ExploreGapList/BuddyObservations/BuddyMemoryCloud）的点击交互
- 补齐 Agent 页（KnowledgeBase 搜索结果/生成资源/瓶颈标签/推荐路径节点/SubagentCard）的点击交互

**Non-Goals:**
- 不修改 D3GraphViewer.tsx（接口已完备）
- 不修改 ResourcePreviewDrawer.tsx 核心逻辑（仅可能补充 API 调用方式）
- 不新增后端 API（全部使用已有 API）
- 不修改已有的路由结构
- 不使用假数据或硬编码 mock

## 影响文件范围

| 文件 | 操作 | Phase |
|------|------|-------|
| `src/stores/resourcePreviewStore.ts` | **新增** | P1 |
| `src/components/resource/NodeDetailPanel.tsx` | **新增** | P1 |
| `src/layouts/CourseLayout.tsx` | 修改 | P1 |
| `src/components/subject/CourseMaterials.tsx` | 修改 | P2 |
| `src/components/subject/GeneratedResources.tsx` | 修改 | P2 |
| `src/pages/LearningTreePage.tsx` | 修改 | P3 |
| `src/layouts/RightSidebar.tsx` | 修改 | P3+P5 |
| `src/App.tsx` | 修改 | P3 |
| `src/pages/KnowledgeGalaxyPage.tsx` | 修改 | P3 |
| `src/components/tree/WeaknessAnalysis.tsx` | 修改 | P4 |
| `src/components/tree/ExploreGapList.tsx` | 修改 | P4 |
| `src/components/tree/BuddyObservations.tsx` | 修改 | P4 |
| `src/components/tree/BuddyMemoryCloud.tsx` | 修改 | P4 |
| `src/components/chat/InlineRecommendationCard.tsx` | 修改 | P5 |
| `src/components/chat/SubagentCard.tsx` | 修改 | P5 |

## 函数-API 级完整数据流

### Phase 1: 核心基础设施

```
┌──────────────────────────────────────────────────────────────────┐
│                   resourcePreviewStore (Zustand)                   │
│                                                                   │
│  State:                                                           │
│    drawerOpen: boolean                                            │
│    drawerResource: ResourceDetail | null                          │
│    drawerLoading: boolean                                         │
│    nodeDetailOpen: boolean                                        │
│    nodeDetailData: {                                              │
│      nodeId: string, title: string, summary?: string,             │
│      mastery?: {label, score}, group?: string,                    │
│      growth_stage?: string, meta?: Record<string,unknown>         │
│    } | null                                                       │
│                                                                   │
│  Actions:                                                         │
│    openResource(userId, resourceId) → fetch + open                │
│    openNodeDetail(nodeData) → set + open                          │
│    closeDrawer() / closeNodeDetail()                              │
│    closeAll()                                                     │
│                                                                   │
│  Usage:                                                           │
│    CourseLayout → <ResourcePreviewDrawer /> + <NodeDetailPanel /> │
│    Any component → store.openResource() / store.openNodeDetail()  │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 2: SubjectHome 资源卡片 → ResourcePreviewDrawer

```
SubjectHome
  │
  ├── CourseMaterials
  │     └─ onClick (per card)
  │         → 判断文件类型:
  │           · pdf → store.openFilePreview(file_url, title)
  │           · md/txt 等文本 → store.openFilePreview(file_url, title)
  │           · pptx/zip/其他 → window.open(download_url, '_blank') 直接下载
  │         → openFilePreview 打开简易 Modal: <iframe src={url}> (PDF)
  │           或 <pre> 文本渲染 (md/txt)
  │
  └── GeneratedResources
        └─ onClick (per card)
            → store.openResource(userId, resource_id)
              → GET /api/generative_detail {user_id, resource_id}
              → ResourceDetail {content, render: {markdown, mermaid}}
              → store.drawerResource = detail
              → store.drawerOpen = true
              → ResourcePreviewDrawer renders in CourseLayout
```

### Phase 3: D3 图谱节点 → NodeDetailPanel

```
LearningTreePage                                    RightSidebar::KnowledgeBasePanel
  │                                                   │
  ├── D3GraphViewer                                   ├── D3GraphViewer (关联图谱)
  │     └─ onNodeClick={handleNodeClick}              │     └─ onNodeClick={handleNodeClick}
  │         → store.openNodeDetail({                   │         → store.openNodeDetail(...)
  │             nodeId: n.id,                          │
  │             title: n.label,                        │   GraphModal
  │             group: n.group,                        │     └─ onNodeClick={handleNodeClick}
  │             mastery: n.meta?.mastery_score,         │         → store.openNodeDetail(...)
  │             summary: n.meta?.summary,
  │             growth_stage: n.meta?.growth_stage,
  │           })

NodeDetailPanel (rendered in CourseLayout, slide-in right panel)
  ├── 基本信息: title + summary (来自 D3 node meta)
  ├── 掌握度: mastery score + label → color-coded badge
  ├── 生长阶段: growth_stage → seed/sprout/fruit icon
  ├── 操作:
  │     ├── "在图谱中定位" → highlightPath in D3 graph
  │     └── "和智能体讨论" → navigate(/learn/{sid}/agent)
  └── 无 API 假数据: 所有字段来自 D3 node.meta（已由 API 填充）
```

### Phase 4: Tree 子组件 → 跳转

```
WeaknessAnalysis                         ExploreGapList
  │                                        │
  ├── onClick per item                     ├── onClick per item
  │     → store.openNodeDetail({            │     → store.openNodeDetail({
  │         nodeId: 由 node 推断,            │         nodeId: n.node_id,
  │         title: n.title,                 │         title: n.title,
  │         mastery: {label:"weak",         │         summary: n.summary,
  │                    score:n.mastery_      │       })
  │                    score},              │
  │         problem: n.problem              │   "和智能体对话" button
  │       })                                │     → navigate(/learn/{sid}/agent)
  │                                        │     (已有, 保持不变)
  │  数据源: study_graph API               │
  │  tree.nodes(mastery.label==="weak")    │
  │                                        │
BuddyObservations                         BuddyMemoryCloud
  │                                        │
  ├── onClick per card                     ├── onClick per tag pill
  │     → if node_title matches D3          │     → store.closeAll()
  │       node id or label:                 │     → navigate to KnowledgeBase
  │       focus/highlight in graph          │       面板 + 自动填入 tag
  │       + scroll to graph area            │       文本为搜索 query
  │     (不打开 NodeDetailPanel,            │     (将 searchQuery 写入
  │      因为 buddy note 本身不是            │      RightSidebar state)
  │      知识点数据)                         │
  │                                        │
  └─ 数据源: buddy_tree API                └─ 数据源: study_buddy/memory API
     nodes[].buddy_notes                       tags[].tag (搜索关键词)
```

### Phase 5: Agent 页 → 跳转

```
RightSidebar::KnowledgeBasePanel                    InlineRecommendationCard
  │                                                   │
  ├── 搜索结果条目 onClick                               ├── 路径节点 onClick
  │     → 判断类型:                                      │     → store.openNodeDetail({
  │       · knowledge_source:                           │         nodeId: node.id,
  │         有 download_url → window.open                │         title: node.title,
  │         无 → store.openNodeDetail(...)               │         mastery: node.mastery,
  │       · generated_resource:                         │       })
  │         store.openResource(userId,                   │
  │           resource_id)                               │   "查看全屏图谱" button
  │       · 其他/文本结果:                                │     → GraphModal (已有)
  │         store.openNodeDetail(...)                    │
  │                                                     │
  ├── 生成资源条目 onClick                                  │
  │     → store.openResource(userId,                     │
  │         f.resource_id)                               │
  │                                                     │
  └── ProfilePanel 瓶颈标签 onClick                        │
        → store.openNodeDetail({                         │
            title: t,                                    │
            (从 profile.bottleneck_topics 推断)            │
          })                                             │

SubagentCard (资源生成事件)
  │
  └── 资源生成完成 (status==="completed" 且 resource_type 字段存在)
        → 卡片底部显示 "查看资源 →" 按钮
        → onClick: store.openResource(userId, resource_id)
           (resource_id 从 tool_output 或 finalResult 中获取)
        → 数据源: SSE ToolStatusEvent.resource_type + resource_id (需前端聚合)

AgentChatPanel
  │
  └── SSE stream 结束检测:
        → 遍历 messages[].finalResult
        → 若含 resource_generation:
           MessageBubble 中已有的 ResourceCard
           在卡片底栏添加 "全屏预览" 按钮
           → onClick: store.openResource(userId, resource.resource_id)
```

## 函数级收口与内部逻辑

### resourcePreviewStore.ts (新增)

```
createResourcePreviewStore(): ZustandStore

State:
  drawerOpen: boolean = false
  drawerResource: ResourceDetail | null = null
  drawerLoading: boolean = false
  nodeDetailOpen: boolean = false
  nodeDetailData: NodeDetailData | null = null
  searchQuery: string = ""  // BuddyMemoryCloud tag click → KB search

Actions:
  openResource(userId: number, resourceId: string): Promise<void>
    - 输入: user_id (来自 authStore), resource_id (来自 ResourceSummary.resource_id)
    - 内部逻辑:
      1. set {drawerLoading: true, drawerOpen: true}
      2. const {material} = await fetchResourceDetail(userId, resourceId)
      3. if material: set {drawerResource: material, drawerLoading: false}
      4. else: set {drawerOpen: false, drawerLoading: false} // API fail → close
    - 输出: void, 副作用将 ResourceDetail 写入 store → CourseLayout 中 Drawer 自动渲染
    - 调用的外部模块: fetchResourceDetail from api/generativeApi

  openNodeDetail(data: NodeDetailData): void
    - 输入: NodeDetailData = {
        nodeId: string,     // 知识节点 ID
        title: string,      // 节点标题（来自 API）
        summary?: string,   // 节点描述（来自 API node.summary）
        mastery?: {label: "weak"|"learning"|"mastered", score: number},
        group?: string,     // 图谱分组 (用于颜色)
        growth_stage?: "seed"|"sprout"|"fruit",
        related_resources?: {resource_id, title, resource_type}[],  // 关联资源
        meta?: Record<string, unknown>  // 其他 API 元数据
      }
    - 内部逻辑: set {nodeDetailData: data, nodeDetailOpen: true}
    - 输出: void

  closeDrawer(): void → set {drawerOpen: false, drawerResource: null}
  closeNodeDetail(): void → set {nodeDetailOpen: false, nodeDetailData: null}
  closeAll(): void → set {drawerOpen: false, nodeDetailOpen: false}
  setSearchQuery(q: string): void → set {searchQuery: q}

  ⛔ 严格禁止: 无 mock 数据、无 fallback 假资源、无硬编码 resource_id
```

### NodeDetailPanel.tsx (新增)

```
NodeDetailPanel(): JSX.Element | null
  - 从 store 读取: {nodeDetailOpen, nodeDetailData}
  - 内部逻辑:
    1. if !nodeDetailOpen || !nodeDetailData → return null
    2. 渲染右侧滑出面板 (~320px 宽):
       ┌─────────────────────────────────┐
       │ ✕ 关闭                           │
       │                                 │
       │ [growth_stage icon] title (16px) │
       │ summary (12px, 多行)             │
       │                                 │
       │ ┌ 掌握度 ─────────────────────┐  │
       │ │ mastery badge: color-coded  │  │
       │ │ score bar: 0-1 → 百分比宽度 │  │
       │ └────────────────────────────┘  │
       │                                 │
       │ ┌ 关联资源 ───────────────────┐  │
       │ │ 如果有 related_resources:   │  │
       │ │ 每项 → onClick:             │  │
       │ │   store.openResource(id)     │  │
       │ │ 如无: "暂无关联资源"         │  │
       │ └────────────────────────────┘  │
       │                                 │
       │ [在图谱中定位] (button)          │
       │ [和智能体讨论] (button)          │
       └─────────────────────────────────┘
    3. "在图谱中定位" → 如果当前在 LearningTreePage:
       - 滚动到 D3 图区域
       - 在图上高亮对应 nodeId
       - 实现: LearningTreePage 监听 store.nodeDetailData.nodeId 变化 → setHighlightPath([nodeId])
    4. "和智能体讨论" → navigate(`/learn/${syllabusId}/agent`)
    5. 关闭 → store.closeNodeDetail()
  - 输入: 从 store 读取 (间接)
  - 输出: JSX.Element | null
  - 渲染位置: 由 CourseLayout 按需 render（在右侧栏或浮动面板）
  - ⛔ 严格禁止: 无数据时渲染假面板
```

### CourseLayout.tsx (修改)

```
CourseLayout()
  - 新增:
    ├── 从 store 读取: {drawerOpen, drawerResource, nodeDetailOpen, nodeDetailData}
    ├── <ResourcePreviewDrawer
    │     open={drawerOpen}
    │     resource={drawerResource}
    │     onClose={() => store.closeDrawer()}
    │   />
    └── <NodeDetailPanel />  // 内部自己从 store 读取，无需 props
  - 不影响已有布局结构
```

### CourseMaterials.tsx (修改)

```
CourseMaterials({ materials, loading })
  - 修改: 每个材料卡片从 <div> 改为可点击元素
  - onClick 逻辑:
    1. 从 API 返回的 file_id + path 推断文件类型 (后缀: .pdf/.md/.txt/.pptx/.zip/...)
    2. 可预览格式 (pdf, md, txt):
       → store.openFilePreview(file_url, title)
       → 渲染 <FilePreviewModal>:
         · PDF: <iframe src={file_url}> 浏览器原生 PDF 查看器 (自带缩放/搜索/下载)
         · MD/TXT: <pre> 文本渲染
    3. 不可预览格式 (pptx, zip 等):
       → window.open(download_url, '_blank') 直接下载
    4. 无 url → 不做交互（保持静态）
  - 视觉: 可点击时 cursor-pointer + hover:shadow-md

  ⚠️ 注意: CourseMaterials 中的 materials 来自 /api/file_list_graph_files。
  API 返回的 files[] 包含: file_id, filename, path, source。
  - 需要从 path/filename 提取文件扩展名判断预览能力
  - download_url 由后端 /api/file_list_graph_files 返回或需拼接
```

### FilePreviewModal (新增，集成在 resourcePreviewStore 中)

```
FilePreviewModal
  - State (在 store 中):
    filePreviewOpen: boolean
    filePreviewUrl: string | null
    filePreviewTitle: string
    filePreviewType: "pdf" | "text" | null

  - Store action: openFilePreview(url, title)
    1. 从 url 后缀判断 type
    2. set {filePreviewOpen: true, filePreviewUrl: url, filePreviewTitle: title, filePreviewType: type}

  - 渲染 (在 CourseLayout 中):
    · 半透明遮罩 Modal (max-w-4xl, max-h-[90vh])
    · PDF: <iframe src={url} className="w-full h-[80vh]">
    · 文本: <pre className="overflow-auto max-h-[80vh] p-4">{fetched_text}</pre>
    · 顶栏: title + 关闭按钮 + "新窗口打开" 按钮

  - ⚠️ 跨域注意: 如果文件 URL 是 OSS/COS 外链，iframe 需要服务端配 CORS 或同域代理
```

### store 补充 action

```
openFilePreview(url: string, title: string): void
  - 输入: url (文件下载/预览 URL), title (文件名)
  - 内部逻辑:
    1. const ext = url.split('.').pop()?.toLowerCase()
    2. const type = ext === 'pdf' ? 'pdf' : ['md','txt','json','yaml','yml'].includes(ext||'') ? 'text' : null
    3. if type: set {filePreviewOpen: true, filePreviewUrl: url, filePreviewTitle: title, filePreviewType: type}
    4. else: 不做预览, 这是一个需要下载的格式
  - 输出: void

closeFilePreview(): void → set {filePreviewOpen: false, filePreviewUrl: null, filePreviewTitle: '', filePreviewType: null}
```

### GeneratedResources.tsx (修改)

```
GeneratedResources({ resources, loading })
  - 修改: 每个资源卡片从 <div> 改为 <button> (或 div + onClick)
  - onClick 逻辑:
    1. const uid = useAuthStore(s => s.student).userId
    2. store.openResource(uid, r.resource_id)
  - 视觉: 添加 cursor-pointer + hover:shadow-md + hover:border-accent/30
  - 数据源: r 来自 fetchResourceList → ResourceSummary (含 resource_id)
```

### LearningTreePage.tsx (修改)

```
LearningTreePage()
  - 修改: D3GraphViewer 处传入 onNodeClick
  - 新增 handleNodeClick:
    (node: GraphNode) => {
      if (!node.meta) return;
      store.openNodeDetail({
        nodeId: node.id,
        title: node.label,
        group: node.group,
        mastery: node.meta.mastery_score != null ? {
          label: node.group === "mastered" ? "mastered" :
                 node.group === "weak" ? "weak" : "learning",
          score: node.meta.mastery_score as number
        } : undefined,
        summary: node.meta.summary as string,
        growth_stage: node.meta.growth_stage as string,
      });
    }
  - 新增: useEffect 监听 store.nodeDetailData.nodeId 变化 → 设置 highlightPath
    (让 NodeDetailPanel 的"在图谱中定位"功能生效)
```

### RightSidebar.tsx (修改: KnowledgeBasePanel)

```
KnowledgeBasePanel({ syllabusId })
  - 修改点 1: 搜索结果条目 onClick
    - 现有: toggleExpand(r.rank) 展开/收起
    - 改为: 同时判断 matchedSources 关联
      · 找到 matchedSources.find(s => s.matched_source === r.source)
      · 若为 generated_resource → store.openResource(uid, s.resource_id)
      · 若为 knowledge_source 且有 download_url → window.open
      · 否则 → store.openNodeDetail({nodeId: r.source, title, ...})

  - 修改点 2: 生成资源条目 (genFiles)
    - 现有: 纯 <div>
    - 改为: <button onClick={() => store.openResource(uid, f.resource_id)}>

  - 修改点 3: 知识源文件条目 (kFiles)
    - 现有: <a href={f.download_url}> (✅ 已有链接)
    - 保持不变

  - 修改点 4: D3 关联图谱 (KB_MOCK_GRAPH → 改为真实数据)
    - KB_MOCK_GRAPH 硬编码假数据 → 从 matchedSources 构建
    - 传入 onNodeClick → store.openNodeDetail(...)

  - 修改点 5: ProfilePanel 瓶颈标签
    - 现有: <span>
    - 改为: <button onClick={() => store.openNodeDetail({title: t, ...})}>
```

### WeaknessAnalysis.tsx (修改)

```
WeaknessAnalysis({ nodes })
  - 修改: 每个 item <div> 改为 <button>
  - onClick 逻辑:
    (n: WeakNode) => store.openNodeDetail({
      nodeId: '',  // 薄弱节点仅 title 无 node_id
      title: n.title,
      mastery: { label: "weak", score: n.mastery_score },
      summary: n.problem || n.comment,
    })
  - 视觉: cursor-pointer + hover:bg-red-50
```

### ExploreGapList.tsx (修改)

```
ExploreGapList({ nodes })
  - 修改: 每个 gap item <div> 改为 <button>
  - onClick 逻辑:
    (n: ExploreNode) => store.openNodeDetail({
      nodeId: n.node_id,
      title: n.title,
      summary: n.summary,
      group: "buddy_hint",  // 小觉推荐
    })
  - 注意: 保留底部 "和智能体对话" 按钮链接 (已有)
```

### BuddyObservations.tsx (修改)

```
BuddyObservations({ notes })
  - 修改: 每个 ObsCard 改为 <button>
  - onClick 逻辑:
    (note: BuddyNote) => {
      store.closeAll();
      // 尝试在 D3 图中定位对应节点
      // 通过触发 store 中一个特殊 action，
      // LearningTreePage 监听后滚动到图并高亮
      store.highlightNodeInGraph(note.node_title);
    }
  - 新增 store action: highlightNodeInGraph(targetLabel: string)
    → set nodeHighlightTarget, LearningTreePage useEffect 监听
    → 在所有 nodes 中匹配 label === targetLabel
    → scrollIntoView + set highlightPath
```

### BuddyMemoryCloud.tsx (修改)

```
BuddyMemoryCloud({ tags })
  - 修改: 每个 tag pill <span> 改为 <button>
  - onClick 逻辑:
    (tag: MemoryTag) => {
      store.setSearchQuery(tag.tag);
      store.closeAll();
      // 导航到 KnowledgeBase 或滚动到 KB 面板
      // 将 tag 文本设置为搜索 query
    }
  - 视觉: cursor-pointer + hover:opacity-80
```

### InlineRecommendationCard.tsx (修改)

```
InlineRecommendationCard({ events })
  - 修改: 路径节点可视化区域中的节点圆形 <div> 改为 <button>
  - onClick 逻辑:
    (displayNode: {id, title, mastery, isCurrent}) => {
      store.openNodeDetail({
        nodeId: displayNode.id,
        title: displayNode.title,
        mastery: displayNode.mastery ? {
          label: displayNode.mastery,
          score: 0  // 推荐路径中无精确 score
        } : undefined,
      });
    }
  - 视觉: cursor-pointer + hover:scale-110 transition
```

### SubagentCard.tsx (修改)

```
SubagentCardList({ events })
  - 修改: 资源生成完成的事件条目底部添加 "查看资源" 链接
  - 判断条件:
    evt.status === "completed"
    && evt.resource_type
    && evt.resource_id  (或从 tool_output 中解析)
  - onClick: store.openResource(uid, resourceId)
  - 视觉: 文字链接 "→ 查看此资源" 在事件行末尾
  - 数据源: SSE ToolStatusEvent — resource_id/result.resource_id
    注意: 需检查 SSE 事件中 resource_id 的实际字段名
    (可能是 result.resource_id / metadata.resource_id / 或独立字段)
```

## ResourcePreviewDrawer 当前状态确认

`ResourcePreviewDrawer` 已完全实现以下功能，**无需修改**：
- Props: `{open: boolean, resource: ResourceDetail | null, onClose: () => void}`
- 支持 resource_type: documents (Markdown 渲染), mindmap (Mermaid 渲染), quiz (交互式答题), coding_practice (代码预览), ppt (slides 预览)
- 全屏切换 (fullscreen state)
- 15s 阅读时长上报 (resource_usage API)
- 测验提交 (submitQuizAttempt API)
- "反馈给 Agent" 按钮 (SSE 消息)

**需要注意的对接点**:
- `fetchResourceDetail(userId, resourceId)` → `{success, material: ResourceDetail}` 路径已通
- store 只需调用 `fetchResourceDetail` 并将 `material` 写入 `drawerResource`
- Drawer 通过 props 接收 resource，不直接调 API

## Decisions

### Decision 1: 使用 Zustand store 而非 props drilling
- **选择**: 新建 `resourcePreviewStore` 集中管理
- **理由**: 点击源分布在 10+ 个组件中，props drilling 需要从 CourseLayout 向下透传，改动范围过大。store 可以让任意组件直接调用 `openResource()` / `openNodeDetail()`，无需层层传参。
- **替代方案**: React context + 自定义 hook — 但 Zustand store 更轻量且已有项目惯例（authStore, agentStore, graphModalStore）

### Decision 2: NodeDetailPanel 放在 CourseLayout 层，不在每个页面各自渲染
- **选择**: CourseLayout 中渲染 NodeDetailPanel（作为浮动侧栏或右侧面板）
- **理由**: 跨页面共享（LearningTree/Syllabus/SubjectHome/Agent 都可能触发），统一管理避免重复
- **替代方案**: 在每个页面各自渲染 → 代码重复 + overlay z-index 冲突

### Decision 3: NodeDetailPanel 数据来自 D3 node.meta + store，不额外调 API
- **选择**: 点击 D3 节点时，将 node.meta 中已有数据传入 store，NodeDetailPanel 直接渲染，无需额外 API 请求
- **理由**: D3 node 的 meta 已包含 summary、mastery_score、growth_stage，从 study_graph API 获取。再次 fetch 是冗余的
- **例外**: 关联资源列表 (related_resources) 需要额外 API（后续 phase 补充）

### Decision 4: CourseMaterials PDF/文本 → iframe 页内预览，其他格式直接下载
- **选择**: PDF 用 `<iframe>` 浏览器原生查看器页内预览；MD/TXT 用 `<pre>` 渲染；PPTX/ZIP 直接下载
- **理由**: 浏览器内置 PDF 查看器成熟好用（缩放/搜索/打印）；iframe 零依赖零成本。AI 生成资源走 ResourcePreviewDrawer（结构化渲染），原始文件走 FilePreviewModal（原始内容渲染），两条路径互不干扰
- **替代方案**: pdfjs-dist → 更可控但增加 bundle；Google Docs Viewer → 依赖外部服务

### Decision 5: BuddyObservations → 图谱定位，不打开 NodeDetailPanel
- **选择**: 点击 buddy 观察卡片时滚动到 D3 图 + 高亮对应节点，而不打开 NodeDetailPanel
- **理由**: Buddy note 本身是学伴的"感受"，不是知识点数据。用户看到 note 后自然想看对应节点在图中的位置
