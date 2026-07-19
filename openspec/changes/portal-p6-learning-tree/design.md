## Context

LearningTreePage 渲染在 CourseLayout 内（232px 侧栏 + 顶栏由 portal-p3 覆盖）。页面由：顶栏布局切换 + Stats bar + 两栏布局（D3 图 + 分析卡片）+ 全宽 section（观察/记忆/建议）+ gap summary bar 组成。

`05-learning-tree.svg`（263 行）定义了精确的视觉规范。当前实现框架正确，但 5 个子组件有配色和结构偏差。

## Goals / Non-Goals

**Goals:**
- 重写 WeaknessAnalysis → 红色主题对齐 SVG lines 117-147
- 重写 ExploreGapList → 纯文本行对齐 SVG lines 150-186
- 重写 BuddyObservations → 全宽 "觉" 头像卡片对齐 SVG lines 190-216
- 重写 BuddyMemoryCloud → rx=6 pill 标签对齐 SVG lines 219-234
- 重写 BuddySuggestion → amber 全宽卡片对齐 SVG lines 237-243
- 验证 Stats bar 和 Gap summary bar

**Non-Goals:**
- 不修改 D3GraphViewer（已验证）
- 不修改 CourseLayout（portal-p3 覆盖）

## 影响文件范围

| 文件 | 操作 |
|------|------|
| `src/pages/LearningTreePage.tsx` | Stats bar 精确验证，gap bar 精确验证，数据传递 |
| `src/components/tree/WeaknessAnalysis.tsx` | 重写 |
| `src/components/tree/ExploreGapList.tsx` | 重写 |
| `src/components/tree/BuddyObservations.tsx` | 重写 |
| `src/components/tree/BuddyMemoryCloud.tsx` | 重写 |
| `src/components/tree/BuddySuggestion.tsx` | 重写 |

## 函数-API 级完整数据流

```
CourseLayout → <Outlet /> → LearningTreePage
  │
  ├── GET /api/study_graph/detail?user_id=N&syllabus_id=S
  │     → {graph: {tree: {nodes, edges, summary}}}
  │     → treeResponseToGraph() → base nodes+edges for D3
  │     → tree.nodes.filter(mastery.label==="weak") → weakNodes for WeaknessAnalysis
  │     → tree.summary → stats: {records, weakCount, mastery%, risk, hints}
  │
  ├── GET /api/study_buddy/tree?user_id=N&syllabus_id=S
  │     → {regions: {trunk, learned, explore}, nodes: {[id]: {title, summary, buddy_notes}}}
  │     → buddyRegionsToGraph() → buddy hint nodes for D3 overlay
  │     → regions.explore → exploreNodes for ExploreGapList
  │     → nodes[].buddy_notes → buddyNotes for BuddyObservations
  │
  ├── GET /api/study_buddy/memory?user_id=N&syllabus_id=S
  │     → {tags: [{tag, category, created_at}]}
  │     → memoryTags for BuddyMemoryCloud
  │
  ├── GET /api/study_buddy/synthesis?user_id=N&syllabus_id=S
  │     → {text: string}
  │     → synthesis for BuddySuggestion
  │
  └── Render:
        ├── ViewToggles (力导向/树状/层级/学伴视角)
        ├── StatsBar (5 stats + 学伴视角 badge)
        ├── D3GraphViewer (560×360) + overlay labels
        ├── WeaknessAnalysis (304×172 right column)
        ├── ExploreGapList (304×176 right column)
        ├── BuddyObservations (880×120 full width)
        ├── BuddyMemoryCloud (880×76 full width)
        ├── BuddySuggestion (880×56 full width)
        └── GapSummaryBar (880×30)
```

## 函数级收口与内部逻辑

### WeaknessAnalysis.tsx

#### `WeaknessAnalysis({ nodes }: { nodes: WeakNode[] }): JSX.Element`
- **输入**: `WeakNode[]` — `{title, problem, comment, mastery_score}`
- **输出**: `304×172 rx=12` 红色主题卡片
- **内部逻辑**:
  1. 若无数据: return null
  2. 渲染层序:
     - 卡片底板 `rect rx=12 fill=#fff stroke=#e2e8f0`
     - 红色 header: `rect rx=12 fill=#fef2f2` + 底部平铺 + title "薄弱点分析" 11px/700/#ef4444 + 副标题 "N 个薄弱集群" 9px/#94a3b8
     - Item 1-2 (红色): `284×36 rx=6 fill=#fef2f2 stroke=#fecaca`
       - 红点: `circle r=5 fill=#ef4444 op=0.15 stroke=#ef4444`
       - 标题: `11px/600/#0f172a` + score `8px/#ef4444 textAnchor=end`
       - 描述: `9px/#64748b`
     - Item 3+ (白色 compact): `284×32 rx=6 fill=#fff stroke=#f1f5f9` + amber 圆点
  3. **最大 3 项** (SVG 显示 3 项)
- **对照**: SVG lines 117-147

### ExploreGapList.tsx

