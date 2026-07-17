## ADDED Requirements

本 spec 覆盖学伴悬浮窗交互和学习成长图谱页面的功能需求。数据源（BuddyTree、buddy_notes、buddy_memory tags、buddy_messages）已在 `study-buddy` spec 中定义。

### Requirement: 学伴悬浮窗对话

Buddy FAB SHALL 触发的悬浮客服式聊天窗口——浮在主内容区上方、固定右下位置（不可拖拽）、不阻断页面操作、可最小化回 FAB。悬浮窗为全域组件：在任意课程页点击 FAB 均弹出同一悬浮窗，不导航到 Agent 页。

#### Scenario: 查看悬浮窗对话
- **WHEN** 用户在任意课程页点击 Buddy FAB 或自动弹出气泡
- **THEN** 弹出紧凑悬浮聊天窗口（~340×420），固定浮在主内容区右下区域。展示完整对话流，包含主动提醒、用户消息、学伴回复，以及学伴自主写入记忆标签（create_memory_tag）的指示

#### Scenario: 悬浮窗最小化
- **WHEN** 用户点击悬浮窗最小化按钮
- **THEN** 悬浮窗关闭，FAB 恢复默认态（保留未读红点如有未读消息）

#### Scenario: 悬浮窗固定位置
- **WHEN** 悬浮窗展开
- **THEN** 窗口保持固定位置，不随页面滚动移动，不支持拖拽

### Requirement: FAB 自动弹出最新推送气泡

Buddy FAB SHALL 在收到新的主动推送消息时自动弹出气泡展示消息内容，无需用户 hover。气泡 5 秒后自动消失，FAB 保留未读红点。

#### Scenario: 新主动消息到达
- **WHEN** 学伴生成一条新的主动消息（如 resource_ready、plan_accepted 等事件触发）
- **THEN** FAB 自动弹出气泡展示消息内容，标注"自动弹出"标签，用户可点击关闭、点击气泡打开悬浮窗，或不做操作等待自动消失

#### Scenario: 气泡自动消失
- **WHEN** 气泡弹出后 5 秒内用户未操作
- **THEN** 气泡自动消失，FAB 保留未读红点标识

#### Scenario: 气泡手动关闭
- **WHEN** 用户点击气泡关闭按钮
- **THEN** 气泡立即消失，FAB 保留未读红点标识

### Requirement: 学习成长图谱展示待探索知识列表

LearningTreePage SHALL 在图谱右侧以文字卡片列表形式展示 BuddyTree 中 `explore` region 的所有节点，每项包含标题、知识摘要、关联主干路径和学伴最新观察备注。

#### Scenario: 查看待探索知识
- **WHEN** 用户浏览学习成长图谱页面
- **THEN** 图谱右侧展示"差了什么 — 待探索知识"区域，列出 4-6 个待探索节点，每个节点显示标题、摘要文本、关联的已掌握知识

### Requirement: 学伴标签记忆可视化

LearningTreePage SHALL 展示学伴记忆标签云，可视化 buddy_memory tags。

#### Scenario: 查看学伴记忆
- **WHEN** 用户浏览学习成长图谱页面
- **THEN** 展示"学伴的记忆"区域，包含 4-6 个自然语言记忆标签，反映学伴跨对话积累的关于该学生的观察

### Requirement: 学伴节点观察展示

LearningTreePage SHALL 展示学伴对特定知识节点的观察笔记（buddy_notes）。

#### Scenario: 查看学伴节点观察
- **WHEN** 用户浏览学习成长图谱页面
- **THEN** 展示"学伴的观察"区域，包含至少 2 条节点观察，每条包含节点名称、观察内容、记录时间和掌握度提示

### Requirement: 学伴综合建议生成

学伴小觉 SHALL 支持按需生成综合学习建议（synthesis 消息类型），以 buddy_tree 的 explore + weak_topics + buddy_notes 为上下文，生成 2-3 句自然语言建议。该消息持久化到 buddy_messages.jsonl 中，标记 `source: "synthesis"`，前端取最新一条展示在学习成长图谱页面底部。

#### Scenario: 生成综合建议
- **WHEN** 用户访问学习成长图谱页面且距上次 synthesis 超过 N 分钟（或从未生成）
- **THEN** 触发 buddy LLM 生成一条 synthesis 消息，综合 explore 待探索节点、薄弱点和学伴观察，输出 2-3 句学习优先级建议

#### Scenario: 缓存复用
- **WHEN** 用户在缓存窗口内再次访问学习成长图谱页面
- **THEN** 直接展示最近一条 synthesis 消息，不重复调用 LLM

### Requirement: Dashboard 推荐探索区块

Dashboard SHALL 展示"推荐探索"区块，调用 knowledge/search API 基于用户薄弱点获取推荐内容。

