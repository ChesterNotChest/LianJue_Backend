## Why

全量扫描发现：**26 个资源/知识点展示点位中，仅 3 个有跳转**（KnowledgeBase 知识源下载、VideoGrid 外链、ExploreGapList→agent 按钮）。其余 23 个纯展示，无 onClick、无 navigation、无 preview。存在系统性「展示-交互」断连：

```
展示层 (渲染)              交互层 (点击)           目标 (跳转/预览)
─────────────────────────────────────────────────────────────────
薄弱知识点      ──────▶      ❌ 断连       ──────▶   ?
待探索节点      ──────▶      ❌ 断连       ──────▶   ?
学伴观察        ──────▶      ❌ 断连       ──────▶   ?
记忆标签        ──────▶      ❌ 断连       ──────▶   ?
D3图谱节点 ×4   ──────▶      ❌ 断连(handler已定义未传入) ─▶  ?
课程资料卡片    ──────▶      ❌ 断连       ──────▶   ?
生成资源卡片    ──────▶      ❌ 断连       ──────▶   ?
图谱搜索条目    ──────▶      ❌ 断连       ──────▶   ?
瓶颈知识点标签  ──────▶      ❌ 断连       ──────▶   ?
推荐路径节点    ──────▶      ❌ 断连       ──────▶   ?
```

关键问题：`D3GraphViewer.onNodeClick` 和 `GraphModal.onNodeClick` 接口早已定义好，**全项目 4 处 D3GraphViewer 使用 + 2 处 GraphModal 使用无一传入实现**。`ResourcePreviewDrawer`（支持文档/导图/测验/练习/PPT 全屏预览）也已实现完成，但仅被 MessageBubble 的 `ResourceCard` 通过 `onOpenInModal` 触发——课程首页的大量资源卡片完全未接入。

## What Changes

### Phase 1: 核心基础设施 — 资源导航 Store + NodeDetailPanel

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/stores/resourcePreviewStore.ts` | **新增** | Zustand store：统一管理 ResourcePreviewDrawer 的 open/close + 资源数据获取 |
| `src/components/resource/NodeDetailPanel.tsx` | **新增** | 知识点详情侧栏/弹窗：标题、描述、掌握度、关联资源列表、在 D3 图谱中查看、打开 Agent |
| `src/layouts/CourseLayout.tsx` | 修改 | 集成 ResourcePreviewDrawer + NodeDetailPanel 到课程子页面容器中 |

### Phase 2: SubjectHome 资源卡片 → ResourcePreviewDrawer

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/subject/CourseMaterials.tsx` | 修改 | 卡片添加 onClick → PDF/MD/TXT iframe 页内预览 (FilePreviewModal)，其他格式直接下载 |
| `src/components/subject/GeneratedResources.tsx` | 修改 | 卡片添加 onClick → 打开 ResourcePreviewDrawer 全屏查看 |

### Phase 3: D3 图谱节点 → NodeDetailPanel

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/pages/LearningTreePage.tsx` | 修改 | 传入 onNodeClick → 打开 NodeDetailPanel |
| `src/layouts/RightSidebar.tsx` | 修改 | KnowledgeBase 关联图谱传入 onNodeClick |
| `src/components/graph/GraphModal.tsx` | 修改 | App.tsx 处传入 onNodeClick → NodeDetailPanel |
| `src/pages/KnowledgeGalaxyPage.tsx` | 修改 | 传入 onNodeClick（如适用） |

### Phase 4: Tree 子组件 → 跳转

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/tree/WeaknessAnalysis.tsx` | 修改 | 薄弱知识点条目添加 onClick → NodeDetailPanel |
| `src/components/tree/ExploreGapList.tsx` | 修改 | 待探索条目添加 onClick → NodeDetailPanel |
| `src/components/tree/BuddyObservations.tsx` | 修改 | 观察卡片添加 onClick → 定位 D3 图中对应节点 |
| `src/components/tree/BuddyMemoryCloud.tsx` | 修改 | Tag pill 添加 onClick → KnowledgeBase 搜索该 tag |

### Phase 5: Agent 页 → 跳转

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/layouts/RightSidebar.tsx` | 修改 | KnowledgeBase: 搜索结果条目 onClick → NodeDetailPanel；生成资源条目 onClick → ResourcePreviewDrawer；ProfilePanel 瓶颈标签 onClick → NodeDetailPanel |
| `src/components/chat/InlineRecommendationCard.tsx` | 修改 | 路径节点 onClick → NodeDetailPanel |
| `src/components/chat/SubagentCard.tsx` | 修改 | 资源生成完成事件 → 点击打开 ResourcePreviewDrawer |
| `src/components/chat/AgentChatPanel.tsx` | 修改 | 集成 ResourcePreviewDrawer（SSE 流结束时检测资源生成结果） |

## Capabilities

### New Capabilities
- **resource-navigation-store**: 统一的资源/知识点导航 Zustand store——`openResource(resourceId)`, `openNodeDetail(nodeId)`, `openFilePreview(url, title)`, `closeAll()`
- **node-detail-panel**: 知识点详情面板——展示 title/summary/mastery/growth_stage/关联资源列表/图谱定位/Agent 跳转操作
- **file-preview-modal**: 原始文件页内预览——PDF 用 `<iframe>` 浏览器原生查看器，MD/TXT 用 `<pre>` 文本渲染
- **resource-preview-wire**: 资源卡片→ResourcePreviewDrawer 的通路——`fetchResourceDetail()` → 打开 Drawer

### Modified Capabilities
- **course-materials-click**: CourseMaterials 卡片 onClick → 文件下载或预览
- **generated-resources-click**: GeneratedResources 卡片 onClick → fetchResourceDetail + ResourcePreviewDrawer
- **d3-node-click**: LearningTreePage/GraphModal/KnowledgeBase 图谱节点 onClick → NodeDetailPanel
- **weakness-analysis-click**: 薄弱项条目 onClick → NodeDetailPanel 或图谱定位
- **explore-gap-click**: 待探索条目 onClick → NodeDetailPanel 或图谱定位
- **buddy-observation-click**: 观察卡片 onClick → 图谱定位对应节点
- **memory-tag-click**: 标签 onClick → KnowledgeBase 搜索
- **kb-search-result-click**: 搜索结果条目 onClick → NodeDetailPanel；生成资源条目 onClick → ResourcePreviewDrawer
- **profile-bottleneck-click**: 瓶颈标签 onClick → NodeDetailPanel
- **inline-rec-node-click**: 推荐路径中的知识点节点 onClick → NodeDetailPanel
- **subagent-resource-click**: 子代理资源生成事件 onClick → ResourcePreviewDrawer

## Impact

- **新增文件**: 2 个（resourcePreviewStore.ts, NodeDetailPanel.tsx）；FilePreviewModal 内嵌在 store + CourseLayout 中
- **修改文件**: 12 个
- **不修改文件**: D3GraphViewer.tsx（接口已完备，仅需传入回调）
- **依赖 API**: `fetchResourceDetail()` (已实现), `study_graph/detail` (已实现), `study_buddy/tree` (已实现), `study_buddy/memory` (已实现)
- **严格禁止**: 假数据、硬编码 mock、未经验证的 API 字段映射
