# Tasks: Portal Phase 2 — Dashboard 全量对齐

> ⛔ **硬性门禁**: 每个 task 必须对照 `01-dashboard.svg` 的 EXACT 行号完成逐元素验证。元素缺失 = 任务未完成。

## 1. Dashboard.tsx 修正（对照 01-dashboard.svg lines 1-332）

- [ ] 1.1 移除重复欢迎区域 — 删除 Dashboard.tsx lines 211-219 的 "你好, {userName}" welcome section（SVG 中不存在该元素，用户信息在 Header 中已显示，lines 16-17）
- [ ] 1.2 新增 `SectionDivider` 组件导入并在 RecommendedExploration 和 GalaxyReveal 前渲染（SVG lines 197-198, 315-317）
- [ ] 1.3 新增 `fetchSyllabusProgressBatch` 函数 — 对每个 syllabus 并行调用 `GET /api/study_graph/detail?user_id=N&syllabus_id=S`，构建 `Record<number, SyllabusProgress>`（design.md 定义的接口）
- [ ] 1.4 新增 `syllabusProgressMap` state + useEffect 在 syllabus 加载后触发 progress 查询
- [ ] 1.5 `SyllabusProgress` 接口定义 — 含 `total_nodes, mastered_nodes, learning_nodes, weak_nodes, weak_node_titles, last_active_text, progress_percent`
- [ ] 1.6 对照 01-dashboard.svg 全量 332 行逐元素验收

## 2. CourseCardGrid 重写（对照 SVG lines 28-67）

- [ ] 2.1 Props 扩展 — 新增 `progressMap: Record<number, SyllabusProgress>`
- [ ] 2.2 `WeekSemesterLine` 组件 — SVG line 36: "18 周 · 2025秋" 12px/700/#0f172a（若 API 无数据则不渲染，零假数据）
- [ ] 2.3 `StatusBadge` 组件 — SVG line 37: `48×20 rx=5 fill=#ede9fe` + "已发布" 9px/600/#6366f1；draft 时 SVG line 64: "课程准备中" 12px/700/#94a3b8
- [ ] 2.4 `ProgressBar` 组件 — SVG lines 38-39, 52-53: 底 bar `352×6 rx=3 fill=#f1f5f9` + 填充 bar 比例宽度，green≥60%, amber<60%
- [ ] 2.5 `MasteryStats` 组件 — SVG lines 40, 54: "{mastered} 节点已掌握 · {weak} 薄弱 · {time}" 10px/#94a3b8
- [ ] 2.6 `ActionButtons` 组件 — SVG lines 41-42, 55-56, 65: "进入学习" 96×26 rx=8 #6366f1 + "管理" 52×26 rx=8 #f1f5f9；draft "等待中" 96×26 disabled
- [ ] 2.7 卡片容器 — SVG line 30/45/60: `384×266 rx=14`，published white solid border，draft dashed border
- [ ] 2.8 组装 `CourseCard` — 完整渲染层序: 底板 → CourseThumbnail → WeekSemesterLine → StatusBadge → ProgressBar → MasteryStats → ActionButtons
- [ ] 2.9 对照 SVG lines 28-67（3 张卡片: published diagonal + published stacked + draft）逐元素验收

## 3. RecentResources 重写（对照 SVG lines 70-121）

