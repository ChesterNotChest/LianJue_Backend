# Resource Preview Store

统一的资源/知识点导航 Zustand store，消除 10+ 组件间的 props drilling。

## State

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `drawerOpen` | boolean | false | ResourcePreviewDrawer 是否打开 |
| `drawerResource` | ResourceDetail \| null | null | 当前预览的资源数据 |
| `drawerLoading` | boolean | false | 资源数据是否加载中 |
| `nodeDetailOpen` | boolean | false | NodeDetailPanel 是否打开 |
| `nodeDetailData` | NodeDetailData \| null | null | 当前展示的知识点数据 |
| `nodeHighlightTarget` | string \| null | null | BuddyObservations 触发的图谱节点高亮目标 |
| `searchQuery` | string | "" | BuddyMemoryCloud tag click → KnowledgeBase 搜索关键词 |

## Actions

### openResource(userId, resourceId)
- **触发者**: GeneratedResources, KnowledgeBase genFiles, SubagentCard, MessageBubble
- **输入**: `userId: number`, `resourceId: string`
- **行为**: 调用 `fetchResourceDetail(userId, resourceId)` → 写入 `drawerResource` → `drawerOpen = true`
- **错误处理**: API 失败则保持 `drawerOpen = false`
- **禁止**: 无 mock fallback

### openNodeDetail(data)
- **触发者**: D3 onNodeClick, WeaknessAnalysis, ExploreGapList, KnowledgeBase results, ProfilePanel bottlenecks, InlineRecommendationCard
- **输入**: `NodeDetailData { nodeId, title, summary?, mastery?, group?, growth_stage?, meta? }`
- **行为**: 立即写入 `nodeDetailData` → `nodeDetailOpen = true`
- **无 API 调用**（数据来自组件已有的 API 数据）

### closeDrawer / closeNodeDetail / closeAll
- **行为**: 对应重置 state 字段

### setSearchQuery(q)
- **触发者**: BuddyMemoryCloud tag click
- **输入**: `q: string`
- **行为**: 写入 `searchQuery`

### setNodeHighlightTarget(label)
- **触发者**: BuddyObservations card click
- **输入**: `label: string`
- **行为**: 写入 `nodeHighlightTarget`；LearningTreePage useEffect 监听此字段变化 → D3 图滚动到对应节点并高亮
