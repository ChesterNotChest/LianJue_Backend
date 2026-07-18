## Context

Dashboard 是用户登录后的着陆页，由 6 个子组件组成，数据来自 4 个 API 端点。`01-dashboard.svg`（332 行）定义了每个像素的视觉规范。

当前实现与 SVG 存在结构性偏差：CourseCardGrid 缺少进度/统计行，RecentResources/RecommendedExploration/GitHubProjects 的卡片结构与 SVG 定义的"上部 100px 色区 + 下部 60px 文本区"单体卡片模式不一致，LifelongGraph 右侧课程统计卡片过于简化。

本设计聚焦于逐元素对照 SVG，建立完整的函数级数据流。

## Goals / Non-Goals

**Goals:**
- 逐元素对照 `01-dashboard.svg` 所有 332 行，确保每个 SVG 元素在实现中有对应
- 定义每个函数的输入输出类型和内部算法逻辑
- 通过现有 API 获取所有数据，零假数据
- 为缺失的数据维度（per-syllabus 进度/统计）建立数据获取策略

**Non-Goals:**
- 不新增后端 API 端点（使用现有 API）
- 不修改 CourseThumbnail/DocThumbnail（由 portal-p1-thumbnails 覆盖）
- 不修改 GalaxyReveal（已验证对齐）

## 影响文件范围

| 文件 | 操作 | 变更范围 |
|------|------|---------|
| `src/pages/Dashboard.tsx` | 修改 | 移除重复欢迎区 + 添加 divider + per-syllabus 数据加载 |
| `src/components/dashboard/CourseCardGrid.tsx` | 重写 | 完整卡片: banner + metadata + progress + stats + buttons |
| `src/components/dashboard/RecentResources.tsx` | 重写 | 单体卡片: 上部 SVG + 下部文本，SVG 卡片结构 |
| `src/components/dashboard/RecommendedExploration.tsx` | 重写 | 缩略图卡片: document/mindmap 预览 + match% badge |
| `src/components/dashboard/GitHubProjects.tsx` | 重写 | 深色代码卡片: `{ }` 水印 + 语言条 + stars |
| `src/components/dashboard/LifelongGraph.tsx` | 重写 | 完整右侧卡片: 472×108 含顶条 + 统计 + 进度条 + 薄弱提示 |

## 函数-API 级完整数据流

### Dashboard 整体数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Dashboard.tsx                                 │
│                                                                      │
│  useAuthStore ──→ student (userId, userName, label, permission)     │
│                                                                      │
│  ┌─ loadData() ──────────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │  ① POST /api/syllabus_list {user_id}                          │  │
│  │     → {syllabuses: [{syllabus_id, title, graph_names,         │  │
│  │                      subject_title, status}]}                  │  │
│  │     → setSyllabuses() ──→ CourseCardGrid                      │  │
│  │                                                                │  │
│  │  ② POST /api/generative_list {user_id, limit:4}               │  │
│  │     → {materials: [ResourceSummary]}                           │  │
│  │     → setResources() ──→ RecentResources                      │  │
│  │                                                                │  │
│  │  ③ GET /api/knowledge/search?q=推荐学习&top_k=2               │  │
│  │     → {results: [{title, summary, score, ...}]}                │  │
│  │     → setRecommended() ──→ RecommendedExploration             │  │
│  │                                                                │  │
│  │  ④ GET /api/study_graph/detail?user_id=N                      │  │
│  │     → {graph: {tree, sibling_trees}}                           │  │
│  │     → setGraphNodes/Edges() ──→ LifelongGraph (left D3)       │  │
│  │     → setCourseStats() ──→ LifelongGraph (right cards)        │  │
│  │     → {summary: {learned_node_count, mastered_node_count,     │  │
│  │                   weak_node_count, tree_growth}}               │  │
│  │                                                                │  │
│  │  ⑤ POST /api/knowledge/github_search {query, max_results:3}   │  │
│  │     → {repos: [{full_name, description, stars, ...}]}         │  │
│  │     → setRepos() ──→ GitHubProjects                           │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ Per-Syllabus Progress (NEW) ─────────────────────────────────┐  │
│  │  for each syllabus:                                            │  │
│  │    GET /api/study_graph/detail?user_id=N&syllabus_id=S        │  │
│  │    → {graph: {tree: {summary: {mastered, learned, weak}}}}    │  │
│  │    → syllabusProgressMap[syllabus_id] = {mastered, total,     │  │
│  │        weak_nodes: [...], last_active}                          │  │
│  └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### CourseCardGrid 数据流