#### `ExploreGapList({ nodes }: { nodes: ExploreNode[] }): JSX.Element`
- **输入**: `ExploreNode[]` — `{title, summary, node_id, associated_trunk}`
- **输出**: `304×176 rx=12` 紫色主题卡片
- **内部逻辑**:
  1. 若无数据: return null
  2. 渲染层序:
     - 紫色 header: `rect rx=12 fill=#ede9fe` + title "差了什么 · 待探索" 11px/700/#7c3aed + "N 项小觉推荐" 9px/#94a3b8
     - 每项: 纯文本行（无边框）
       - title: `11px/600/#0f172a`
       - 关联: `9px/#94a3b8 "← 关联: {trunk_title} ✓"`
     - Agent 链接: `284×16 rx=4 fill=#ede9fe` + "→ 和智能体对话，走一条推荐路径" 8px/600/#7c3aed
- **对照**: SVG lines 150-186

### BuddyObservations.tsx

#### `BuddyObservations({ notes }: { notes: BuddyNote[] }): JSX.Element`
- **输入**: `BuddyNote[]` — `{node_title, note, created_at, mastery_hint}`
- **输出**: `880×120 rx=12` 全宽白色卡片
- **内部逻辑**:
  1. 若无数据: return null
  2. 渲染层序:
     - 卡片底板 `rx=12 fill=#fff stroke=#e2e8f0`
     - Header: "学伴的观察" 13px/700/#0f172a + 副标题 10px/#94a3b8
     - Observation cards (最多 3): `rx=8 fill=#fafafa stroke=#f1f5f9`
       - "觉" 圆形头像: `circle r=6 fill=#ede9fe` + text "觉" 8px/#7c3aed textAnchor=middle
       - 引用: "「{note}」" 11px/#0f172a
       - 日期行: "{date} · mastery_hint: {hint}" 9px/#94a3b8
     - Card 1: `410×32` (左)
     - Card 2: `426×32` (右)
     - Card 3: `848×28` (全宽底行)
- **对照**: SVG lines 190-216

### BuddyMemoryCloud.tsx

#### `BuddyMemoryCloud({ tags }: { tags: MemoryTag[] }): JSX.Element`
- **输入**: `MemoryTag[]` — `{tag, created_at, category}`
- **输出**: `880×76 rx=12` 全宽白色卡片
- **内部逻辑**:
  1. 若无数据: return null
  2. 渲染层序:
     - 卡片底板 `rx=12 fill=#fff stroke=#e2e8f0`
     - Header: "学伴的记忆" 13px/700/#0f172a + 副标题 10px/#94a3b8
     - Tag pills: 每个 `rx=6`，高度 24px，宽度按内容自适应（min ~96px, max ~132px）
       - `category === "weak_pattern"` → `fill=#ede9fe` + `text 10px/#7c3aed`
       - `category === "strength"` → `fill=#dcfce7` + `text 10px/#16a34a`
     - "+N 条更早" text 10px/#94a3b8 (当 tags.length > 6)
- **对照**: SVG lines 219-234

### BuddySuggestion.tsx

#### `BuddySuggestion({ text }: { text?: string }): JSX.Element`
- **输入**: synthesis 文本
- **输出**: `880×56 rx=12` amber 全宽卡片
- **内部逻辑**:
  1. 若无 text: return null
  2. 渲染层序:
     - 卡片底板 `rx=12 fill=#fef3c7 stroke=#fde68a`
     - Buddy 头像: `circle r=10 fill=#6366f1` + 双眼 (r=2 fill=white) + 微笑 path
     - Title: "小觉的综合建议" 12px/700/#92400e
     - 副标题: "buddy LLM synthesis · 访问页面时按需生成" 9px/#b45309
     - 正文: synthesis text 11px/#b45309
- **对照**: SVG lines 237-243

### GapSummaryBar (in LearningTreePage.tsx)

#### Stats 计算
```ts
stats.records = tree.nodes.length  // 来自 study_graph
stats.weakCount = tree.nodes.filter(n => n.mastery?.label === "weak").length
stats.mastery = Math.round((tree.summary?.mastered_node_count ?? 0) / Math.max(tree.nodes.length, 1) * 100)
stats.risk = Math.min(Math.round(weakCount / Math.max(tree.nodes.length, 1) * 100), 100)
stats.hints = allNodes.filter(n => n.group === "buddy_hint").length  // 来自 buddy_tree
```

## Decisions

### Decision 1: BuddyObservations/BuddyMemoryCloud/BuddySuggestion 使用全宽布局
- **选择**: 这三个 section 从右侧 304px 侧栏移出，使用全宽 `880px` 布局
- **理由**: SVG lines 191, 221, 238 明确定义 `width=880`，与 D3 图左对齐

### Decision 2: WeaknessAnalysis 使用红色主题
- **选择**: Header `fill=#fef2f2`、红色卡片 `stroke=#fecaca`、红色圆点
- **理由**: SVG lines 119, 124 明确定义红色主题，非 amber

### Decision 3: Memory tag pill 使用 rx=6 长方形
- **选择**: `rx=6` 长方形 pill（非 rounded-full），宽度自适应内容
- **理由**: SVG 显示不同宽度的长方形标签 (132/128/104/108/96/104 px)，`rx=6` 产生圆角矩形非完美圆形
