# Tasks: Frontend Portal Redesign

整合所有 mockup 设计决策后的统一实施任务。

## 1. Backend: New API Endpoints

- [x] 1.1 Add `POST /api/knowledge/video_search` endpoint — B站 search wrapper, 8s timeout
- [x] 1.2 Add `POST /api/knowledge/github_search` endpoint — GitHub repo search, params: query/topic/max_results/min_stars
- [x] 1.3 Add optional `title` parameter to existing `POST /api/file_upload_calendar` endpoint — passes through to `create_syllabus(title=title)`, enables admin-set syllabus titles in wizard
- [x] 1.4 Add buddy synthesis message generation — triggered on learning tree page visit (cached N min), buddy LLM generates 2-3 sentence suggestion from explore + weak_topics + buddy_notes context, persisted as buddy message with source="synthesis"
- [x] 1.5 Add tests for all endpoints

## 2. Frontend: Route Restructuring

- [ ] 2.1 Update `src/App.tsx`: replace routes with new architecture (Dashboard → CourseLayout → sub-pages)
- [ ] 2.2 Create `CourseLayout` component with left sidebar nav + `<Outlet/>`
- [ ] 2.3 Remove old `/` → `SubjectOverview` mapping
- [ ] 2.4 Add redirect `/learn/:id` → `/learn/:id/home`

## 3. Frontend: Dashboard Page

- [ ] 3.1 Create `src/pages/Dashboard.tsx` with scroll flow layout
- [ ] 3.2 Create `CourseCardGrid` — algorithmic banner covers (djb2 hash → palette/geometry/typography, 360×136)
- [ ] 3.3 Create `RecentResources` — cross-course generative_list top 4, type thumbnails (doc/mindmap/quiz/code/ppt)
- [ ] 3.4 Create `RecommendedExploration` — knowledge/search top 2, match % + weak-point reason
- [ ] 3.5 Create `GitHubProjects` — github_search results, language color bar + stars
- [ ] 3.6 Create `LifelongGraph` — embedded D3 study_graph/detail with course stat cards
- [ ] 3.7 Create `GalaxyReveal` — scroll-triggered parallax, 2D SVG star field, "进入全屏知识总览" link
- [ ] 3.8 Wire Dashboard to: syllabus_list + generative_list + knowledge/search + github_search

## 4. Frontend: CourseLayout + Sidebar

- [ ] 4.1 Create `src/layouts/CourseLayout.tsx` (232px left nav + main content area)
- [ ] 4.2 Create `CourseSidebar` — nav items (首页/大纲/智能体/学习成长图谱/知识图谱), active state, quick links (课程进度/我的测验)
- [ ] 4.3 Add course title + status badge + Back-to-Dashboard breadcrumb in top bar

## 5. Frontend: Subject Home Page

- [ ] 5.1 Create `src/pages/SubjectHome.tsx` — three sections: 课程资料 / AI 生成资源 / 相关视频
- [ ] 5.2 `CourseMaterials` — syllabus docs + knowledge documents (non-generated)
- [ ] 5.3 `GeneratedResources` — from generative_list, doc thumbnails per resource_type
- [ ] 5.4 `VideoGrid` — from video_search API, inline video cards (thumbnail + title + duration + source)
- [ ] 5.5 Loading skeletons and empty states for all sections

## 6. Frontend: Syllabus Page

- [ ] 6.1 Create `src/pages/SyllabusPage.tsx`
- [ ] 6.2 Integrate existing `SyllabusTimeline` + `ActivityGantt` components
- [ ] 6.3 Create `WeeklyStats` — 7d/30d active days, avg duration

## 7. Frontend: Agent Page Streamlining

- [ ] 7.1 Extract `AgentStatsBar` from old RightSidebar overview tab (综合掌握度/7天活跃/薄弱点/当前步骤)
- [ ] 7.2 Create collapsible `ProfileRadarPanel` (画像雷达, collapsed by default)
- [ ] 7.3 Create collapsible `KBSearchPanel` (知识库搜索, collapsed by default)
- [ ] 7.4 Refactor `AgentChatPanel` — 2-column: main chat (left) + collapsible panels (right)
- [ ] 7.5 Keep existing `MiniGraphPanel`, `AgentChatInput`, inline recommendation card (路径推荐) unchanged

## 8. Frontend: Learning Tree Page

- [ ] 8.1 Create `src/pages/LearningTreePage.tsx` — split layout: D3 graph (left 560px) + analysis cards (right 304px)
- [ ] 8.2 Reuse `D3GraphViewer` for force graph — student nodes (green=mastered, indigo=learning, red=weak) + buddy hint nodes (purple dashed). Requires: add `GROUP_COLORS.buddy_hint` to D3GraphViewer, merge buddy_tree explore nodes as extra graph data with group="buddy_hint"
- [ ] 8.3 `WeaknessAnalysis` panel — top 3-4 weak nodes: title, problem description, buddy short comment, mastery score
- [ ] 8.4 `ExploreGapList` panel — buddy_tree explore region nodes: title, summary, associated trunk path, "→ 和智能体对话" CTA
- [ ] 8.5 `BuddyObservations` section — buddy_notes cards: node title, observation text, timestamp, mastery_hint (stronger/weaker)
- [ ] 8.6 `BuddyMemoryCloud` section — buddy_memory tags as styled chips (purple=weak pattern, green=strength)
- [ ] 8.7 `BuddySuggestion` bar — 2-3 sentence natural language suggestion from 小觉. Backend: add synthesis message type to buddy (source="synthesis"), triggered on tree page visit, cached N minutes
- [ ] 8.8 Stats header — 学习记录/薄弱点/掌握度/辍学风险/小觉提示 counts
- [ ] 8.9 View toggle — 力导向/树状/层级/学伴视角 (学伴视角 default on)
- [ ] 8.10 Gap summary bar — "+N 提示节点 · 覆盖 M 薄弱区 · 建议优先顺序: ..." (注意: 不展示掌握度提升预估——该数字无可靠口岸)