```
Dashboard.tsx
  ├── syllabuses: SyllabusItem[]
  ├── syllabusProgressMap: Record<number, SyllabusProgress>  ← NEW
  │
  └── <CourseCardGrid syllabuses={s} progressMap={p} />
        │
        └── for each syllabus:
              ├── <CourseThumbnail title={title} subtitle={graph_names[0]} draft={status==="draft"} />
              ├── WeekSemesterLine({syllabus})  ← NEW
              ├── StatusBadge({status})  (modified: SVG exact)
              ├── ProgressBar({progress%})  ← NEW (from progressMap)
              ├── MasteryStats({mastered, weak, lastActive})  ← NEW
              └── ActionButtons({syllabus_id, isDraft})
```

### RecentResources 数据流

```
Dashboard.tsx
  ├── resources: ResourceSummary[]
  │
  └── <RecentResources resources={r} onRefresh={loadData} />
        │
        └── for each resource:
              └── ResourceCard({resource})  ← NEW component
                    ├── TopSection({type}) — 100px 类型色彩区 + SVG 图标
                    │     ├── documents: #eff6ff + 文档折角 SVG
                    │     ├── mindmap: #ecfdf5 + 思维导图 SVG
                    │     ├── quiz: #fffbeb + "?" 水印 + 选项框
                    │     ├── coding_practice: #1e293b + monospace 代码
                    │     └── ppt: #fef2f2 + 幻灯片预览
                    ├── BottomSection — 60px 白色区
                    │     ├── title 12px/700
                    │     ├── type·course 10px
                    │     └── time·match 9px
                    └── CardBorder — rx=10, stroke=#e2e8f0
```

### RecommendedExploration 数据流

```
Dashboard.tsx
  ├── recommended: RecommendedItem[]
  │
  └── <RecommendedExploration items={r} />
        │
        └── for each item:
              └── RecommendedCard({item})  ← NEW component
                    ├── TopSection({match_score}) — 100px 色区
                    │     ├── documents type: #eff6ff + 文档预览 + 折角 + 文字行
                    │     ├── mindmap type: #ecfdf5 + 中心圆 + 3 分支
                    │     └── MatchBadge({score%}) — 右上角 20×20 rx=6
                    ├── BottomSection — 60px
                    │     ├── title 12px/700
                    │     └── description 10px/#64748b
                    └── CardBorder — rx=10
```

### GitHubProjects 数据流

```
Dashboard.tsx
  ├── repos: GitHubRepo[]
  │
  └── <GitHubProjects repos={r} />
        │
        └── for each repo:
              └── GitHubCard({repo})  ← NEW component
                    ├── TopSection — 100px fill=#1e293b
                    │     ├── "{ }" watermark 18px monospace op=0.15
                    │     ├── LanguageBar({language, color}) — 80×4 rx=2
                    │     └── LanguageLabel({language}) — 9px monospace
                    ├── BottomSection — 60px fill=#fff
                    │     ├── repo full_name 10px monospace #6366f1
                    │     ├── description 11px/700
                    │     ├── lang·license 9px
                    │     └── stars 10px/700/amber textAnchor=end
                    └── CardBorder — rx=10
```

### LifelongGraph 数据流

