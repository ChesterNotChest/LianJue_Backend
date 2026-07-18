## Context

SubjectHome 是学科首页，渲染在 CourseLayout 内（左侧 232px 侧栏 + 顶栏 + 主内容区）。`02-course-home.svg`（140 行）定义了完整视觉规范。

三个内容组件（CourseMaterials、GeneratedResources、VideoGrid）已在前轮 fixup 中基本对齐 SVG，但顶栏、侧栏、BuddyFAB 和 CourseMaterials 数据源仍有偏差。

## Goals / Non-Goals

**Goals:**
- 逐元素对照 `02-course-home.svg`，重写 CourseSidebar 和 BuddyFAB，修正 CourseLayout 顶栏
- CourseMaterials 使用真实 API 数据替代假数据
- 验证 GeneratedResources 和 VideoGrid 对齐

**Non-Goals:**
- 不修改 CourseThumbnail/DocThumbnail（portal-p1-thumbnails 覆盖）
- 不新增后端 API 端点

## 影响文件范围

| 文件 | 操作 | 变更范围 |
|------|------|---------|
| `src/layouts/CourseLayout.tsx` | 修改 | 顶栏 header 元素对齐 |
| `src/layouts/CourseSidebar.tsx` | 重写 | 移出 CourseThumbnail，导航 SVG 对齐 |
| `src/pages/SubjectHome.tsx` | 修改 | 课程资料 API 数据源 |
| `src/components/buddy/BuddyFAB.tsx` | 重写 | SVG 表情风格 |

## 函数-API 级完整数据流

### SubjectHome 数据流

```
CourseLayout (wrapper)
  ├── useParams → syllabusId
  ├── useEffect → POST /api/syllabus_list → courseTitle, courseStatus
  ├── CourseSidebar({courseTitle, courseStatus, syllabusId})
  │     └── Nav items → navigate(/learn/{sid}/{path})
  │
  ├── header (top bar)
  │     ├── Logo "联觉 LianJue" → navigate("/")
  │     ├── "/" separator
  │     ├── courseTitle text
  │     ├── status badge
  │     └── "← 返回首页" → navigate("/")
  │
  └── <Outlet /> → SubjectHome
        │
        ├── ① POST /api/generative_list {user_id, syllabus_id, resource_type:"documents"}
        │     → {materials: [ResourceSummary]}
        │     → setMaterials() → CourseMaterials
        │
        ├── ② POST /api/generative_list {user_id, syllabus_id}  (all types)
        │     → {materials: [ResourceSummary]}
        │     → setResources() → GeneratedResources
        │
        ├── ③ POST /api/knowledge/video_search {query, max_results:6}
        │     → {videos: [{title, thumbnail_url, video_url, duration, source, author, play_count, publisher}]}
        │     → setVideos() → VideoGrid
        │
        └── BuddyFAB (fixed, bottom-right)
              ├── unreadCount → red badge
              └── onClick → toggle BuddyFloatWindow
```

### CourseSidebar 数据流

```
CourseLayout
  ├── courseTitle: string (from syllabus_list API)
  ├── courseStatus: "draft" | "published"
  ├── syllabusId: number
  │
  └── <CourseSidebar courseTitle={title} courseStatus={status} syllabusId={sid}>
        │
        ├── TitleRow: courseTitle 15px/700/#0f172a
        ├── StatusBadge: 52×20 rx=5 fill=#ede9fe text 9px/600/#6366f1
        ├── NavItems (5 items)
        │     ├── "学科首页" → /learn/{sid}/home
        │     ├── "教学大纲" → /learn/{sid}/syllabus
        │     ├── "智能体" → /learn/{sid}/agent
        │     ├── "学习成长图谱" → /learn/{sid}/tree
        │     └── "知识图谱" → /learn/{sid}/galaxy
        ├── Divider line
        ├── "快捷入口" label 11px/600/#94a3b8
        └── QuickLinks
              ├── "课程进度" → /learn/{sid}/syllabus
              └── "我的测验" → /learn/{sid}/quizzes
```

## 函数级收口与内部逻辑

### CourseLayout.tsx — 顶栏修正

#### Header 渲染层序
1. `<header className="h-14 ...">` — 56px 高度
2. Logo: `<span fontSize=16 fontWeight=800 fill=#6366f1 letterSpacing=1>` "联觉 LianJue"
3. 分隔符: `<span fontSize=13 fill=#cbd5e1>` "/"
4. 课程标题: `<span fontSize=13 fontWeight=600 fill=#0f172a>` {courseTitle}
5. 返回链接: `<a fontSize=11 fill=#6366f1>` "← 返回首页"

**对照**: SVG lines 7-10

---

### CourseSidebar.tsx — 重写

#### `NavItem` 类型
```ts
interface NavItem { key: string; label: string; path: string; }
```

#### `NAV_ITEMS` (MODIFIED)
```ts
const NAV_ITEMS: NavItem[] = [
  { key: "home",     label: "学科首页",       path: "home" },
  { key: "syllabus", label: "教学大纲",       path: "syllabus" },
  { key: "agent",    label: "智能体",         path: "agent" },
  { key: "tree",     label: "学习成长图谱",    path: "tree" },
  { key: "galaxy",   label: "知识图谱",        path: "galaxy" },
];
```

