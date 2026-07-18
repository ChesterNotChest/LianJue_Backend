# Tasks: Portal Phase 5 — Agent 全量对齐

> ⛔ 对照 `04-agent.svg` 222 行逐元素验证。

## 1. Stats Bar 新增（SVG lines 31-39）
- [ ] 1.1 容器 `820×44 rx=10 fill=#fff stroke=#f1f5f9`
- [ ] 1.2 4 列: 综合掌握度 68% green / 7天活跃 5天 / 薄弱点 4 red / 当前步骤 purple
- [ ] 1.3 列间 `line` dividers stroke=#f1f5f9

## 2. RightSidebar 重写（SVG lines 104-137）
- [ ] 2.1 LearningPlan `296×210 rx=10` — 纵向时间线，绿/紫/灰步骤圆
- [ ] 2.2 Profile `296×172 rx=10` — 雷达图 + 能力 bar + 薄弱点 + 学习风格
- [ ] 2.3 KnowledgeBase `296×42 rx=10` — "知识库搜索" + "展开"

## 3. BuddyFloatWindow 重写（SVG lines 141-197）
- [ ] 3.1 `340×420 rx=14` 紫色头部 + 表情 + 标题 + badge + 控制按钮
- [ ] 3.2 主动提醒消息(amber #fef3c7) + 用户消息(indigo op=0.1) + 小觉回复(gray)
- [ ] 3.3 Memory tag — `316×22 rx=6 fill=#ede9fe stroke=#c4b5fd`
- [ ] 3.4 输入栏 `316×38 rx=10` + 发送按钮

## 4. BuddyPopupBubble 重写（SVG lines 200-212）
- [ ] 4.1 `280×72 rx=12` + 指向三角 polygon
- [ ] 4.2 表情头像 + "小觉" + "现在 · 自动弹出" + 消息文本 + 关闭按钮

## 5. Inline Recommendation Card 验证（SVG lines 62-93）
- [ ] 5.1 紫色头部 + Mini D3 inline (5 nodes with color-coded mastery)
- [ ] 5.2 3 candidate paths + "确认路径 A" 按钮 + "查看全屏图谱" 按钮

## 6. 构建验证
- [ ] 6.1 TypeScript 编译通过
- [ ] 6.2 Vite build 通过