```
Dashboard.tsx
  ├── graphNodes: GraphNode[], graphEdges: GraphEdge[]
  ├── courseStats: CourseStat[]  ← 增强类型
  │
  └── <LifelongGraph nodes={n} edges={e} courseStats={cs} />
        │
        ├── StatsHeader — 1248×40 rx=8 bg=#f8fafc
        │     ├── "课程数" {count}
        │     ├── divider line
        │     ├── "总节点" {totalNodes}
        │     ├── divider line
        │     ├── "已掌握" {mastered} (green)
        │     ├── "学习中" {learning} (indigo)
        │     └── "薄弱" {weak} (red)
        │
        ├── LeftPanel: D3GraphViewer — 760×350
        │     ├── Title bar: "终身学习图谱" 13px/700
        │     ├── D3 force layout with mastery coloring
        │     └── Legend: 3 items (mastered/learning/weak)
        │
        └── RightPanel: CourseStatCard[] — 每张 472×108 rx=12
              │
              └── CourseStatCard({stat})  ← NEW component
                    ├── TopColorBar: 472×4 rx=2 — index-mapped color
                    ├── Title: 13px/700 + badge (RAG/Software/etc.)
                    ├── StatsRow:
                    │     ├── "已掌握 {n}" 10px
                    │     ├── "学习中 {n}" 10px
                    │     ├── "薄弱 {n}" 10px
                    │     └── "{percent}%" 10px/700
                    ├── ProgressBar: 440×6 rx=3
                    │     ├── bg: #f1f5f9
                    │     └── fill: color, width={percent%}
                    ├── WeakNote: "薄弱: {node_titles}" 10px #94a3b8
                    └── ActionButton: "进入学习" 80×22 rx=6 #f1f5f9
              │
              └── EmptyPlaceholder (when courseStats.length < 3)
                    ├── dashed border rx=12
                    ├── "新的学科等着你探索" 14px/700 #cbd5e1
                    ├── "完成一门课程后，开始新的学习旅程" 11px #d1d5db
                    └── "浏览可用学科" button
```

## 函数级收口与内部逻辑

### Dashboard.tsx

#### `SyllabusProgress` 类型 (NEW)
```ts
interface SyllabusProgress {
  syllabus_id: number;
  total_nodes: number;
  mastered_nodes: number;
  learning_nodes: number;
  weak_nodes: number;
  weak_node_titles: string[];  // top 2 薄弱节点标题
  last_active_text: string;     // "2小时前活跃" / "昨天活跃"
  progress_percent: number;     // 0-100
}
```

#### `fetchSyllabusProgressBatch(userId: number, syllabuses: SyllabusItem[]): Promise<Record<number, SyllabusProgress>>`
- **输入**: userId + 课程列表
- **输出**: `{ [syllabus_id]: SyllabusProgress }`
- **内部逻辑**:
  1. `Promise.all(syllabuses.map(s => fetchStudyGraph(userId, s.syllabus_id)))` — 并行查询每个 syllabus 的图谱
  2. 从 `res.graph.tree.summary` 提取 `mastered_node_count`, `learned_node_count`, `weak_node_count`
  3. `total = mastered + learned + weak`
  4. `progress_percent = total > 0 ? Math.round((mastered / total) * 100) : 0`
  5. 从 `res.graph.tree.nodes` 中筛选 `mastery.label === "weak"` 的节点，取前 2 个 title 作为 `weak_node_titles`
  6. `last_active_text` 从 `summary.last_updated_at` 计算相对时间
  7. 返回 map

#### `formatRelativeTime(timestamp: number): string`
- **输入**: Unix 秒时间戳
- **输出**: "2小时前活跃" / "昨天活跃" / "3天前活跃"
- **内部逻辑**: `const diff = Date.now() - timestamp * 1000`; 按分钟/小时/天分支

#### `Dashboard(props): JSX.Element`
- **新增状态**: `syllabusProgressMap: Record<number, SyllabusProgress>`
- **新增 useEffect**: syllabus 列表加载完成后触发 `fetchSyllabusProgressBatch`
- **移除**: lines 211-219 重复的欢迎区域（`你好, {userName}` 在 SVG 不存在）
- **新增**: 两个 `<SectionDivider>` 组件（在 RecommendedExploration 和 GalaxyReveal 前）

---

### CourseCardGrid.tsx

#### `CourseCardGridProps` (MODIFIED)
```ts
interface CourseCardGridProps {
  syllabuses: SyllabusItem[];
  progressMap: Record<number, SyllabusProgress>;  // NEW
  loading?: boolean;
}
```

