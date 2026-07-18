# Agent Page Click

Agent 页面（RightSidebar + InlineRecommendationCard + SubagentCard）的资源点击跳转。

## 影响文件

- `src/layouts/RightSidebar.tsx` (KnowledgeBasePanel + ProfilePanel)
- `src/components/chat/InlineRecommendationCard.tsx`
- `src/components/chat/SubagentCard.tsx`

## Requirements

### KnowledgeBasePanel — 搜索结果条目

| 条目类型 | onClick | 说明 |
|---------|---------|------|
| knowledge_source (有 download_url) | `window.open(url)` | 保持现有 `<a>` 行为 |
| knowledge_source (无 download_url) | `store.openNodeDetail(...)` | 标题+source 作为 node 信息 |
| generated_resource | `store.openResource(userId, resource_id)` | → ResourcePreviewDrawer |
| 纯文本结果 | `store.openNodeDetail({title, ...})` | 使用 result.title + result.content |

### KnowledgeBasePanel — 生成资源条目 (genFiles)

| 需求 | 说明 |
|------|------|
| 从 `<div>` 改为 `<button>` | cursor-pointer + hover:bg-slate-50 |
| onClick | `store.openResource(userId, f.resource_id)` |

### KnowledgeBasePanel — 知识源文件条目 (kFiles)

| 需求 | 说明 |
|------|------|
| 保持现有 `<a href={download_url}>` | ✅ 已有链接，保持不变 |

### KnowledgeBasePanel — D3 关联图谱

| 需求 | 说明 |
|------|------|
| 替换 KB_MOCK_GRAPH | 从 `matchedSources` + `reasoningEdges` 构建真实图谱 |
| 节点: matchedSources 中每个 source 为一个节点 | id=source.id, label=source.title |
| 边: reasoningEdges 中每对 source→target | 类型为 "reasoning" |
| 传入 onNodeClick | `store.openNodeDetail(...)` |

### ProfilePanel — 瓶颈知识点标签

| 需求 | 说明 |
|------|------|
| 从 `<span>` 改为 `<button>` | cursor-pointer + hover:opacity-80 |
| onClick | `store.openNodeDetail({title: t, mastery: {label: "weak", score: 0}})` |
| 数据源 | `profile.bottleneck_topics` (来自 learning_profile_detail API) |

### InlineRecommendationCard — 路径节点

| 需求 | 说明 |
|------|------|
| 路径可视化区域的节点圆形改为 `<button>` | cursor-pointer + hover:scale-110 transition |
| onClick | 从 displayNodes 中获取 node title + mastery → `store.openNodeDetail(...)` |

### SubagentCard — 资源生成事件

| 需求 | 说明 |
|------|------|
| 已完成资源生成事件底部加 "→ 查看此资源" 链接 | 仅当 `status === "completed"` 且 `resource_type` 存在 |
| onClick | `store.openResource(userId, resourceId)` |
| resourceId 来源 | 从 `ToolStatusEvent` 的 `result.resource_id` 或 `metadata.resource_id` 字段获取 |
| ⚠️ 需验证 | SSE 事件中 resource_id 的实际字段名（查看 `agent_tools.py` 中 resource 生成 tools 的 output） |

## 约束
- 所有 API 数据来源已存在 (`/api/knowledge/search`, `/api/generative_detail`, `learning_profile_detail`)
- 不修改后端代码
- 不用假数据
