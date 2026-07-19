# Tasks: Portal Phase 1 — 缩略图系统

> ⛔ **硬性门禁**: 每个 task 必须对照 `ref-course-thumbnails.svg` 或 `ref-doc-thumbnails.svg` 的 EXACT 行号完成逐元素验证。元素缺失 = 任务未完成。

## 1. CourseThumbnail 重写（对照 ref-course-thumbnails.svg 68行全量）

- [x] 1.1 移除渐变叠加层 — 删除 `<defs>` 中的 `<linearGradient>` 和叠加 `<rect>`（SVG 不存在这些元素）
- [x] 1.2 移除 `textShadow` style 属性（SVG 无 textShadow）
- [x] 1.3 背景 rect 确认 `rx=12` + 下半部平底 rect `y=height/2 fill={bgColor}`（line 14: `rect y=60 h=60 fill=同色`）
- [x] 1.4 DecorativeCircles 验证 — 已发布: `cx=220 cy=40 r=70 op=0.06` + `cx=60 cy=90 r=100 op=0.04`（line 15）
- [x] 1.5 DraftCircle 验证 — 草稿: `cx=200 cy=40 r=70 op=0.05`（line 53）
- [x] 1.6 diagonal 几何验证 — 2 条线（line 16）: `(50,15)→(160,80)` op=0.08 + `(100,15)→(200,80)` op=0.05
- [x] 1.7 stacked 几何验证 — 3 个空心 rect（line 36）: 坐标 x=60,120,90 y=70,55,30 尺 40×40,40×40,30×40, opacity=0.1
- [x] 1.8 ripple 几何验证 — 4 个椭圆 cent=180,68, rx=40,72,104,140, ry=rx*0.42, op 0.6→0.24
- [x] 1.9 triangles 几何验证 — 4 个 polygon, fill=op0.06, stroke=op0.14
- [x] 1.10 标题 22px/800/white/ls=2（line 17）; 草稿 20px/800（line 54）
- [x] 1.11 副标题 10px/rgba(255,255,255,0.5)（line 18）; 草稿 "草稿 · 尚未发布" 10px/op0.4（line 55）
- [x] 1.12 djb2 算法验证 — `PALETTE[hash%8]` 8 色（line 65）+ `GEOMETRIES[(hash>>4)%4]` 4 几何（line 66）
- [x] 1.13 对照 ref-course-thumbnails.svg 全量 68 行逐元素验收，产出通过/未通过结论

## 2. DocThumbnail 重写（对照 ref-doc-thumbnails.svg 95行全量）

- [x] 2.1 公共结构: 白色卡片 `rx=10` + 彩色 stroke（lines 7/26/44/59/79）
- [x] 2.2 公共顶条: `150×3 rx=1.5` 按 accent 色（lines 8/27/45/60/80）
- [x] 2.3 公共底部标签: `56×16 rx=5` fill=accent op=0.1, 文本 9px/600/accent（lines 20/38/53/73/92）
- [x] 2.4 文档模板 — 内部区域 118×100 rx=4 + 折角 polygon + 6 行 rect + 分隔线（lines 9-19）
- [x] 2.5 思维导图模板 — 中心圆 r=22 + 内点 r=7 + 3 分支 + 1 子分支（lines 28-37）
- [x] 2.6 测验模板 — "?" 水印 24px + 3 选项框 114×22 rx=6, B 琥珀高亮（lines 46-52）
- [x] 2.7 代码练习模板 — 编辑器 122×90 rx=6 + tab bar 14px + 3 控制点 + 6 行代码 monospace 语法着色（lines 61-72）
- [x] 2.8 课件模板 — 幻灯片 118×72 rx=6 + 标题栏 + 文字行 + 迷你图表 50×20 + 3 导航点（lines 81-91）
- [x] 2.9 对照 ref-doc-thumbnails.svg 全量 95 行逐元素验收，产出通过/未通过结论

## 3. 构建验证

- [x] 3.1 TypeScript 编译通过（`tsc --noEmit`）
- [x] 3.2 Vite build 通过（`vite build`）