#### `WeekSemesterLine({ syllabus }: { syllabus: SyllabusItem }): JSX.Element | null`
- **输出**: `<text x=16 y=158 fontSize=12 fontWeight=700 fill=#0f172a>` "18 周 · 2025秋" 或 null
- **内部逻辑**: 从 syllabus 元数据中提取 week/semester 信息。**若 API 未返回则隐藏此行**（零假数据约束）
- **数据源检查**: syllabus_list API 返回的 syllabus 对象中是否有 `weeks`/`semester` 字段。若无，此行不渲染。

#### `StatusBadge({ status, isDraft }: { status?: string; isDraft: boolean }): JSX.Element`
- **输出**: 
  - 已发布: `rect 48×20 rx=5 fill=#ede9fe` + text "已发布" 9px/600/#6366f1
  - 草稿: 无独立 badge（草稿状态在 banner 副标题已显示）；状态文本 "课程准备中" 12px/700/#94a3b8 替代 badge 位置
- **对照**: SVG line 37/64

#### `ProgressBar({ percent, color }: { percent: number; color: string }): JSX.Element`
- **输出**: 
  - 底 bar: `rect w=352 h=6 rx=3 fill=#f1f5f9`
  - 填充 bar: `rect w={352 * percent/100} h=6 rx=3 fill={color}`
- **对照**: SVG lines 39, 53

#### `MasteryStats({ progress }: { progress: SyllabusProgress }): JSX.Element | null`
- **输出**: `<text fontSize=10 fill=#94a3b8>` "{n} 节点已掌握 · {k} 薄弱 · {time}"
- **内部逻辑**: 从 SyllabusProgress 提取 `mastered_nodes`, `weak_nodes`, `last_active_text`
- **对照**: SVG lines 40, 54

#### `ActionButtons({ syllabus_id, isDraft }: { syllabus_id: number; isDraft: boolean }): JSX.Element`
- **输出**:
  - 已发布: "进入学习" btn `96×26 rx=8 fill=#6366f1` + "管理" btn `52×26 rx=8 fill=#f1f5f9`
  - 草稿: "等待中" btn `96×26 rx=8 fill=#f1f5f9 stroke=#e2e8f0` (disabled)
- **对照**: SVG lines 41-42, 55-56, 65

#### `CourseCard({ syllabus, progress }: { syllabus: SyllabusItem; progress?: SyllabusProgress }): JSX.Element`
- **输出**: 完整 384×266 卡片
- **渲染层序**:
  1. 卡片底板 `rect rx=14` (draft: dashed)
  2. `<CourseThumbnail>` — banner 384×136
  3. `<WeekSemesterLine>` — 周/学期行（有数据时）
  4. `<StatusBadge>` — 状态标签
  5. `<ProgressBar>` — 进度条（有 progress 数据时）
  6. `<MasteryStats>` — 掌握统计行（有 progress 数据时）
  7. `<ActionButtons>` — 操作按钮
- **SVG 对照**: lines 30-66

---

### RecentResources.tsx

#### `ResourceCard({ resource }: { resource: ResourceSummary }): JSX.Element`
- **输出**: 单体 `296×160 rx=10` 卡片
- **渲染层序**:
  1. `<rect rx=10 fill=#fff stroke=#e2e8f0>` — 卡片底板
  2. `<TopSection type={resource.resource_type}>` — 100px 类型色区
     - `<rect rx=10 fill={typeColor}>` + `<rect y=50 h=50 fill={typeColor}>` — 上部+平底
     - 类型 SVG 图标（内联，对照 SVG lines 75-78/87-89/97-102/111-115）
  3. `<BottomSection>` — 60px 文本
     - `<rect rx=10 fill=#fff>` + `<rect y=110 h=50 fill=#fff>` — 下部+平顶
     - `title` 12px/700/#0f172a
     - `typeLabel · topic` 10px/#64748b
     - `time · match%` 9px/#94a3b8

#### `TopSectionSVG({ type }: { type: ResourceType }): JSX.Element`
- **输入**: 资源类型
- **输出**: 100px 高度内的类型 SVG 图标
- **内部逻辑**: switch 分发到 5 种内联 SVG:
  - **mindmap** (SVG lines 75-78): 中心圆 r=14 + 内点 r=4 + 上分支 + 左下分支 + 右下分支，配色 #059669
  - **quiz** (SVG lines 87-89): "?" 水印 28px/800 op=0.12 + 选项 A/B 框 96×16 rx=4
  - **ppt** (SVG lines 97-102): 幻灯片预览 116×64 rx=6 + title + 2 文字行 + 迷你图表 40×10 rx=3
  - **coding_practice** (SVG lines 111-115): 5 行 monospace 代码 9px 语法着色
  - **documents** (default): 文档预览 + 折角 SVG（与 DocThumbnail documents 模板一致）

