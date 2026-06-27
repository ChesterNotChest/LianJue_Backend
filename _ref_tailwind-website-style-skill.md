# _ref_tailwind-website-style-skill

> 来源: https://github.com/Lisvu/tailwind-website-style-skill (本地 clone: Lianjue_Frontend/_ref_tailwind-website-style-skill)
> 获取日期: 2026-06-27
> 用途: 管理员页面 & 用户页面前端设计规范参考

---

## 源文件清单

| 文件 | 角色 |
|---|---|
| `SKILL.md` (194行) | 设计系统规格说明书 |
| `examples/style.css` (60行) | **权威 CSS** — 星空背景 + 折叠卡片 + 关键帧 |
| `examples/example-page.jsx` (48行) | React 组件范例 "Cosmic Dashboard" |
| `README.md` (37行) | 简要介绍 + 截图 |
| `assets/home.png` | 首页预览截图 |

> **优先级规则**: 当 SKILL.md 中的代码片段与 `examples/style.css` 冲突时，**以 `style.css` 为准**。

---

## 概述

**名称**: "tailwind-website-style" — 星空风格暗色未来主义设计系统。

**触发条件**: 用户请求"使用这个网站风格"、暗色未来主义 UI、登录页/落地页/个人主页/后台管理页面。

---

## 视觉风格

- 纯黑背景 + 大量不规则漂移的白色动画星星
- 内容直接浮在星空之上（无毛玻璃/大面积半透明面板）
- 白色文字 + 浅蓝色高亮（`text-sky-200`, `text-cyan-100`）
- 控件：细白边框、黑色填充、圆角药丸形（`rounded-full`）
- 美学：未来主义、安静、宇宙感、极简

---

## 色彩系统

| 用途 | Tailwind Class |
|---|---|
| 背景 | `bg-black`, `bg-[#05030f]` |
| 正文 | `text-white` / `text-white/70` / `text-white/75` |
| 主强调色 | `text-sky-200`, `text-cyan-100` |
| 主按钮填充 | `bg-cyan-300` + `text-zinc-950` |
| 边框 | `border-white` / `border-white/30` / `border-white/15` |
| 危险色 | `text-rose-100`, `bg-rose-300/10`, `border-rose-300/40` |

**禁止**: 大面积渐变、毛玻璃面板、重阴影、亮色多色调色板。

---

## 排版

- **字体栈**: `Arial, "Microsoft YaHei", sans-serif`
- **Hero 标题**: `text-5xl sm:text-6xl lg:text-7xl font-black leading-none tracking-tight`
- **页面标题**: `text-2xl font-black tracking-tight text-sky-200`
- **卡片标题**: `text-4xl font-black leading-none`
- **正文**: `text-white/70 font-semibold leading-8`

---

## 布局规范

- **外壳 (.app-shell)**: `relative min-h-screen overflow-hidden bg-[#05030f] px-4 py-5 text-white sm:px-6`
- **星空层 (.space-background)**: `pointer-events-none fixed inset-0 bg-black` — 自闭合空元素 `<div className="space-background" />`
- **内容**: `<section className="relative z-10 mx-auto max-w-7xl">` — 导航也在其中
- **双页体验**: 横向滑动轨道 + 对角线手势触发页面切换
    - Viewport: `h-[calc(100vh-112px)] overflow-hidden touch-none`
    - Track: `flex transition-transform duration-700 ease-out`
    - Page: `h-[calc(100vh-112px)] min-w-full overflow-hidden`
- **桌面 Hero 网格**: `grid gap-8 px-5 py-10 md:grid-cols-[1fr_360px]`
- **移动端**: 堆叠布局

---

## 星空背景 CSS（权威版本，来自 style.css）

**共 7 层 radial-gradient + 1 个 `#000` 底色**，星点尺寸 0.45px–1.2px，各层 `background-size` 从 149px 到 457px 不等：

