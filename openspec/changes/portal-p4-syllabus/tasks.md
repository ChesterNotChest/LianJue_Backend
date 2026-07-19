# Tasks: Portal Phase 4 — Syllabus 全量对齐

> ⛔ **硬性门禁**: 每个 task 必须对照 `03-syllabus.svg` 的 EXACT 行号完成逐元素验证。

## 1. ActivityPanel 重写（对照 SVG lines 73-81）

- [x] 1.1 面板底板 — `280×460 rx=12 fill=#fff stroke=#f1f5f9 filter=url(#ss)` (SVG line 73)
- [x] 1.2 标题 — "学习活跃度" 14px/700/#0f172a + "过去 7 天" 10px/#94a3b8 (SVG lines 74-75)
- [x] 1.3 7 天柱状图 — 7 bars, 26px wide, height 6-50px range (SVG line 76)
  - [x] 1.3a 今天: indigo (#6366f1) op=0.7
  - [x] 1.3b 活跃天: green (#22c55e) op 0.4-0.7 proportional
  - [x] 1.3c 无数据天: gray (#f1f5f9)
  - [x] 1.3d 星期标签 (日/一/二/三/四/五/六) 10px
- [x] 1.4 统计行 1 — "7 天活跃天数" → "{n} 天" (SVG line 77-78)
- [x] 1.5 统计行 2 — "日均学习时长" → "{n} 分钟" (SVG line 78)
- [x] 1.6 统计行 3 — "30 天活跃天数" → "{n} 天" (SVG line 79)
- [x] 1.7 统计行 4 — "总学习时长" → "{n} 小时" (SVG line 80)
- [x] 1.8 每行规格 — `248×42 rx=8 fill=#f8fafc`, label 12px/#64748b + value 15px/800/#0f172a 右对齐
- [x] 1.9 对照 SVG lines 73-81 逐元素验收

## 2. SyllabusTimeline 验证（对照 SVG lines 43-69）

- [x] 2.1 纵向线 — stroke=#e2e8f0 w=2 (SVG line 43)
- [x] 2.2 已掌握圆 — r=12 fill=#22c55e border=3px white + 白色对勾 (SVG lines 44, 48)
- [x] 2.3 当前圆 — r=16 fill=#6366f1 + 内点 r=6 fill=white op=0.6 (SVG line 52)
- [x] 2.4 待开始圆 — r=12 fill=#fff stroke=#cbd5e1 w=2 (SVG lines 56, 60, 66)
- [x] 2.5 周卡片 — rx=8 + 左侧 4px 色条 + title 13px/700 + desc 11px + 状态标签 (SVG lines 45-68)
- [x] 2.6 折叠点 — 3 circles r=5 fill=#e2e8f0 + "..." (SVG line 64)
- [x] 2.7 对照 SVG lines 43-69 逐元素验收

## 3. StatsBar 验证（对照 SVG lines 35-41）

- [x] 3.1 容器 — `840×48 rx=10 fill=#fff stroke=#f1f5f9` (SVG line 35)
- [x] 3.2 完成列 — "完成" 9px/#94a3b8 + green count 16px/800 (SVG line 36)
- [x] 3.3 当前列 — "当前" 9px/#94a3b8 + "第 N 周" 16px/800/#6366f1 (SVG line 38)
- [x] 3.4 进度列 — green gradient bar 200×8 rx=4 + "{n}%" (SVG line 40)
- [x] 3.5 对照 SVG lines 35-41 逐元素验收

## 4. 构建验证

- [x] 4.1 TypeScript 编译通过（`tsc --noEmit`）
- [x] 4.2 Vite build 通过（`vite build`）