#### `formatRelativeTime` — 复用已有实现

---

### RecommendedExploration.tsx

#### `RecommendedCard({ item }: { item: RecommendedItem }): JSX.Element`
- **输出**: `296×160 rx=10` 卡片
- **渲染层序**:
  1. 卡片底板
  2. 上部 100px — 根据 match_score 或内容类型决定色区（高匹配 document→#eff6ff，高匹配 mindmap→#ecfdf5）
  3. 类型预览 SVG（document: 折角文档 + 4 文字行，mindmap: 中心圆 + 3 分支）
  4. MatchBadge: 右上角 `20×20 rx=6`，显示 "92%" 或 "85%"
  5. 下部 60px: title + description
- **对照**: SVG lines 126-152

#### `MatchBadge({ score, color }: { score: number; color: string }): JSX.Element`
- **输出**: `<rect 20×20 rx=6 fill={color} op=0.15>` + `<text 9px/700 fill={color}>` "{score}%"
- **对照**: SVG lines 134-135, 147-148

#### `RecommendedDocPreview(): JSX.Element`
- **输出**: 文档预览 SVG — `256×72 rx=6 fill=#fff stroke=#bfdbfe` + 4 文字行 rect + 折角 polygon
- **对照**: SVG lines 128-133

#### `RecommendedMindmapPreview(): JSX.Element`
- **输出**: 思维导图预览 SVG — 中心圆 r=18 + 内点 r=5 + 上分支 + 左下分支 + 右下分支
- **对照**: SVG lines 143-146

---

### GitHubProjects.tsx

#### `GitHubCard({ repo }: { repo: GitHubRepo }): JSX.Element`
- **输出**: `296×160 rx=10` 卡片
- **渲染层序**:
  1. 卡片底板 `rx=10 fill=#fff stroke=#e2e8f0`
  2. `TopSection` — 100px fill=#1e293b
     - `{ }` 水印 text 18px monospace 700 op=0.15 textAnchor=middle
     - 语言色条 rect 80×4 rx=2（从 LANG_COLORS 查找）
     - 语言标签 text 9px monospace #94a3b8
     - 可选: 第二色条（SVG line 163，当有额外语言时）
  3. `BottomSection` — 60px fill=#fff
     - repo `full_name` 10px monospace #6366f1
     - `description` 11px/700 #0f172a
     - metadata row: `language` · `license` 9px #94a3b8
     - `stars` 10px/700 #f59e0b textAnchor=end（格式化: ≥1000 用 "N.Nk ★"）
- **对照**: SVG lines 158-193

#### `LANG_COLORS` — 复用已有映射

#### `formatStars(n: number): string`
- **输入**: star 数量
- **输出**: "5.2k ★" / "14.8k ★" / "40.1k ★"
- **内部逻辑**: `n >= 1000 ? (n/1000).toFixed(1) + "k ★"` : n + " ★"

---

### LifelongGraph.tsx

#### `CourseStat` 类型 (MODIFIED)
```ts
interface CourseStat {
  syllabus_id: number;
  subject_title: string;
  tag?: string;               // "RAG" / "Software" — from graph_names[0]
  tagColor?: string;          // badge background color
  node_count: number;
  mastered: number;
  learning: number;
  weak: number;
  weak_titles: string[];      // top 2 weak node titles
  progress_percent: number;
  color: string;              // top bar color (index-mapped)
}
```

#### `StatHeader({ stats }: { stats: CourseStat[] }): JSX.Element`
- **输出**: `1248×40 rx=8 fill=#f8fafc` 容器
- **内部**: 
  - 课程数 = stats.length
  - 总节点 = sum(node_count)
  - 已掌握 = sum(mastered)
  - 学习中 = sum(learning)
  - 薄弱 = sum(weak)
  - 各项以 `<line>` 分隔
