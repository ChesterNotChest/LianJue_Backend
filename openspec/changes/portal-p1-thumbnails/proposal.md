## Why

`ref-course-thumbnails.svg` 和 `ref-doc-thumbnails.svg` 是 13 个页面中所有课程卡片横幅和资源缩略图的权威视觉规范。当前 `CourseThumbnail.tsx` 和 `DocThumbnail.tsx` 与 SVG 存在元素级偏差——元素缺失（装饰圆、底部标签）、不该存在的元素（渐变叠加层、textShadow）、坐标错位（几何图案位置与 SVG 不对应）。修复这两个组件是后续页面 SVG 对齐的阻塞性前提。

## What Changes

**`CourseThumbnail.tsx`** — 逐元素对齐 `ref-course-thumbnails.svg`（lines 7-67）:

- **背景层**: 移除 `<defs>` 渐变叠加 `<rect>`（SVG 不存在该元素）。保留纯色 `<rect rx=12 fill={bgColor}>` + 下半部平底 `<rect y=height/2 fill={bgColor}>`（line 14: `rect y=60 h=60 fill=#4f46e5`）。
- **装饰圆**: 已发布卡片 2 个（line 15: `circle r=70 fill=rgba(255,255,255,0.06)` + `circle r=100 fill=rgba(255,255,255,0.04)`），草稿卡片 1 个（line 53: `circle r=70 fill=rgba(255,255,255,0.05)`）。
- **斜线几何（diagonal）**: 2 条线（line 16）—— `line (50,15)→(160,80)` stroke=rgba(255,255,255,0.08) w=2 + `line (100,15)→(200,80)` stroke=rgba(255,255,255,0.05) w=2。
- **矩形几何（stacked）**: 3 个空心矩形（line 36）—— `rect x=60,y=70 40×40` + `rect x=120,y=55 40×40` + `rect x=90,y=30 30×40`，均 rx=4，stroke=#fff w=3，opacity=0.1。
- **波纹几何（ripple）**: 4 个同心椭圆（SVG 未独立展示但算法参数列出），stroke=rgba(255,255,255,0.12)，opacity 0.6→0.24。
- **三角几何（triangles）**: 4 个重叠多边形（SVG 未独立展示但算法参数列出），fill=rgba(255,255,255,0.06)，stroke=rgba(255,255,255,0.14)。
- **标题文本**: 已发布 22px/800/white/letter-spacing=2（line 17），草稿 20px/800/white（line 54）。无 textShadow。
- **副标题文本**: 已发布 10px/rgba(255,255,255,0.5)（line 18），草稿 10px/rgba(255,255,255,0.4)（line 55，"草稿 · 尚未发布"）。
- **算法参数**: PALETTE[hash%8]（line 65 列举 8 色）、GEOMETRY[(hash>>4)%4]（line 66 列举 4 种几何）。

**`DocThumbnail.tsx`** — 逐元素对齐 `ref-doc-thumbnails.svg`（lines 1-95）:

- **公共结构**: 每个类型卡片 150×166 rx=10（lines 7, 26, 44, 59, 79），白色 fill `#fff`，彩色 stroke 边框。
- **公共顶条**: 150×3 rx=1.5（lines 8, 27, 45, 60, 80），按类型 accent 色填充。
- **公共底部标签**: 56×16 rx=5（lines 20, 38, 53, 73, 92），`fill={accent} opacity=0.1`，居中文本 9px/600/{accent}。
- **文档（documents）**: 内部文档区 118×100 rx=4 fill=#eff6ff stroke=#bfdbfe（line 9）。右上折角 polygon（line 10）+ 两条折角边缘线（line 11-12）。6 行文字 rect（lines 13-18，宽度 60/80/50/70/40/65，前 2 行有颜色 #93c5fd/无颜色 #bfdbfe）。分隔线 line（line 19，#eff6ff）。标签文本 "文档"（line 21）。
- **思维导图（mindmap）**: 中心圆 r=22 fill=#ecfdf5 stroke=#059669 w=2（line 28）+ 内点 r=7 fill=#059669 op=0.5（line 29）。上方分支 line (75,38→75,18) op=0.4 + circle r=10 op=0.6（lines 30-31）。左下分支 line (75,82→38,106) op=0.35 + circle r=8 op=0.5 + 子分支 line (34,110→14,130) op=0.2 + circle r=6 op=0.35（lines 32-37）。右下分支 line (75,82→112,106) op=0.35 + circle r=8 op=0.5（lines 34-35）。标签文本 "思维导图"（line 39）。
- **测验（quiz）**: "?" 水印 24px/800 fill=#d97706 op=0.15（line 46）。3 个选项框 114×22 rx=6——A fill=#f8fafc stroke=#e2e8f0（line 47）、B fill=#fffbeb stroke=#d97706 正确高亮（line 49）、C fill=#f8fafc stroke=#e2e8f0（line 51）。每个选项内有 9px 文本（lines 48, 50, 52）。标签文本 "测验"（line 54）。
- **代码练习（coding_practice）**: 编辑器区 122×90 rx=6 fill=#1e293b（line 61）。Tab bar 122×14 rx=6 fill=#334155 + 底部平直 rect（lines 63-64）。3 个窗口控制点 r=3 fill=red/amber/green op=0.6（lines 64-66）。6 行代码文本 monospace 8px——def(字色 #a78bfa)、solve(#38bdf8)、(n:int)(#94a3b8)、if(#c084fc)、n<=1(#94a3b8)、return(#c084fc)（lines 67-72）。标签文本 "代码练习"（line 74）。
- **课件（ppt）**: 幻灯片区 118×72 rx=6 fill=#fef2f2（line 81）。标题栏 94×12 rx=3 fill=#dc2626 op=0.15 + "Slide Title" 9px/700（lines 83-84）。2 条文字行 rect（lines 85-86，宽度 40/55）。迷你图表 rect 50×20 rx=4 fill=#dc2626 op=0.1 stroke=#fca5a5（line 87）。3 个幻灯片导航点 r=4 op 递减（lines 89-91）。标签文本 "课件"（line 93）。

## Capabilities

### New Capabilities
- `course-thumbnail`: 算法封面横幅——djb2(title) → PALETTE[hash%8] 配色 + GEOMETRY[(hash>>4)%4] 几何图案 + 装饰圆 + 标题/副标题排版。props: title(来自 syllabus API), subtitle(来自 graph_names[0]), draft(来自 status)。无渐变叠加层。无 textShadow。
- `doc-thumbnail`: 5 种资源缩略图模板——按 resource_type 匹配。每类含 3px 顶条 + 类型专属 SVG + 底部标签 badge。props: type(来自 generativeApi ResourceSummary.resource_type)。

### Modified Capabilities
<!-- None — 这是新建 spec，不修改已有 capability -->

## Impact

- **修改文件**: `src/components/thumbnails/CourseThumbnail.tsx`（重写），`src/components/thumbnails/DocThumbnail.tsx`（重写）
- **不修改文件**: 所有使用这两个组件的父组件（`CourseCardGrid`、`RecentResources`、`GeneratedResources`、`QuizAttempts`）——props 接口保持不变
- **SVG 对照**: `ref-course-thumbnails.svg` 68 行全量，`ref-doc-thumbnails.svg` 95 行全量
- **零 API 调用**: 纯视觉组件，无直接 API 依赖