```css
.space-background {
  @apply pointer-events-none fixed inset-0 bg-black;
  background:
    /* 亮星层 (0.7-1.2px) */
    radial-gradient(circle at 13% 24%, rgba(255, 255, 255, 0.9) 0 1px, transparent 1.7px),
    radial-gradient(circle at 61% 78%, rgba(255, 255, 255, 0.75) 0 0.8px, transparent 1.5px),
    radial-gradient(circle at 84% 37%, rgba(255, 255, 255, 0.68) 0 1.2px, transparent 2px),
    radial-gradient(circle at 28% 66%, rgba(255, 255, 255, 0.82) 0 0.7px, transparent 1.4px),
    radial-gradient(circle at 45% 12%, rgba(255, 255, 255, 0.72) 0 0.8px, transparent 1.4px),
    /* 暗星层 (0.45-0.5px) */
    radial-gradient(circle at 31% 43%, rgba(255, 255, 255, 0.55) 0 0.45px, transparent 0.9px),
    radial-gradient(circle at 69% 9%, rgba(255, 255, 255, 0.58) 0 0.5px, transparent 0.95px),
    #000;
  background-size: 263px 241px, 331px 293px, 397px 347px, 457px 389px, 311px 277px, 149px 131px, 167px 139px, auto;
  animation: movingStarsNear 48s ease-in-out infinite alternate;
}
```

关键帧（8 组坐标 — 7 层星星 + 1 auto）：

```css
@keyframes movingStarsNear {
  0% { background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0 0, 0 0, 0 0; }
  33% { background-position: 20px -10px, -18px 12px, 14px 8px, -10px -14px, -12px 9px, 7px 12px, -9px 6px, 0 0; }
  66% { background-position: -12px 22px, 24px -16px, -18px 10px, 16px -8px, 15px 18px, 10px -7px, -8px -11px, 0 0; }
  100% { background-position: 18px 14px, -26px -20px, 20px -12px, -22px 16px, -18px -10px, -6px 9px, 12px -4px, 0 0; }
}
```

**关键约束**: 不规则漂移、多方向偏移、48s 周期、禁止垂直单向移动、禁止网格状排列。

---

## 组件规范

### 导航栏 (Navigation)

- 纯文字为主，无 logo（除非明确要求）
- 使用 `<nav>` 语义标签，在 `<section className="relative z-10">` 内部
- 标题: `text-2xl font-black tracking-tight text-sky-200`
- 按钮: 药丸形，`ml-auto` 推到右侧

完整模式（来自 `example-page.jsx`）：

```jsx
<nav className="flex flex-wrap items-center gap-4 px-5 py-4">
  <h1 className="text-2xl font-black tracking-tight text-sky-200">页面标题</h1>
  <div className="ml-auto flex gap-2">
    <button className="rounded-full bg-white px-4 py-2 text-sm font-black text-zinc-950">当前页</button>
    <button className="rounded-full px-4 py-2 text-sm font-black text-white/60 hover:text-white">其他页</button>
  </div>
</nav>
```

### 按钮 (Buttons)

- **Primary**: `rounded-full bg-cyan-300 px-4 py-2 font-black text-zinc-950 transition hover:-translate-y-0.5`
- **Secondary**: `rounded-full border border-white bg-black px-4 py-2 font-black text-white transition hover:bg-white hover:text-zinc-950`

### 输入框 (Inputs)

- `w-full rounded-2xl border border-white bg-black px-3 py-3 font-bold text-white outline-none placeholder:text-white/30 focus:border-cyan-200`

### 折叠悬停卡片 (Folded Hover Cards)

**精确数值（来自 style.css，与 SKILL.md 代码片段有差异时以此为准）**：

| 状态 | min-height | 位置 |
|---|---|---|
| 收起 (默认) | `112px` | 叠加 + 旋转偏移 |
| 展开 (hover) | `220px` | 子卡片分离平移 |

