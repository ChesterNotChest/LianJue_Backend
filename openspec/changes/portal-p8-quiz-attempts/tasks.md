# Tasks: Portal Phase 8 — QuizAttempts 对齐

> ⛔ 对照 `08-quiz-attempts.svg` 180 行逐元素验证。

## 1. Stats Bar（SVG lines 31-38）
- [x] 1.1 `880×48 rx=10` + 4 列 + vertical dividers
- [x] 1.2 可用测验/已完成(green)/平均得分(green)/薄弱知识点(red)

## 2. QuizCard 三栏布局（SVG lines 42-101）
- [x] 2.1 容器 `880×200 rx=12 fill=#fff stroke=#e2e8f0`
- [x] 2.2 **Left** `280×168 rx=8 fill=#fef3c7`: badge + title + desc + buttons (SVG lines 46-56)
- [x] 2.3 **Middle** 成绩摘要: Best green card `160×48` + Recent gray card `160×48` + 薄弱点 red area `344×44` (SVG lines 58-86)
- [x] 2.4 **Right** 提交历史: 3 entries `160×28 rx=6` (green/red circles) (SVG lines 89-100)

## 3. QuizCard 分数变体（SVG lines 104-149）
- [x] 3.1 中等分数 (70%): Best card amber `fill=#fef3c7 stroke=#fde68a`
- [x] 3.2 "重新测验" button text variant

## 4. UntouchedCard（SVG lines 152-169）
- [x] 4.1 `880×120 rx=12` dashed border, gray theme
- [x] 4.2 "开始测验" btn `100×28 rx=8 fill=#6366f1`

## 5. 数据加载
- [x] 5.1 `fetchResourceList(uid, sid, "quiz")` + `quiz_attempts` API merge
- [x] 5.2 Stats 聚合: total, completed, avgScore, weakCount

## 6. 构建验证
- [x] 6.1 TypeScript 编译通过
- [x] 6.2 Vite build 通过
