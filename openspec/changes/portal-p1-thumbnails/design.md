## Context

`CourseThumbnail` 是课程卡片顶部横幅组件（360×136 SVG），`DocThumbnail` 是资源缩略图组件（150×166 SVG）。两者被 Dashboard、SubjectHome、RecentResources、QuizAttempts 等页面引用。

当前实现与 SVG 设计稿的偏差已在 `frontend-portal-redesign-fixup` 中部分修复（Coursethumbnail 去掉了渐变叠加层和 textShadow），但仍存在结构性问题：装饰圆坐标不随 viewBox 缩放、几何图案布局与 SVG 不完全一致、DocThumbnail 缺少底部类型标签 badge。

本设计聚焦于逐元素对照 SVG，建立完整的函数级数据流。

## Goals / Non-Goals

**Goals:**
- 逐元素对照 `ref-course-thumbnails.svg` 和 `ref-doc-thumbnails.svg`，确保每个 SVG 元素在实现中有对应
- 定义每个函数的输入输出类型和内部算法逻辑
- 零假数据——所有视觉元素由真实 props 驱动

**Non-Goals:**
- 不涉及任何 API 调用（两个组件都是纯视觉组件）
- 不修改使用这两个组件的父组件（props 接口保持兼容）

## 影响文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/thumbnails/CourseThumbnail.tsx` | 重写 | 完全对照 ref-course-thumbnails.svg |
| `src/components/thumbnails/DocThumbnail.tsx` | 重写 | 完全对照 ref-doc-thumbnails.svg |

## 函数-API 级完整数据流

### CourseThumbnail 数据流

```
API: POST /api/syllabus_list {user_id}
  → {syllabuses: [{syllabus_id, title, graph_names, status}]}
    → Dashboard.tsx: setSyllabuses(data.syllabuses)
      → CourseCardGrid: <CourseCardGrid syllabuses={syllabuses} />
        → <CourseThumbnail title={s.title} subtitle={s.graph_names?.[0]} draft={s.status==="draft"} />
          ├── djb2(title) → PALETTE[hash%8] → bgColor
          ├── (hash>>4)%4 → GEOMETRIES[i] → 几何图案
          └── SVG render: {bgColor} → DecorativeCircles → GeometryPattern → text(title,22px/800/white)
```

### DocThumbnail 数据流

```
API: POST /api/generative_list {user_id, syllabus_id, resource_type}
  → {materials: [{resource_id, resource_type, title, topic, ...}]}
    → RecentResources / GeneratedResources / QuizAttempts:
      → <DocThumbnail type={r.resource_type} />
        ├── TYPE_STYLES[type] → {bg, accent, fg, stroke, label}
        └── SVG render: white card + 3px top bar + type SVG icon + bottom label badge
```

## 函数级收口与内部逻辑

### CourseThumbnail.tsx

#### `djb2(str: string): number`
- **输入**: title 字符串（如 "大数据概论"）
- **输出**: 32-bit unsigned integer
- **内部逻辑**: 经典 djb2 哈希——`hash = ((hash << 5) + hash + charCode) | 0`，迭代每个字符，返回 `hash >>> 0`
- **用途**: 确定性映射 title → 配色 + 几何图案。同一课程名始终得到相同的封面

#### `PALETTE: readonly string[]`
- **定义**: `["#4f46e5", "#0f766e", "#b91c1c", "#92400e", "#1e40af", "#6b21a8", "#9d174d", "#166534"]`
- **来源**: ref-course-thumbnails.svg 底部算法参数
- **选取**: `PALETTE[hash % 8]`

#### `GEOMETRIES: readonly Geometry[]`
- **定义**: `["diagonal", "stacked", "ripple", "triangles"]` — 4 种几何图案
- **选取**: `GEOMETRIES[(hash >> 4) % 4]`

#### `GeometryPattern({ type }: { type: Geometry }): JSX.Element`
- **输入**: 几何类型字符串
- **输出**: SVG `<g>` 元素
- **内部逻辑**: switch 分发到 4 种图案：
  - `"diagonal"`: 2 条斜线，stroke=rgba(255,255,255,0.08/0.05)，strokeWidth=2，对照 SVG Banner 1
  - `"stacked"`: 3 个矩形堆叠，opacity=0.1，stroke=#fff，strokeWidth=3，对照 SVG Banner 2
  - `"ripple"`: 4 个同心椭圆，stroke=rgba(255,255,255,0.12)，opacity 0.6→0.24
  - `"triangles"`: 4 个重叠三角，fill=rgba(255,255,255,0.06)，stroke=rgba(255,255,255,0.14)

