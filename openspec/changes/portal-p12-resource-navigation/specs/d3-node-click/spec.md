# D3 Node Click

为所有 D3GraphViewer 使用点传入 `onNodeClick` 回调，点击节点时打开 NodeDetailPanel。

## 影响文件

- `src/pages/LearningTreePage.tsx`
- `src/layouts/RightSidebar.tsx` (KnowledgeBasePanel)
- `src/App.tsx` (AgentPage → GraphModal)
- `src/pages/KnowledgeGalaxyPage.tsx`

## Requirements

### LearningTreePage

| 需求 | 说明 |
|------|------|
| 传入 `onNodeClick` | `D3GraphViewer` props 新增 `onNodeClick={handleNodeClick}` |
| handleNodeClick 逻辑 | 从 `GraphNode.meta` 提取 `mastery_score`, `summary`, `growth_stage` → `store.openNodeDetail(...)` |
| group → mastery.label 映射 | `mastered` → `"mastered"`, `weak` → `"weak"`, 其他 → `"learning"` |
| "在图谱中定位" 联动 | `useEffect` 监听 `store.nodeDetailData?.nodeId` 变化 → 设置 D3 highlightPath |

### RightSidebar KnowledgeBasePanel

| 需求 | 说明 |
|------|------|
| D3 关联图谱 | 传入 `onNodeClick` → `store.openNodeDetail(...)` |
| 替换 KB_MOCK_GRAPH | 从 `matchedSources` + `reasoningEdges` 构建真实图谱节点 |
| 图谱节点数据 | `matchedSources[].matched_source` → node.id/label |

### App.tsx GraphModal

| 需求 | 说明 |
|------|------|
| 传入 `onNodeClick` | `GraphModal` props 新增 `onNodeClick={handleNodeClick}` |
| handleNodeClick | `store.openNodeDetail(...)` (同 LearningTreePage) |

### KnowledgeGalaxyPage

| 需求 | 说明 |
|------|------|
| 如有 D3GraphViewer | 传入 `onNodeClick` |

## 约束
- D3GraphViewer.tsx **不修改**（接口已完备）
- 所有节点数据来自已有 API (study_graph, buddy_tree)
- 不额外调 API 获取节点详情
