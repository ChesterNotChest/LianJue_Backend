# Node Detail Panel

知识点详情面板：点击任意知识节点时，从右侧滑出展示完整信息。数据完全来自点击源已有的 API 数据（不额外调 API）。

## Requirements

### 触发条件
- `store.nodeDetailOpen === true` 且 `store.nodeDetailData !== null`
- 渲染位置：CourseLayout 层，作为浮动面板在右侧

### 显示内容（全部来自 store.nodeDetailData）

| 区域 | 数据源字段 | 显示方式 |
|------|-----------|---------|
| 标题 | `title` | 16px/700 带 growth_stage icon |
| 描述 | `summary` | 12px 多行文本 |
| 掌握度 | `mastery.label` + `mastery.score` | color-coded badge + 进度条 (score→百分比) |
| 生长阶段 | `growth_stage` | seed→🌱 / sprout→🌿 / fruit→🍎 icon + label |
| 图谱分组 | `group` | 对应颜色圆点 (mastered=green, learning=indigo, weak=red, buddy_hint=purple) |

### 操作按钮

| 按钮 | 行为 |
|------|------|
| "在图谱中定位" | 设置 store.highlightTarget → 滚动 D3 图并高亮 (仅在 LearningTreePage 中有效) |
| "和智能体讨论" | `navigate(\`/learn/${syllabusId}/agent\`)` |

### 约束
- ⛔ 无数据时不渲染（return null），不渲染空面板
- ⛔ 所有字段从 store 读取，不自行调 API
- ⛔ 无硬编码 mock 数据
- 关闭按钮 (`✕`) 在右上角
- 面板宽度 ~320px，背景白色，圆角 rx=12，有 shadow

## API/数据依赖

无额外 API 调用。数据由点击源组件从已有 API 数据中提供：
- D3 节点: study_graph API → node.meta
- 薄弱项: study_graph API → tree.nodes (mastery.label==="weak")
- 待探索: study_buddy/tree API → regions.explore
- 瓶颈标签: learning_profile_detail API → bottleneck_topics