## 9. Frontend: Galaxy Feature Pages

- [ ] 9.1 Remove left sidebar (course cards, admin tools) from Galaxy page — keep 3D body, DetailPanel, NebulaOverlay, view toggles
- [ ] 9.2 Create `KnowledgeGalaxy` for `/learn/:id/galaxy` — embedded sub-window with dark theme inside CourseLayout
- [ ] 9.3 Create `FullGalaxy` for `/galaxy` — lifelong galaxy, loads all graph_ids
- [ ] 9.4 Add "当前: X课程图谱" / "终身学习图谱" toggle in bottom bar
- [ ] 9.5 Dark theme preserved as only exception — subtle indicator badge

## 10. Frontend: Thumbnail Generators

- [ ] 10.1 Create `CourseThumbnail` — algorithmic identicon: `djb2(title)` → `PALETTE[hash%8]` → `GEOMETRY[(hash>>4)%4]` → 360×136 SVG
- [ ] 10.2 PALETTE: {#4f46e5, #0f766e, #b91c1c, #92400e, #1e40af, #6b21a8, #9d174d, #166534}
- [ ] 10.3 GEOMETRIES: {斜线交叉, 矩形堆叠, 同心波纹, 三角重叠} — semi-transparent white overlay
- [ ] 10.4 Create `DocThumbnail` — type-based SVG templates:
  - `documents`: blue #2563eb, corner-fold doc with text lines
  - `mindmap`: emerald #059669, central node + branching connections
  - `quiz`: amber #d97706, question mark + answer options
  - `coding_practice`: violet #7c3aed, dark editor with syntax-colored code
  - `ppt`: red #dc2626, slide preview with title + chart elements
- [ ] 10.5 Use `CourseThumbnail` in Dashboard CourseCardGrid and CourseSidebar
- [ ] 10.6 Use `DocThumbnail` in SubjectHome (GeneratedResources) and Dashboard (RecentResources, RecommendedExploration)

## 11. Frontend: Global Buddy FAB + Floating Chat Window

- [ ] 11.1 Create `BuddyFAB` — 56px floating button, bottom-right, notification badge with unread count
- [ ] 11.2 Create `BuddyFloatWindow` — compact floating chat (~340×420), fixed position bottom-right, non-draggable
- [ ] 11.3 FAB → FloatWindow open animation (scale + fade from FAB origin)
- [ ] 11.4 FloatWindow → minimize back to FAB, preserve unread badge state
- [ ] 11.5 Chat messages display: proactive alerts (source label), user messages, buddy replies, `create_memory_tag` indicator
- [ ] 11.6 Chat input + send button, Enter to send / Shift+Enter newline
- [ ] 11.7 Global scope: BuddyFAB + BuddyFloatWindow mounted at CourseLayout level, available on all course sub-pages

## 12. Frontend: Buddy Auto-Popup Bubble

- [ ] 12.1 Create `BuddyPopupBubble` — appears near FAB when new proactive message arrives
- [ ] 12.2 Bubble content: buddy avatar + message preview text + timestamp + close button + pointer to FAB
- [ ] 12.3 Auto-dismiss after 5 seconds, FAB retains unread badge
- [ ] 12.4 Click bubble → open BuddyFloatWindow; click close → dismiss bubble, keep badge
- [ ] 12.5 Only one bubble visible at a time; new message replaces existing bubble

## 13. Frontend: Admin Pages

- [ ] 13.1 Create `AdminCreateSubjectModal` — 3-step wizard: ① basic info (name/description/weeks/goal template) → ② graph selection → ③ confirm & create
- [ ] 13.2 Wizard boundary: creates draft syllabus (not published), then hands off to AdminSubjectDetail for full editing
- [ ] 13.3 Update `AdminSubjectDetail` styles: dark space theme → Agent light theme
- [ ] 13.4 Update `AdminStudents` styles: dark → light
- [ ] 13.5 Update `AdminGraph` styles: dark → light
- [ ] 13.6 Sidebar nav consistency: 学科总览/学生进度/知识图谱 with "← 返回首页" breadcrumb

## 14. Frontend: Quiz Attempts Page

- [ ] 14.1 Create `src/pages/QuizAttempts.tsx` — per-course quiz attempt history from sidebar "我的测验" quick link
- [ ] 14.2 Aggregate quiz resources by resource_type=quiz, show latest attempt per resource (score, correct count, weak topics)
- [ ] 14.3 Unattempted quizzes shown as gray pending state
- [ ] 14.4 Type-specific card thumbnails for each quiz resource

## 15. Integration & Polish

- [ ] 15.1 Consistent Agent light theme across all pages (except Galaxy dark sub-window)
- [ ] 15.2 Replace emoji icons with lucide-react equivalents
- [ ] 15.3 Add loading states and error boundaries to all new pages
- [ ] 15.4 Test full user flow: Login → Dashboard → Create Subject (wizard) → Course Home → Agent → Tree → Galaxy → Quiz Attempts
- [ ] 15.5 Test admin flow: Dashboard → Create Subject → Admin Dashboard (fill knowledge, edit syllabus) → Students → Graph
- [ ] 15.6 Admin pages sidebar nav with breadcrumb "← 返回首页"