- **对照**: SVG lines 210-219

#### `CourseStatCard({ stat, color }: { stat: CourseStat; color: string }): JSX.Element`
- **输出**: `472×108 rx=12` 卡片
- **渲染层序**:
  1. 卡片底板 `rx=12 fill=#fff stroke=#e2e8f0`
  2. 彩色顶条 `472×4 rx=2 fill={color}`
  3. 标题 `x=16 y=26 fontSize=13 fontWeight=700` + tag badge（如 "RAG"）
  4. 统计行: "已掌握 {n} 学习中 {n} 薄弱 {n} {percent}%"
  5. 进度条: `440×6 rx=3`，fill 为 color
  6. 薄弱提示: "薄弱: {titles}" 10px #94a3b8
  7. "进入学习" 按钮: `80×22 rx=6 fill=#f1f5f9`（navigate to subject home）
- **对照**: SVG lines 267-299

#### `EmptyCoursePlaceholder(): JSX.Element`
- **输出**: `472×108 rx=12` dashed 卡片
- **内部**: 居中文本 "新的学科等着你探索" + 副文本 + "浏览可用学科" 按钮
- **对照**: SVG lines 303-310

#### `COURSE_CARD_COLORS: readonly string[]`
- **定义**: `["#6366f1", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#06b6d4"]`
- **选取**: `COURSE_CARD_COLORS[index % COURSE_CARD_COLORS.length]`

#### `LifelongGraph(props): JSX.Element`
- **内部逻辑**:
  1. 从 nodes 计算 `totalNodes`, `masteredCount`, `learningCount`, `weakCount`
  2. 渲染统计 header
  3. 左侧 D3 图 + 图例
  4. 右侧课程卡片列表（最大 3 张，不足补 `EmptyCoursePlaceholder`）
- **SVG 覆盖**: lines 200-313 全量

---

### SectionDivider.tsx (NEW)

#### `SectionDivider({ text, arrows }: { text: string; arrows?: number }): JSX.Element`
- **输入**: 文本内容，箭头数量（默认 1）
- **输出**: 居中组 `<g textAnchor=middle>`
  - text 12px #94a3b8
  - 水平线 `<line>` stroke=#cbd5e1
  - N 个下箭头 `<polygon>` fill=#94a3b8
- **对照**: SVG lines 197-198 (1 arrow), lines 315-317 (2 arrows)

## Decisions

### Decision 1: Per-syllabus study_graph 查询
- **选择**: Dashboard 加载时为每个 syllabus 并行查询 `GET /api/study_graph/detail?user_id=N&syllabus_id=S`
- **代价**: N 个额外 HTTP 请求（通常 N ≤ 3）
- **理由**: 卡片需要 per-syllabus 的 mastered/weak 计数和薄弱节点标题，这些数据不在 syllabus_list 中

### Decision 2: Week/Semester 行条件渲染
- **选择**: 若 syllabus_list API 不返回 weeks/semester，则隐藏该行而非硬编码假数据
- **理由**: 零假数据约束。若后续 API 扩展此字段，自动显示

### Decision 3: RecommendedExploration 卡片类型判定
- **选择**: 从 `knowledge/search` 返回的 `matched_sources` 推断类型（document/mindmap），无法判定时默认 document 型
- **理由**: search API 返回 `matched_sources` 数组包含文件路径，可从中提取类型

### Decision 4: 单体卡片结构
- **选择**: RecentResources/RecommendedExploration/GitHubProjects 统一使用 SVG 定义的单体卡片：上部 100px 色区 + 下部 60px 文本区，在同一个 `rect rx=10` 内
- **理由**: SVG 定义如此，当前分离式布局是偏差

## Risks / Trade-offs

- **Per-syllabus API 调用**: 最坏情况 3-5 个额外请求，但可并行发出。需处理单个请求失败不阻塞其他卡片。
- **RecommendedExploration 数据源**: `knowledge/search` 返回的 `results` 不包含 `resource_type`，需从 `matched_sources` 文件路径推断。若推断失败，fallback 到 document 型。
- **进度百分比计算**: 使用 `mastered/(mastered+learning+weak)` 可能与后端业务逻辑的 progress 定义不同。若无节点数据则不显示进度条。