- [ ] 3.1 标题行 — SVG lines 70-71: "最近资源" 16px/700 + "跨课程最近生成的学习材料" 12px/#94a3b8 + 刷新按钮 60×24 rx=6
- [ ] 3.2 `ResourceCard` 单体卡片结构 — SVG lines 73, 85, 96, 109: `296×160 rx=10 fill=#fff stroke=#e2e8f0`
- [ ] 3.3 上部 TopSection `100px` 色区 — SVG lines 74, 86, 97, 110: 类型色彩 + 底部平铺 rect
- [ ] 3.4 Mindmap SVG 图标 — SVG lines 75-78: 中心圆 r=14 + 内点 r=4 + 上分支 + 左下分支 + 右下分支，#059669
- [ ] 3.5 Quiz SVG 图标 — SVG lines 87-89: "?" 水印 28px/800 op=0.12 + 选项 A/B 框 96×16 rx=4，B #fef3c7/#d97706
- [ ] 3.6 PPT SVG 图标 — SVG lines 97-102: 幻灯片 116×64 rx=6 + title 12px/700 + 2 文字行 + 迷你图表 40×10 rx=3
- [ ] 3.7 Coding SVG 图标 — SVG lines 111-115: 5 行 monospace 代码 9px 语法着色 (def/solve/(n:int)/if/n<=1)
- [ ] 3.8 下部 BottomSection `60px` 文本 — SVG lines 80-82, 91-93, 104-106, 117-119: title 12px/700 + type·course 10px + time·match 9px
- [ ] 3.9 对照 SVG lines 70-121（4 张卡片: mindmap + quiz + ppt + coding）逐元素验收

## 4. RecommendedExploration 重写（对照 SVG lines 124-153）

- [ ] 4.1 标题行 — SVG line 124: "推荐探索" 16px/700 + "基于薄弱点 · knowledge/search · 匹配度排序" 12px/#94a3b8
- [ ] 4.2 `RecommendedCard` 单体卡片 — SVG lines 126, 141: `296×160 rx=10`
- [ ] 4.3 Document 预览 — SVG lines 128-133: 文档区 `256×72 rx=6 fill=#fff stroke=#bfdbfe` + 4 文字行 rect (w=60/80/50/70) + 折角 polygon
- [ ] 4.4 Mindmap 预览 — SVG lines 143-146: 中心圆 r=18 + 内点 r=5 + 3 分支 lines + endpoint circles
- [ ] 4.5 `MatchBadge` — SVG lines 134-135, 147-148: `20×20 rx=6`，document #3b82f6，mindmap #059669，text 9px/700
- [ ] 4.6 下部文本 — SVG lines 137-138, 150-151: title 12px/700 + description 10px/#64748b（含推荐理由）
- [ ] 4.7 类型判定 — 从 `knowledge/search` 的 `matched_sources` 推断 content type，无法判定默认 document 型
- [ ] 4.8 对照 SVG lines 124-153（2 张卡片: document + mindmap）逐元素验收

## 5. GitHubProjects 重写（对照 SVG lines 156-194）

- [ ] 5.1 标题行 — SVG lines 156-157: "实训项目" 16px/700 + "GitHub 开源项目 · 按相关度与 Star 数检索" 12px + 刷新按钮
- [ ] 5.2 `GitHubCard` 单体卡片 — SVG lines 159, 171, 183: `296×160 rx=10`
- [ ] 5.3 上部 TopSection `100px #1e293b` — SVG lines 160, 172, 184: dark background + 底部平铺
- [ ] 5.4 `{ }` 水印 — SVG line 161: 18px monospace 700 #f8fafc op=0.15 textAnchor=middle
- [ ] 5.5 语言色条 — SVG lines 162, 174, 186: `80×4 rx=2`，颜色从 LANG_COLORS 查找
- [ ] 5.6 语言标签 — SVG lines 162, 174, 186: 9px monospace #94a3b8
- [ ] 5.7 下部 BottomSection `60px` — SVG lines 165-168: repo name 10px monospace #6366f1 + description 11px/700 + lang·license 9px + stars 10px/700/amber
- [ ] 5.8 `formatStars` 函数 — ≥1000 用 "N.Nk ★"，否则 "{n} ★"
- [ ] 5.9 对照 SVG lines 156-194（3 张卡片: Java/Java/Scala）逐元素验收

## 6. LifelongGraph 重写（对照 SVG lines 200-313）

