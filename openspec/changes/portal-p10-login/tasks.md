# Tasks: Portal Phase 10 — Login 对齐

> ⛔ 对照 `00-login.svg` 73 行逐元素验证。

## 1. Page Layout（SVG lines 1-16）
- [x] 1.1 背景 `fill=#f8fafc`
- [x] 1.2 顶条 accent `1440×4 fill=url(#topBar)`
- [x] 1.3 品牌区: "联觉 LianJue" 32px/800/#0f172a ls=2 + 副标题

## 2. Login Card（SVG lines 18-42）
- [x] 2.1 `400×260 rx=16 fill=#fff` + "登录" title
- [x] 2.2 用户名输入 `336×46 rx=10`
- [x] 2.3 密码输入 `336×46 rx=10`
- [x] 2.4 登录按钮 `336×46 rx=10 fill=#6366f1`

## 3. Quick-fill + Seeded（SVG lines 44-72）
- [x] 3.1 ~~3 demo user buttons + password hint~~ **已移除** — 用户要求去掉 demo 学生，只留干净的登录
- [x] 3.2 ~~Seeded user cards (green 160×50 rx=8)~~ **已移除** — 用户要求去掉 demo 学生，只留干净的登录
- [x] 3.3 Footer text

## 4. 构建验证
- [x] 4.1 TypeScript 编译通过（LoginPage.tsx 无新增错误，已存错误均为其他文件）
- [x] 4.2 Vite build 通过
