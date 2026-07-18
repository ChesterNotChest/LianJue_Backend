# Tasks: Portal Phase 6 — LearningTree 全量对齐

> ⛔ **硬性门禁**: 每个 task 必须对照 `05-learning-tree.svg` 的 EXACT 行号完成逐元素验证。

## 1. WeaknessAnalysis 重写（对照 SVG lines 117-147）

- [ ] 1.1 卡片底板 `304×172 rx=12 fill=#fff stroke=#e2e8f0` (SVG line 118)
- [ ] 1.2 红色 header `fill=#fef2f2` + 底部平铺 + "薄弱点分析" 11px/700/#ef4444 + "N 个薄弱集群" 9px/#94a3b8 (SVG lines 119-121)
- [ ] 1.3 Weak item 1-2: `284×36 rx=6 fill=#fef2f2 stroke=#fecaca` + 红点 r=5 + title 11px/600 + desc 9px + score 8px/#ef4444 right-aligned (SVG lines 124-138)
- [ ] 1.4 Weak item 3: `284×32 rx=6 fill=#fff stroke=#f1f5f9` + amber 圆点 r=5 (SVG lines 140-146)
- [ ] 1.5 移除 amber 配色 — 全部使用 SVG 定义的红色主题
- [ ] 1.6 对照 SVG lines 117-147 逐元素验收

## 2. ExploreGapList 重写（对照 SVG lines 150-186）

- [ ] 2.1 紫色 header `fill=#ede9fe` + "差了什么 · 待探索" 11px/700/#7c3aed + "N 项小觉推荐" 9px/#94a3b8 (SVG lines 151-154)
- [ ] 2.2 纯文本行 — 每项: title 11px/600/#0f172a + "← 关联: {trunk} ✓" 9px/#94a3b8 (SVG lines 157-180)
- [ ] 2.3 移除边框卡片布局 — 使用纯文本行（SVG 无 item 卡片边框）
- [ ] 2.4 Agent 链接 `284×16 rx=4 fill=#ede9fe` + "→ 和智能体对话，走一条推荐路径" 8px/600/#7c3aed (SVG lines 182-185)
- [ ] 2.5 对照 SVG lines 150-186 逐元素验收

## 3. BuddyObservations 重写（对照 SVG lines 190-216）

- [ ] 3.1 全宽卡片 `880×120 rx=12 fill=#fff stroke=#e2e8f0` (SVG line 191)
- [ ] 3.2 Header: "学伴的观察" 13px/700/#0f172a + 副标题 10px/#94a3b8 (SVG lines 192-193)
- [ ] 3.3 "觉" 圆形头像: `circle r=6 fill=#ede9fe` + text "觉" 8px/#7c3aed textAnchor=middle (SVG line 198)
- [ ] 3.4 Obs card 1: `410×32 rx=8 fill=#fafafa stroke=#f1f5f9` (SVG lines 196-201)
- [ ] 3.5 Obs card 2: `426×32 rx=8` (SVG lines 203-208)
- [ ] 3.6 Obs card 3: `848×28 rx=8` (SVG lines 210-215)
- [ ] 3.7 内联文本格式: 引用 11px/#0f172a + 日期·mastery_hint 9px/#94a3b8 (SVG lines 199-200)
- [ ] 3.8 对照 SVG lines 190-216 逐元素验收

## 4. BuddyMemoryCloud 重写（对照 SVG lines 219-234）

- [ ] 4.1 全宽卡片 `880×76 rx=12 fill=#fff stroke=#e2e8f0` (SVG line 221)
- [ ] 4.2 Header: "学伴的记忆" 13px/700/#0f172a + 副标题 10px/#94a3b8 (SVG lines 222-223)
- [ ] 4.3 Tag pill: `rx=6 h=24` 长方形（非 rounded-full）(SVG lines 226-231)
- [ ] 4.4 Purple pills: `fill=#ede9fe` + text 10px/#7c3aed (weak_pattern)
- [ ] 4.5 Green pills: `fill=#dcfce7` + text 10px/#16a34a (strength)
- [ ] 4.6 "+N 条更早" text 10px/#94a3b8 when tags > 6 (SVG line 232)
- [ ] 4.7 对照 SVG lines 219-234 逐元素验收

## 5. BuddySuggestion 重写（对照 SVG lines 237-243）

- [ ] 5.1 Amber 卡片 `880×56 rx=12 fill=#fef3c7 stroke=#fde68a` (SVG line 238)
- [ ] 5.2 Buddy 头像: `circle r=10 fill=#6366f1` + 双眼 (r=2) + 微笑 path (SVG line 239)
- [ ] 5.3 Title: "小觉的综合建议" 12px/700/#92400e + 副标题 9px/#b45309 (SVG lines 240-241)
- [ ] 5.4 正文: synthesis text 11px/#b45309 (SVG line 242)
- [ ] 5.5 移除紫色渐变配色 — 全部使用 amber 主题
- [ ] 5.6 对照 SVG lines 237-243 逐元素验收

## 6. LearningTreePage 验证

- [ ] 6.1 Stats bar: 5 stats + "学伴视角 · 开启" badge (SVG lines 38-48)
- [ ] 6.2 Gap summary bar: `880×30 rx=8` + hint count + weak area count + 建议顺序 + "学伴视角 · 已开启" badge (SVG lines 246-250)
- [ ] 6.3 View toggles: 4 pills with exact SVG sizes and colors (SVG lines 14-17)
- [ ] 6.4 D3 Graph: overlay labels (当前步骤/薄弱集群/小觉跟随提示) (SVG lines 94-103)
- [ ] 6.5 Legend: 4 items (SVG lines 106-111)

## 7. 构建验证

- [ ] 7.1 TypeScript 编译通过（`tsc --noEmit`）
- [ ] 7.2 Vite build 通过（`vite build`）
