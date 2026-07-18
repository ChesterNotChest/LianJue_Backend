# Tree Component Click

LearningTreePage 的 4 个子组件（WeaknessAnalysis, ExploreGapList, BuddyObservations, BuddyMemoryCloud）添加点击交互。

## 影响文件

- `src/components/tree/WeaknessAnalysis.tsx`
- `src/components/tree/ExploreGapList.tsx`
- `src/components/tree/BuddyObservations.tsx`
- `src/components/tree/BuddyMemoryCloud.tsx`

## Requirements

### WeaknessAnalysis — 薄弱点条目

| 需求 | 说明 |
|------|------|
| onClick | `store.openNodeDetail({title: n.title, mastery: {label:"weak", score: n.mastery_score}, summary: n.problem \|\| n.comment})` |
| 视觉 | `cursor-pointer` + `hover:bg-red-50` |
| 数据源 | 来自 LearningTreePage: `tree.nodes.filter(n => n.mastery?.label === "weak")` |

### ExploreGapList — 待探索条目

| 需求 | 说明 |
|------|------|
| onClick | `store.openNodeDetail({nodeId: n.node_id, title: n.title, summary: n.summary, group: "buddy_hint"})` |
| 视觉 | `cursor-pointer` + `hover:bg-purple-50` |
| 数据源 | 来自 buddy_tree API: `regions.explore` |
| 底部 Agent 链接 | 保持不变 |

### BuddyObservations — 观察卡片

| 需求 | 说明 |
|------|------|
| onClick | `store.setNodeHighlightTarget(note.node_title)` — 滚动 D3 图 + 高亮对应节点 |
| 视觉 | `cursor-pointer` + `hover:bg-slate-100` |
| 不打开 NodeDetailPanel | Buddy note 是观察而非知识点，直接定位图谱 |
| 数据源 | 来自 buddy_tree API: `nodes[].buddy_notes` |

### BuddyMemoryCloud — 记忆标签

| 需求 | 说明 |
|------|------|
| onClick | `store.setSearchQuery(tag.tag)` — 设置搜索 query 并展开 KnowledgeBase 面板 |
| 视觉 | `cursor-pointer` + `hover:opacity-80` |
| 数据源 | 来自 `/api/study_buddy/memory`: `tags[].tag` |

## 约束
- 所有数据来自已有 API (study_graph, study_buddy/tree, study_buddy/memory)
- 不使用假数据
- 保持组件现有 SVG 对齐样式不变
