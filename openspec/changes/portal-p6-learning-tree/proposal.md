## Why

`05-learning-tree.svg`（263 行）是学习成长图谱页面的权威视觉规范。当前 LearningTreePage + 5 个子组件已在前轮 fixup 中搭建了框架（stats bar、D3 图、分析卡片），但部分子组件与 SVG 存在元素级偏差：

1. **WeaknessAnalysis** — SVG 使用红色主题（header `fill=#fef2f2`、卡片 `fill=#fef2f2 stroke=#fecaca`、红色圆点），当前使用 amber 配色。
2. **BuddyObservations** — SVG 使用内联 "觉" 字圆形头像 (r=6 fill=#ede9fe)、mastery_hint 内联显示、日期在文本行末。当前使用标题+徽章分离布局。
3. **BuddyMemoryCloud** — SVG 使用 `rx=6` 长方形 pill 标签（`132×24, 128×24` 等），当前使用 `rounded-full`。
4. **BuddySuggestion** — SVG 使用 amber 卡片 (`fill=#fef3c7 stroke=#fde68a`)、内含 buddy 表情头像。当前使用紫色渐变卡片。
5. **ExploreGapList** — SVG 使用纯文本行 + 关联前缀 "← 关联: xxx ✓"，当前使用边框卡片布局。
6. **Gap Summary Bar** — SVG 定义 `880×30 rx=8` 底部条，含 "+N 提示节点 · 覆盖 M 薄弱区 · 建议顺序" + "学伴视角 · 已开启" badge。当前已基本对齐但需精确验证。

## What Changes

### 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/pages/LearningTreePage.tsx` | 修改 | Gap summary bar 精确对齐，数据流增强 |
| `src/components/tree/WeaknessAnalysis.tsx` | 重写 | SVG 红色主题对齐 lines 117-147 |
| `src/components/tree/ExploreGapList.tsx` | 重写 | SVG 纯文本行列对齐 lines 150-186 |
| `src/components/tree/BuddyObservations.tsx` | 重写 | SVG "觉" 头像卡片对齐 lines 190-216 |
| `src/components/tree/BuddyMemoryCloud.tsx` | 重写 | SVG pill 标签对齐 lines 219-234 |
| `src/components/tree/BuddySuggestion.tsx` | 重写 | SVG amber 卡片对齐 lines 237-243 |

### SVG 元素逐行对照

#### 1. 顶栏布局切换（SVG lines 14-17）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 14 | 力导向 active | `64×28 rx=8 fill=#6366f1 opacity=0.1` + text 10px/600/#6366f1 |
| 15 | 树状 inactive | `48×28 rx=8 fill=#f1f5f9` + text 10px/#64748b |
| 16 | 层级 inactive | `48×28 rx=8 fill=#f1f5f9` + text 10px/#64748b |
| 17 | 学伴视角 | `72×28 rx=8 fill=#ede9fe stroke=#c4b5fd` + text 10px/600/#7c3aed |

**状态**: 基本对齐，需验证 each pill 的精确尺寸和颜色。

#### 2. Stats Bar（SVG lines 38-48）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 38 | 容器 | `880×46 rx=10 fill=#fff stroke=#f1f5f9 filter=url(#ss)` |
| 39 | 学习记录 | "学习记录" 9px/#94a3b8 + "18" 16px/800/#0f172a |
| 41 | 薄弱点 | "薄弱点" 9px/#94a3b8 + "8" 16px/800/#ef4444 |
| 43 | 掌握度 | "掌握度" 9px/#94a3b8 + "64%" 16px/800/#22c55e |
| 45 | 辍学风险 | "辍学风险" 9px/#94a3b8 + "中" 16px/800/#f59e0b |
| 47 | 小觉提示 | "小觉提示" 9px/#94a3b8 + "6" 16px/800/#7c3aed |
| 48 | 视角 badge | `120×32 rx=6 fill=#ede9fe` + "学伴视角 · 开启" 10px/600/#7c3aed |

**状态**: 基本对齐。数据源: `study_graph API tree.summary` + `buddy_tree nodes count`。

#### 3. D3 Graph 区域（SVG lines 53-113）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 55 | 容器 | `560×360 rx=14 fill=#fff stroke=#e2e8f0 filter=url(#ss)` |
| 56 | 标题栏 | `560×28 rx=14 fill=#fafafa` + info text 8px/#94a3b8 |
| 61-70 | 学生节点 | mastered: green r=14/12, learning: indigo r=14/12, weak: red dashed r=14/12 |
| 73-84 | Buddy hint 节点 | purple dashed r=12 + glow filter + 紫虚线连接 (stroke-dasharray=2,3) |
| 87-91 | 连接边 | `<line>` 连接学生节点 |
| 94-103 | 叠加标签 | "当前步骤" purple pill + dashed line; "薄弱集群 · 4 节点" red dashed rect; "小觉跟随提示" purple rect |
| 106-111 | 图例 | 4 项: 已掌握(green) / 学习中(indigo) / 薄弱(red dashed) / 小觉提示(purple dashed) |

**状态**: 已在前轮 fixup 中对齐。需验证 buddy hint 节点的 glow filter 和虚线样式。

#### 4. WeaknessAnalysis（SVG lines 117-147）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 118 | 卡片 | `304×172 rx=12 fill=#fff stroke=#e2e8f0` |
| 119 | 红色 header | `304×34 rx=12 fill=#fef2f2` + 底部平铺 rect |
| 120 | 标题 | `x=14 y=22 fontSize=11 fontWeight=700 fill=#ef4444` "薄弱点分析" |
| 121 | 副标题 | `x=220 y=22 fontSize=9 fill=#94a3b8` "4 个薄弱集群" |
| 124-129 | Weak item 1 | `284×36 rx=6 fill=#fef2f2 stroke=#fecaca` |
| | 红点 | `circle cx=14 cy=18 r=5 fill=#ef4444 opacity=0.15 stroke=#ef4444` |
| | 标题 | `x=26 y=14 fontSize=11 fontWeight=600 fill=#0f172a` |
| | 描述 | `x=26 y=28 fontSize=9 fill=#64748b` |
| | 分数 | `x=240 y=14 fontSize=8 fill=#ef4444` "score 0.38" |
| 132-138 | Weak item 2 | 同结构 |
| 140-146 | Weak item 3 | `284×32 rx=6 fill=#fff stroke=#f1f5f9` (compact, 非红色) + amber 圆点 |

**关键偏差**: 当前使用 amber 配色和不同卡片结构。SVG 明确使用红色主题，item 1-2 为红色高亮、item 3 为普通白色。

#### 5. ExploreGapList（SVG lines 150-186）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 151 | 卡片 | `304×176 rx=12 fill=#fff stroke=#e2e8f0` |
| 152 | 紫色 header | `304×34 rx=12 fill=#ede9fe` + 底部平铺 |
| 153 | 标题 | "差了什么 · 待探索" 11px/700/#7c3aed |
| 154 | 副标题 | "6 项小觉推荐" 9px/#94a3b8 |
| 157-180 | 6 个探索项 | 每行: `text fontSize=11 fontWeight=600 fill=#0f172a` + `text fontSize=9 fill=#94a3b8 "← 关联: xxx ✓"` (SVG lines 157-180) |
| 182-185 | Agent 链接 | `284×16 rx=4 fill=#ede9fe` + "→ 和智能体对话，走一条推荐路径" 8px/600/#7c3aed |

**关键偏差**: SVG 使用纯文本行（无卡片边框），每项一行。当前使用带边框的卡片+按钮布局。

#### 6. BuddyObservations（SVG lines 190-216）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 191 | 卡片 | `880×120 rx=12 fill=#fff stroke=#e2e8f0` — 全宽！ |
| 192 | 标题 | "学伴的观察" 13px/700/#0f172a |
| 193 | 副标题 | "小觉对节点的感受 · 跨对话持久化在 buddy_notes" 10px/#94a3b8 |
| 196-201 | Obs 1 | `410×32 rx=8 fill=#fafafa stroke=#f1f5f9` |
| | "觉" 头像 | `circle cx=14 cy=16 r=6 fill=#ede9fe` + text "觉" 8px/#7c3aed |
| | 引用文本 | `x=28 y=14 fontSize=11 fill=#0f172a` "DFS — 嘴上说理解了…" |
| | 日期+标签 | `x=28 y=27 fontSize=9 fill=#94a3b8` "2026-07-15 · mastery_hint: weaker" |
| 203-208 | Obs 2 | `426×32 rx=8` 右列，同结构 |
| 210-215 | Obs 3 | `848×28 rx=8` 全宽底行，同结构 |

**关键偏差**: SVG 使用 `880×120` **全宽**卡片（不是 304px 侧栏），3 个观察项使用 "觉" 字圆形头像 + 内联引用格式。当前使用 304px 侧栏 + 不同卡片样式。

#### 7. BuddyMemoryCloud（SVG lines 219-234）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 221 | 卡片 | `880×76 rx=12 fill=#fff stroke=#e2e8f0` — 全宽！ |
| 222 | 标题 | "学伴的记忆" 13px/700/#0f172a |
| 223 | 副标题 | "小觉关于你的跨对话笔记 · 最多 30 条 · 自然演化" 10px/#94a3b8 |
| 226-231 | 6 个 tag pill | 不等宽 `rx=6 fill=#ede9fe` (5 purple) + `fill=#dcfce7` (1 green positive) |
| 232 | "+2" | text "+2 条更早" 10px/#94a3b8 |

各标签规格:
| Tag | 宽度 | 颜色 |
|-----|------|------|
| "RowKey 热点反复挫败" | 132×24 rx=6 | #ede9fe (purple) |
| "喜欢短文档胜过视频" | 128×24 rx=6 | #ede9fe |
| "DFS 时容易放弃" | 104×24 rx=6 | #ede9fe |
| "分治策略掌握扎实" | 108×24 rx=6 | #dcfce7 (green) |
| "考试前会紧张" | 96×24 rx=6 | #ede9fe |
| "需要更多实操练习" | 104×24 rx=6 | #ede9fe |

**关键偏差**: SVG 使用长方形 `rx=6` pill（非 rounded-full），紫色/绿色双色，全宽布局。

#### 8. BuddySuggestion（SVG lines 237-243）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 238 | 卡片 | `880×56 rx=12 fill=#fef3c7 stroke=#fde68a` — 全宽 amber！ |
| 239 | Buddy 头像 | `circle cx=20 cy=20 r=10 fill=#6366f1` + 双眼 (r=2) + 微笑 path |
| 240 | 标题 | `x=40 y=20 fontSize=12 fontWeight=700 fill=#92400e` "小觉的综合建议" |
| 241 | 副标题 | `x=160 y=20 fontSize=9 fill=#b45309` "buddy LLM synthesis · 访问页面时按需生成" |
| 242 | 正文 | `x=40 y=40 fontSize=11 fill=#b45309` synthesis 文本 |

**关键偏差**: SVG 使用 amber 配色 + buddy 表情头像，全宽 `880×56`。当前使用紫色渐变卡片。

#### 9. Gap Summary Bar（SVG lines 246-250）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 247 | 容器 | `880×30 rx=8 fill=#fff stroke=#e2e8f0` |
| 248 | 文本 | "+6 提示节点 · 覆盖 4 薄弱区 · 建议优先顺序: 减治法 → BFS → 贪心策略" |
| 249 | 视角 badge | `240×22 rx=6 fill=#ede9fe` + "学伴视角 · 已开启" 9px/600/#7c3aed |

**状态**: 基本对齐，需验证。

## Capabilities

### Modified Capabilities
- `weakness-analysis`: 红色主题卡片——header `fill=#fef2f2`、item `fill=#fef2f2 stroke=#fecaca`、红色圆点 + score。数据源: `study_graph API tree.nodes (mastery.label="weak")`。
- `explore-gap-list`: 纯文本行列表——紫色 header `fill=#ede9fe`、每项 "title ← 关联: prerequisite ✓"、底部 agent 链接条。数据源: `buddy_tree API regions.explore`。
- `buddy-observations`: 全宽卡片——"觉" 圆形头像 + 引用文本 + mastery_hint + 日期内联。数据源: `buddy_tree API nodes[].buddy_notes`。
- `buddy-memory-cloud`: 全宽 tag cloud——长方形 `rx=6` pill，紫色/绿色双色。数据源: `study_buddy/memory API`。
- `buddy-suggestion`: Amber 全宽卡片——buddy 表情头像 + synthesis 文本。数据源: `study_buddy/synthesis API`。

## Impact

- **修改文件**: 6 个文件
- **不修改文件**: D3GraphViewer.tsx（已验证节点渲染）
- **SVG 对照**: `05-learning-tree.svg` 263 行全量
- **数据源**: study_graph API + study_buddy/tree API + study_buddy/memory API + study_buddy/synthesis API
