# Tasks: Portal Phase 3 — SubjectHome 全量对齐

> ⛔ **硬性门禁**: 每个 task 必须对照 `02-course-home.svg` 的 EXACT 行号完成逐元素验证。

## 1. CourseLayout 顶栏修正（对照 SVG lines 7-10）

- [x] 1.1 顶栏高度 — `h-14` (56px), `bg-white`, `border-b border-[#f1f5f9]` (SVG line 7)
- [x] 1.2 Logo 文字 — "联觉 LianJue" 16px/800/#6366f1 letterSpacing=1 (SVG line 8)
- [x] 1.3 分隔符 — "/" 13px/#cbd5e1 (SVG line 9)
- [x] 1.4 课程标题 — courseTitle 13px/600/#0f172a (SVG line 9)
- [x] 1.5 返回链接 — "← 返回首页" 11px/#6366f1, navigate to "/" (SVG line 10)
- [x] 1.6 对照 SVG lines 7-10 逐元素验收

## 2. CourseSidebar 重写（对照 SVG lines 13-28）

- [x] 2.1 移出 CourseThumbnail banner — 侧栏顶部仅文字标题 (SVG lines 14-15)
- [x] 2.2 标题行 — courseTitle 15px/700/#0f172a + 状态 badge 52×20 rx=5 fill=#ede9fe text "已发布" 9px/600/#6366f1 (SVG lines 14-15)
- [x] 2.3 NAV_ITEMS 标签更新 — "学科首页/教学大纲/智能体/学习成长图谱/知识图谱" (SVG lines 18-22)
- [x] 2.4 激活态 — 左侧 3px 色条 `3×38 rx=1.5 fill=#6366f1` + 背景 `208×38 rx=8 fill=#6366f1 op=0.1` + text 13px/700/#6366f1 (SVG lines 17-18)
- [x] 2.5 非激活态 — text 13px/#475569, 无图标 (SVG lines 19-22)
- [x] 2.6 移除所有 lucide 图标 — 导航项和快捷链接均为纯文字 (SVG 无图标)
- [x] 2.7 分隔线 — `<line>` stroke=#f1f5f9 between nav and quick links (SVG line 24)
- [x] 2.8 "快捷入口" label — 11px/600/#94a3b8 (SVG line 25)
- [x] 2.9 快捷链接 — "课程进度" "我的测验" 12px/#475569 (SVG lines 26-27)
- [x] 2.10 对照 SVG lines 13-28 逐元素验收

## 3. BuddyFAB 重写（对照 SVG lines 132-139）

- [x] 3.1 文字标签区 — "学伴小觉" 11px/#6366f1 + "全天候陪伴" 10px/#94a3b8, textAnchor=end (SVG line 139)
- [x] 3.2 外圆 — `r=30 fill=#fff` + drop-shadow filter (SVG line 134)
- [x] 3.3 内圆 — `r=28 fill=#6366f1` (SVG line 134)
- [x] 3.4 左眼 — `circle cx=-6 cy=-3 r=3.5 fill=#fff op=0.9` (SVG line 135)
- [x] 3.5 右眼 — `circle cx=6 cy=-3 r=3.5 fill=#fff op=0.9` (SVG line 135)
- [x] 3.6 微笑 — `path d="M-8,8 Q0,18 8,8" stroke=#fff fill=none strokeWidth=2 op=0.6 strokeLinecap=round` (SVG line 136)
- [x] 3.7 通知 badge — `circle cx=20 cy=-20 r=10 fill=#ef4444` + text count 9px/700/white textAnchor=middle (SVG line 137)
- [x] 3.8 移除 lucide MessageCircle 图标 — 使用内联 SVG 表情
- [x] 3.9 对照 SVG lines 132-139 逐元素验收

## 4. CourseMaterials 数据源修正（对照 SVG lines 36-71）

- [x] 4.1 数据源改为 `fetchResourceList(uid, sid, "documents", 6)` — 从 generative_list API 加载 documents 类型
- [x] 4.2 移出从 syllabus_list 构造假数据的逻辑
- [x] 4.3 Props 类型改为 `materials: ResourceSummary[]`（与 generativeApi 一致）
- [x] 4.4 卡片结构验证 — 252×135 rx=10 + 3px #64748b top bar + 折角文档 SVG + title 12px/700 + "文档" 10px 右对齐
- [x] 4.5 空状态 — API 返回空数组时 return null (不显示)
- [x] 4.6 对照 SVG lines 36-71 逐元素验收

## 5. 已对齐组件验证（对照 SVG）

- [x] 5.1 GeneratedResources 验证 — 卡片 252×124 rx=10 + 3px 彩色顶条 + 左侧类型 SVG + 右侧文字 (SVG lines 77-100)
- [x] 5.2 VideoGrid 验证 — 卡片 252×172 rx=10 + 深色缩略图 108px + 播放三角 + 时长 + 来源信息 (SVG lines 106-129)

## 6. 构建验证

- [x] 6.1 TypeScript 编译通过（`tsc --noEmit`）
- [x] 6.2 Vite build 通过（`vite build`）
