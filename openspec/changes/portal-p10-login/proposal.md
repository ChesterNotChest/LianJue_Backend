## Why

`00-login.svg`（73 行）是登录页面的权威视觉规范。当前 LoginPage 需对照 SVG 验证。

### 关键 SVG 元素

| 区域 | SVG 行 | 属性 |
|------|--------|------|
| 顶条 accent | 10 | `1440×4 fill=url(#topBar)` #4f46e5→#6366f1 |
| 品牌区 | 13-16 | "联觉 LianJue" 32px/800/#0f172a ls=2 + 副标题 14px/#64748b |
| 登录卡片 | 19-42 | `400×260 rx=16 fill=#fff stroke=#e2e8f0` + 标题 "登录" 18px/700 |
| 用户名输入 | 26-29 | `336×46 rx=10 fill=#f8fafc stroke=#e2e8f0` + placeholder "用户名" |
| 密码输入 | 32-35 | `336×46 rx=10 fill=#f8fafc stroke=#e2e8f0` + placeholder "密码" |
| 登录按钮 | 38-41 | `336×46 rx=10 fill=#6366f1` + "登 录" 14px/700/white |
| Quick-fill | 45-54 | 3 demo user buttons `120×34 rx=8` + password hint |
| Seeded users | 58-68 | 2 green cards `160×50 rx=8 fill=#dcfce7` showing seeded demo users |

## What Changes

- **修改**: `src/pages/LoginPage.tsx` — 对照 SVG lines 1-73 逐元素验证