#### `DecorativeCircles(): JSX.Element`
- **输入**: 无（硬编码坐标）
- **输出**: 2 个 `<circle>` 元素
- **内部逻辑**: 
  - `circle cx=220 cy=40 r=70 fill=rgba(255,255,255,0.06)` 
  - `circle cx=60 cy=90 r=100 fill=rgba(255,255,255,0.04)`
- **约束**: 坐标按 360×136 viewBox 比例设计，若 props 修改 viewBox 需同步缩放

#### `DraftCircle(): JSX.Element`
- **输入**: 无
- **输出**: 1 个 `<circle>` 元素
- **内部逻辑**: `circle cx=200 cy=40 r=70 fill=rgba(255,255,255,0.05)`
- **约束**: draft 封面仅 1 个装饰圆，无几何图案，背景色 `#94a3b8`

#### `CourseThumbnail(props: CourseThumbnailProps): JSX.Element`
- **输入**:
  ```ts
  { title: string; subtitle?: string; width?: number; height?: number; draft?: boolean; className?: string }
  ```
- **输出**: `<svg viewBox="0 0 {width} {height}">`
- **内部逻辑**:
  1. `useMemo`: djb2(title) → `{bgColor, geometry}`（draft 时 bgColor=#94a3b8, geometry=null）
  2. 渲染层序（从底到顶）:
     - `<rect rx=12 fill={bgColor}>` — 纯色背景
     - `<DecorativeCircles />` 或 `<DraftCircle />` — 装饰圆
     - `<GeometryPattern type={geometry} />` — 几何图案（draft 跳过）
     - `<text fontSize=22 fontWeight=800 letterSpacing=2 fill=white>` — 标题
     - `<text fontSize=10 fill=rgba(255,255,255,0.5)>` — 副标题
  3. **无渐变叠加层，无 textShadow**

#### SVG 元素对照清单 (ref-course-thumbnails.svg)

| SVG 元素 | Banner 1 (已发布, diagonal) | Banner 2 (已发布, stacked) | Banner 3 (草稿) |
|----------|---------------------------|--------------------------|----------------|
| 卡片底板 | 270×230, rx=12, #fff | 270×230, rx=12, #fff | 270×230, rx=12, #fafafa, stroke-dasharray=5,3 |
| Banner 封面 | 270×120, rx=12, #4f46e5 | 270×120, rx=12, #0f766e | 270×120, rx=12, #94a3b8 |
| 底部铺平 rect | y=60, h=60, 同色 | y=60, h=60, 同色 | y=60, h=60, 同色 |
| 装饰圆 1 | cx=220,cy=40,r=70,op=0.06 | cx=220,cy=30,r=80,op=0.06 | cx=200,cy=40,r=70,op=0.05 |
| 装饰圆 2 | cx=60,cy=90,r=100,op=0.04 | cx=60,cy=80,r=90,op=0.04 | 无 |
| 几何图案 | 2 条斜线, op=0.08/0.05 | 3 个矩形, op=0.1 | 无 |
| 标题 | 22px, 800, #fff, ls=2 | 22px, 800, #fff, ls=2 | 20px, 800, #fff |
| 副标题 | 10px, rgba(255,255,255,0.5) | 10px, rgba(255,255,255,0.5) | 10px, rgba(255,255,255,0.4) |
| 渐变叠加层 | **不存在** | **不存在** | **不存在** |

### DocThumbnail.tsx