#### Scenario: 查看推荐探索
- **WHEN** 用户浏览 Dashboard 页面且存在薄弱点数据
- **THEN** 在"最近资源"和"实训项目"之间展示"推荐探索"区块，显示 top 2 搜索结果，每项包含匹配度百分比和基于薄弱点的推荐理由

---

## 图谱渲染引擎对照

本变更涉及的所有图谱 mockup 与前端渲染引擎的对应关系。实施时必须确保引擎能力覆盖以下每一项。

### 引擎清单

| 引擎 | 技术 | 使用场景 |
|------|------|---------|
| D3GraphViewer | d3-force + 自定义 tree/dagre 布局, SVG 渲染 | 学习成长图谱、终身学习图谱、推荐路径内联图、学伴树 |
| KnowledgeGalaxy | Three.js 3D WebGL | 知识图谱 3D 星系 (单课程 + 终身) |

### D3GraphViewer 能力映射

引擎代码: `src/components/graph/D3GraphViewer.tsx`
LayoutMode: `"force" | "tree" | "dagre"`
GROUP_COLORS: mastered(#22c55e) / learning(#3b82f6) / weak(#f59e0b) / unknown(#94a3b8) / prerequisite(#6366f1) / active(#6366f1) / chapter(#2563eb) / knowledge(#93c5fd) / resource(#34d399)

| SVG mockup 元素 | 引擎实现路径 | 状态 |
|----------------|-------------|------|
| **05 力导向图**: 绿/蓝/红节点 + 标签 + score 副标题 | `group` → GROUP_COLORS, `meta.mastery_score` → subtitle | ✅ 原生支持 |
| **05 边**: parent_of 箭头 | `type="parent_of"` → 箭头标记 | ✅ |
| **05 视图切换**: 力导向/树状/层级 | `layout="force"/"tree"/"dagre"` | ✅ |
| **05 学伴提示节点**: 紫色虚线 + glow | **需新增 `buddy_hint` 分组**: fill=#ede9fe, stroke=#7c3aed, stroke-dasharray=3,3 | ⚠️ 引擎缺少此分组 |
| **05 薄弱集群虚线框** | 不在节点层 — 前端额外绘制 `<rect>` 标注框 | ⚠️ 非引擎能力, 业务层叠加 |
| **05 当前步骤/小觉跟随提示 标签** | 不在节点层 — 前端 `<div>` overlay 标注 | ⚠️ 非引擎能力, 业务层叠加 |
| **01 终身图谱**: 跨课程 D3 力导向 | `get_student_lifelong_overview()` → nodes/edges → D3GraphViewer(layout="force") | ✅ |
| **01 课程标签框** (大数据概论/Python) | 不在节点层 — 前端额外渲染 | ⚠️ 业务层叠加 |
| **04 推荐路径内联图**: 节点水平序列 | D3GraphViewer(layout="dagre") + highlightPath | ✅ |
| **04 候选路径 A/B/C** | 不在图内 — 右侧 `candidates[]` 列表, 前端渲染 | ⚠️ 业务层叠加 |
| **04 "查看全屏图谱" 按钮** | `useGraphModalStore.openGraph()` → GraphModal (全屏玻璃遮罩 + D3GraphViewer) | ✅ |
| **11 学习成长图谱 + 学伴树** | 静态 SVG 占位 → 实际用 D3GraphViewer (tree layout) 渲染 | ✅ |
| **06/12 3D 星系** | KnowledgeGalaxy (Three.js) — 非 D3 | ✅ 独立引擎 |
| **Hover 高亮邻居** | D3GraphViewer 内置: mouseenter → dim non-neighbors | ✅ |
| **Zoom/Pan/拖拽** | d3-zoom + d3-drag | ✅ |
| **节点 tooltip** | `<title>` 元素: label + mastery_score + summary + difficulty 等 | ✅ |

### 学伴视角实现

"学伴视角"（05 顶栏第四个选项）不是新布局模式，而是**数据叠加**:
1. 从 `study_graph/detail` 取基础 nodes + edges
2. 从 `buddy_tree / regions.explore` 取额外节点, 标记为 `group: "buddy_hint"`
3. 合并后传给 D3GraphViewer
4. 前端在 D3GraphViewer 外层叠加薄弱集群标注框 + 当前步骤/小觉跟随提示标签

### 实施要求

- 新增 `GROUP_COLORS.buddy_hint` = `{fill: "#ede9fe", stroke: "#7c3aed", stroke-dasharray: "3,3"}`
- D3GraphViewer 的 `nodeRadius()` 需感知 buddy_hint 分组（较小半径, 12px）
- buddy_hint 节点的边使用虚线 `stroke-dasharray`, 低透明度 (0.3-0.5)
- 集群标注框、步骤标签等 overlay 元素在 D3GraphViewer 容器外部渲染, 跟随 zoom/pan 变换