```css
.card-stack { @apply relative flex min-h-[360px] flex-col; perspective: 1200px; }
.stack-card { @apply absolute left-0 right-0 overflow-hidden rounded-[28px] border border-white bg-black px-5 py-4 text-white transition-all duration-500 ease-out; min-height: 112px; }

/* 收起: 叠加旋转 */
.stack-card:nth-child(1) { top: 0; transform: rotate(-2deg); z-index: 4; }
.stack-card:nth-child(2) { top: 26px; transform: rotate(1.5deg) scale(0.985); z-index: 3; }
.stack-card:nth-child(3) { top: 52px; transform: rotate(-1deg) scale(0.97); z-index: 2; }
.stack-card:nth-child(4) { top: 78px; transform: rotate(1deg) scale(0.955); z-index: 1; }

/* 展开: 边框变色 + 分离 */
.card-stack:hover .stack-card { @apply border-cyan-200; min-height: 220px; }
.card-stack:hover .stack-card:nth-child(2) { transform: translateY(140px) rotate(1deg); }
.card-stack:hover .stack-card:nth-child(3) { transform: translateY(280px) rotate(-1deg); }
.card-stack:hover .stack-card:nth-child(4) { transform: translateY(420px) rotate(1.5deg); }

/* 隐藏详情揭示 */
.card-details { @apply mt-5 max-h-0 overflow-hidden text-sm font-bold leading-7 text-white/75 opacity-0 transition-all duration-500; }
.card-stack:hover .card-details { @apply max-h-40 opacity-100; }
```

**卡片模板（来自 example-page.jsx）**：

```jsx
<article className="stack-card" key={card}>
  <div className="mb-5 flex justify-between text-[10px] font-black uppercase tracking-[0.24em] text-white/50">
    <span>{String(index + 1).padStart(2, '0')}</span>
  </div>
  <h3 className="text-4xl font-black leading-none">{card}</h3>
  <div className="card-details">
    <p>Hidden details appear when the stack is hovered.</p>
  </div>
</article>
```

### 表格/管理面板 (Tables/Admin)

- 黑色背景，白色边框
- 表头: `font-black text-cyan-100`
- 内部滚动区（不滚整页）: `max-h-[calc(100vh-330px)] w-full overflow-auto`
- 行悬停: `hover:bg-white/5`

---

## 动效规则

- 星空漂移: 40-90s 周期
- 页面切换: 横向滑动 (`duration-700 ease-out`)
- 按钮: `hover:-translate-y-0.5`
- 卡片: `hover:-translate-y-1`
- **禁止**: 弹跳动画、大幅视差跳跃、垂直浮动

---

## 响应式

- `max-w-7xl` + `px-4 sm:px-6`
- 桌面: `md:grid-cols-[1fr_360px]`
- 移动端: 堆叠布局
- 高内容区独立滚动容器

---

## 代码要求

- Tailwind CSS（复杂样式用 `@apply` 写入独立 CSS 文件）
- React 语义化组件（`<nav>`, `<article>`, `<aside>`, `<section>`）
- `import './style.css'` 分离样式
- 星空层用自闭合 `<div className="space-background" />`
- 导航在 `<section className="relative z-10">` 内容区内
- 不复制第三方品牌/商标/版权内容

---

## 完整范例：Cosmic Dashboard 组件树

```
<main className="app-shell">
  <div className="space-background" />                          ← 自闭合星空层
  <section className="relative z-10 mx-auto max-w-7xl">        ← 所有内容在此
    <nav className="flex flex-wrap items-center gap-4 ...">     ← 导航在 section 内
      <h1>标题</h1>
      <button>操作</button>
    </nav>
    <div className="grid gap-8 px-5 py-10 md:grid-cols-[1fr_360px]">
      <div>                                                     ← 左栏: hero 文本
        <h2>Hero 标题</h2>
        <p>正文描述</p>
      </div>
      <aside className="card-stack">                            ← 右栏: 卡片堆叠
        <article className="stack-card">                        ← 每张卡 <article>
          <div>索引号</div>
          <h3>卡片标题</h3>
          <div className="card-details">隐藏详情</div>
        </article>
      </aside>
    </div>
  </section>
</main>
```