#### `CourseSidebar(props): JSX.Element`
- **内部逻辑**:
  1. **无 CourseThumbnail** — SVG 仅用文字标题
  2. 标题行: `text fontSize=15 fontWeight=700 fill=#0f172a` {courseTitle}
  3. 状态 badge: published→`rect 52×20 rx=5 fill=#ede9fe` + "已发布" 9px/600/#6366f1；draft→amber 色
  4. 导航列表: 每个 item 含
     - 激活态: 背景 `rect 208×38 rx=8 fill=#6366f1 op=0.1` + 左侧条 `rect 3×38 rx=1.5 fill=#6366f1` + text 13px/700/#6366f1
     - 非激活: text 13px/#475569，hover 时背景变化
  5. 分隔线: `<line>` stroke=#f1f5f9
  6. "快捷入口" label: 11px/600/#94a3b8
  7. 快捷链接: "课程进度" "我的测验" 12px/#475569（无图标）
  8. 底部返回: "返回首页" → navigate("/")
- **不包含**: lucide 图标（SVG 不存在）
- **对照**: SVG lines 13-28

---

### SubjectHome.tsx — 数据源修正

#### `loadData()` 修改
```ts
// 课程资料: 从 generative_list 加载 documents 类型（替代 syllabus_list 假数据）
setMatLoading(true);
try {
  const data = await fetchResourceList(uid, sid, "documents", 6);
  if (data.success) setMaterials(data.materials ?? []);
} catch {} finally { setMatLoading(false); }
```

---

### BuddyFAB.tsx — 重写

#### `BuddyFAB({ unreadCount, onClick }): JSX.Element`
- **输出**: `<button className="fixed bottom-6 right-6 z-40">`
- **渲染层序**:
  1. 文字标签区（FAB 左侧）:
     - "学伴小觉" 11px/#6366f1 textAnchor=end
     - "全天候陪伴" 10px/#94a3b8 textAnchor=end
  2. 外圆: `r=30 fill=#fff` + shadow filter
  3. 内圆: `r=28 fill=#6366f1`
  4. 表情:
     - 左眼: `circle cx=-6 cy=-3 r=3.5 fill=#fff op=0.9`
     - 右眼: `circle cx=6 cy=-3 r=3.5 fill=#fff op=0.9`
     - 微笑: `path d="M-8,8 Q0,18 8,8" stroke=#fff fill=none w=2 op=0.6 strokeLinecap=round`
  5. 通知 badge（unreadCount > 0 时）:
     - `circle cx=20 cy=-20 r=10 fill=#ef4444`
     - text "{count}" 9px/700/white textAnchor=middle
- **尺寸**: 总区域约 76×76（含标签和 badge）
- **对照**: SVG lines 133-139

### CourseMaterials.tsx — 验证

- Props `materials: ResourceSummary[]`（与 generativeApi 类型一致）
- 卡片 `252×135 rx=10 fill=#fff stroke=#e2e8f0` + `3px top bar fill=#64748b`
- 内部文档 SVG + 标题 12px/700 + "文档" 10px/#94a3b8 右对齐
- **对照**: SVG lines 36-71

### GeneratedResources.tsx — 验证

- 卡片 `252×124 rx=10` + 3px 类型色顶条
- 左侧类型 SVG 图标 + 右侧文字（title 13px/700 + type·match% 10px + 2-line desc 11px）
- **对照**: SVG lines 77-100

### VideoGrid.tsx — 验证

- 卡片 `252×172 rx=10`
- 深色缩略图 `252×108 rx=10 fill=#1e293b`
- 播放三角形 polygon + 时长 9px/#fff op=0.5
- 标题 12px/700 + source·author·play_count 10px + publisher 10px/#cbd5e1
- **对照**: SVG lines 106-129

## Decisions

### Decision 1: CourseSidebar 移除 CourseThumbnail banner
- **选择**: 仅显示文字标题 + 状态 badge，移除 CourseThumbnail
- **理由**: SVG lines 14-15 仅含 title text 15px/700 + badge rect，无 banner 元素

### Decision 2: CourseSidebar 移除 lucide 图标
- **选择**: 导航项仅文字，不显示图标
- **理由**: SVG lines 18-22 仅有 `<text>` 元素，无图标

### Decision 3: 激活态导航项加左侧 3px 色条
- **选择**: 激活项左侧 `rect 3×38 rx=1.5 fill=#6366f1` + 背景 `rect 208×38 rx=8 fill=#6366f1 op=0.1`
- **理由**: SVG lines 17-18 明确定义

### Decision 4: CourseMaterials 使用 generative_list API
- **选择**: `fetchResourceList(uid, sid, "documents", 6)` 替代从 syllabus_list 构造假数据
- **理由**: documents 类型的 ResourceSummary 包含 title/topic/metadata，足以驱动卡片渲染

## Risks / Trade-offs

- **CourseMaterials 空状态**: 若无 documents 资源可能显示空列表。保留空状态处理。
- **BuddyFAB 表情为 SVG 内联**: 使用内联 SVG 替代 lucide 图标，精确匹配设计稿。