#### `TYPE_STYLES: Record<ResourceType, {bg, accent, fg, stroke, label}>`
- **定义**: 5 种资源类型的配色映射
  - `documents`: `{bg:"#eff6ff", accent:"#2563eb", fg:"#1e40af", stroke:"#bfdbfe", label:"文档"}`
  - `mindmap`: `{bg:"#ecfdf5", accent:"#059669", fg:"#065f46", stroke:"#a7f3d0", label:"思维导图"}`
  - `quiz`: `{bg:"#fffbeb", accent:"#d97706", fg:"#92400e", stroke:"#fde68a", label:"测验"}`
  - `coding_practice`: `{bg:"#ede9fe", accent:"#7c3aed", fg:"#5b21b6", stroke:"#c4b5fd", label:"代码练习"}`
  - `ppt`: `{bg:"#fef2f2", accent:"#dc2626", fg:"#991b1b", stroke:"#fecaca", label:"课件"}`
- **来源**: ref-doc-thumbnails.svg

#### `TopBar({ w, accent }: { w: number; accent: string }): JSX.Element`
- **输出**: `<rect width={w} height=3 rx=1.5 fill={accent}>` — 顶部 3px 色标

#### `TypeLabel({ w, h, c }: { w: number; h: number; c }): JSX.Element`
- **输出**: 底部居中标签 — `rect 56×16 rx=5 fill={accent} opacity=0.1` + `text 9px/600 fill={accent}`
- **文本内容**: `c.label`（如 "文档"、"思维导图" 等）

#### `DocThumbnail(props: DocThumbnailProps): JSX.Element`
- **输入**:
  ```ts
  { type: ResourceType; width?: number; height?: number; className?: string }
  ```
- **输出**: `<svg viewBox="0 0 {width} {height}">`
- **内部逻辑**:
  1. `TYPE_STYLES[type]` → 配色
  2. 渲染层序（从底到顶）:
     - `<rect rx=10 fill=#fff stroke={stroke}>` — 白色卡片底板
     - `<TopBar>` — 3px 类型色顶条
     - 类型专属 SVG — 5 种 switch（DocumentSVG/MindmapSVG/QuizSVG/CodingPracticeSVG/PptSVG）
     - `<TypeLabel>` — 底部类型标签 badge

#### 5 种类型 SVG 内部元素对照 (ref-doc-thumbnails.svg)

| 类型 | 底板 | 顶条色 | 核心 SVG 元素 |
|------|------|-------|-------------|
| documents | 150×166, stroke=#bfdbfe | #2563eb | 内部文档区 118×100 rx=4 fill=#eff6ff + 折角 polygon + 6 条文字行 rect + 分隔线 |
| mindmap | 150×166, stroke=#a7f3d0 | #059669 | 中心圆 r=22 + 内点 r=7 + 3 条分支线（上/左下/右下）+ 1 条子分支（左下深度2） |
| quiz | 150×166, stroke=#fde68a | #d97706 | "?" 水印 24px op=0.15 + 3 个选项框 114×22 rx=6（A 灰色/B 琥珀高亮/C 灰色） |
| coding_practice | 150×166, stroke=#c4b5fd | #7c3aed | 编辑器 122×90 rx=6 fill=#1e293b + tab bar 14px fill=#334155 + 3 窗口点 + 6 行代码文本 monospace |
| ppt | 150×166, stroke=#fecaca | #dc2626 | 幻灯片区 118×72 rx=6 fill=#fef2f2 + 标题栏 + 文字行 + 迷你图表 50×20 + 3 个导航点 |

## Decisions

### Decision 1: 装饰圆坐标不随 viewBox 缩放
- **选择**: 固定像素坐标，要求在 360×136 的 viewBox 下精确渲染
- **备选方案**: 百分比坐标 —— 被否决，因为 SVG ref 使用固定坐标，百分比无法精确映射

### Decision 2: 无渐变叠加层
- **选择**: 移除 `<defs>` 渐变叠加 `<rect>`，标题白色文字直接放纯色背景上
- **理由**: ref-course-thumbnails.svg 中 3 个 Banner 均无渐变叠加层

### Decision 3: 不修改 props 接口
- **选择**: `CourseThumbnailProps` 和 `DocThumbnailProps` 保持现有字段
- **理由**: 这是纯视觉修复，不改变父组件调用方式

## Risks / Trade-offs

- **草稿卡片无装饰圆**: `DraftCircle` 仅 1 个圆，坐标硬编码 — 若 viewBox 改变需同步更新
- **DocThumbnail 高度 166px**: 原有调用方使用 `height=100` 或 `height=172`——保持兼容，父组件自行控制尺寸