- [ ] 6.1 Section 标题 — SVG lines 203-204: "终身学习图谱" 16px/700 + 副标题 12px/#94a3b8
- [ ] 6.2 `StatsHeader` 组件 — SVG lines 210-219: `1248×40 rx=8 fill=#f8fafc`，5 指标 + dividers
- [ ] 6.3 统计计算 — 从 nodes 聚合 `课程数, 总节点, 已掌握, 学习中, 薄弱`
- [ ] 6.4 左侧 D3 图标题栏 — SVG lines 224-226: `760×36 rx=14 fill=#fafafa` + "终身学习图谱" 13px/700
- [ ] 6.5 D3 图例 — SVG lines 256-259: 3 项 legend (已掌握绿/学习中紫/薄弱红虚线)
- [ ] 6.6 `CourseStatCard` 组件 — SVG lines 267-299: `472×108 rx=12`
- [ ] 6.7 彩色顶条 — SVG lines 268, 286: `472×4 rx=2`，index-mapped color from COURSE_CARD_COLORS
- [ ] 6.8 标题 + tag badge — SVG lines 269-270, 287-288: title 13px/700 + badge (RAG/Software) 可变宽度 rx=4
- [ ] 6.9 统计行 — SVG lines 272-275, 290-294: "已掌握 {n} 学习中 {n} 薄弱 {n} {percent}%"
- [ ] 6.10 进度条 — SVG lines 278, 296: `440×6 rx=3`，bg #f1f5f9，fill 比例
- [ ] 6.11 薄弱提示 — SVG lines 280, 298: "薄弱: {titles}" 10px/#94a3b8
- [ ] 6.12 "进入学习" 按钮 — SVG lines 281, 299: `80×22 rx=6 fill=#f1f5f9` + text 9px/#6366f1
- [ ] 6.13 `EmptyCoursePlaceholder` — SVG lines 303-310: dashed border，居中文本，"浏览可用学科" 按钮
- [ ] 6.14 `COURSE_CARD_COLORS` —— `["#6366f1", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#06b6d4"]`
- [ ] 6.15 对照 SVG lines 200-313（StatsHeader + D3 图 + 3 张课程卡片）逐元素验收

## 7. SectionDivider 新建（对照 SVG lines 197-198, 315-317）

- [ ] 7.1 `SectionDivider` 组件 — text 12px/#94a3b8 textAnchor=middle + 水平线 stroke=#cbd5e1 + 下箭头 polygon fill=#94a3b8
- [ ] 7.2 第一个 divider: "向下滚动探索更多" + 1 arrow（SVG lines 197-198）
- [ ] 7.3 第二个 divider: "向下滚动探索知识全景" + 2 arrows（SVG lines 315-317）
- [ ] 7.4 对照 SVG lines 197-198 和 315-317 逐元素验收

## 8. GalaxyReveal 验证（对照 SVG lines 319-331）

- [ ] 8.1 渐变背景 — SVG line 320: `url(#spaceR)` 4-stop gradient #f8fafc→#e2e8f0→#334155→#03040a
- [ ] 8.2 星星 — SVG line 321: 50 seeded stars, 3 色 (warm/cool/mid)
- [ ] 8.3 星云路径 — SVG lines 322-323: path #38bdf8 w=50 op=0.03 + path #a78bfa w=44 op=0.025
- [ ] 8.4 中心光晕 — SVG line 324: 3 circles r=60/26/8
- [ ] 8.5 知识标签 — SVG lines 325-328: RAG/Algorithm/Software 节点 r=14 + text
- [ ] 8.6 "知识全景" — SVG line 330: 18px/800 letterSpacing=3 rgba(248,250,252,0.4)
- [ ] 8.7 CTA — SVG line 331: "进入全屏知识总览" 13px rgba(129,140,248,0.6)
- [ ] 8.8 对照 SVG lines 319-331 逐元素验收

## 9. 构建验证

- [ ] 9.1 TypeScript 编译通过（`tsc --noEmit`）
- [ ] 9.2 Vite build 通过（`vite build`）
