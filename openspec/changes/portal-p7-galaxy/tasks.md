# Tasks: Portal Phase 7 — Galaxy 验证对齐

> ⛔ 对照 `06-galaxy.svg` 逐元素验证。

## 1. 深空子窗口（SVG lines 32-35）
- [ ] 1.1 Dark frame border `1176×804 rx=14 stroke=#1e293b w=2`
- [ ] 1.2 Space gradient background #03040a→#080c1a (linearGradient id="spaceBg")

## 2. 视图切换（SVG lines 64-67）
- [ ] 2.1 "银河" active pill: `52×22 rx=11 fill=rgba(56,189,248,0.2) stroke=rgba(56,189,248,0.25)` text 9px/700/#38bdf8
- [ ] 2.2 "平面" inactive pill: `48×22 rx=11 fill=rgba(255,255,255,0.03)` text 9px/#475569

## 3. 数据源 badge（SVG line 70）
- [ ] 3.1 `240×18 rx=4 fill=rgba(0,0,0,0.3)` + info text 7px/#475569 textAnchor=middle

## 4. DetailPanel 重写（SVG lines 73-80）
- [ ] 4.1 Dark glass panel `240×320 rx=12 fill=rgba(10,16,30,0.92) stroke=rgba(56,189,248,0.08)`
- [ ] 4.2 Close button `16×16 rx=8 fill=rgba(255,255,255,0.06)` + "x"
- [ ] 4.3 DOC badge: 8px/700/#7dd3fc letterSpacing=1
- [ ] 4.4 Title: 14px/800/#f8fafc + summary: 10px/#b6c3d8
- [ ] 4.5 Info bar: `212×28 rx=6 fill=rgba(14,165,233,0.12)` + text 9px/#d7f1ff

## 5. NebulaOverlay 验证（SVG lines 55-61）
- [ ] 5.1 Glow filter: `feGaussianBlur stdDeviation=2.5`
- [ ] 5.2 Stardust nodes: r=5, mastered=#22c55e op=0.7, learning=#6366f1 op=0.7, weak=#ef4444 op=0.5
- [ ] 5.3 Connecting lines: stroke-width=0.5, opacity=0.3

## 6. Starfield + Spiral Arms 验证（SVG lines 38-44）
- [ ] 6.1 10+ stars r=0.5-1, 3 colors, op=0.3
- [ ] 6.2 2 spiral arms: blue w=46 op=0.03 + purple w=40 op=0.025
- [ ] 6.3 Center glow: 3 circles r=60/24/8 + glow filter

## 7. Knowledge clusters 验证（SVG lines 47-52）
- [ ] 7.1 RAG/Algorithm/Software/课程名 labels + circles

## 8. 构建验证
- [ ] 8.1 TypeScript 编译通过
- [ ] 8.2 Vite build 通过
