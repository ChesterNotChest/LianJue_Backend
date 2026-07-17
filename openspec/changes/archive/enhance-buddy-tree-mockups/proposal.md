## Why

当前 `frontend-portal-redesign` 的 SVG 设计稿 中，学伴（小觉）仅被表达为右下角 FAB 按钮，其完整六层能力体系（知识树、标签记忆、节点观察、主动消息、独立对话、学霸人设）在视觉稿中几乎不可见。05 学习成长图谱过度依赖 D3 图表达"差了什么"，缺乏文字描述和学伴观察笔记，信息密度不足以支撑比赛评审。

## What Changes

- **重绘 05-learning-tree.svg**：图谱下方增加三个文字信息区——"差了什么"待探索知识列表（含摘要和关联主干）、"学伴的观察"节点笔记卡片、"小觉的综合建议"文字段落。图谱适当缩小为信息区腾出空间。
- **扩展 04-agent.svg**：将 BuddyDrawer 滑出态加入右侧面板区域，展示完整学伴对话流（含主动提醒、用户回复、学伴回复、记忆标签自动写入），表达独立对话的实际效果。
- **表达学伴记忆**：在 05 或 04 中可视化 buddy_memory tags，展示学伴"记住了什么"。
- **表达节点观察**：在 05 的待探索列表中展示 buddy_notes 字段——学伴对特定知识节点的感受和观察备注。

## Capabilities

### New Capabilities

无需新增后端能力——所有数据源（BuddyTree.regions.explore、BuddyTreeNode.buddy_notes、buddy_memory tags、buddy_messages）已在后端实现，本变更仅涉及 SVG 设计稿 层面的视觉表达。

### Modified Capabilities

无现有 spec 修改。

## Impact

- 影响文件：`openspec/changes/frontend-portal-redesign/设计稿s/05-learning-tree.svg`（重绘）、`04-agent.svg`（扩展）
- 不涉及后端代码、API、前端组件
- 仅为 设计稿 视觉表达增强，属于 `frontend-portal-redesign` 变更的细化补充
