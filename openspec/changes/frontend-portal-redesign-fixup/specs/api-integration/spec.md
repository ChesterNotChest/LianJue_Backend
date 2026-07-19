## 发现：旧前端已有完整的数据流和组件，不得抛弃

本轮是**重构布局和路由**，不是重写数据流。以下旧前端能力已确认完整且正确，新页面必须复用而非重写：

| 已有能力 | 组件/模块 | 复用方式 |
|---------|----------|---------|
| 资源预览（5种类型） | `ResourcePreviewDrawer` | 所有资源卡片 onClick → `fetchResourceDetail()` → 打开 Drawer |
| 资源内联卡片 | `ResourceCard` | Agent 对话中已有使用，保持不变 |
| 知识库搜索结果→真实文档映射 | `KBPage` 中的 `matched_sources[kind=generated_resource\|knowledge_source]` | 推荐探索卡片 onClick → 根据 kind 打开对应资源 |
| 测验交互+提交+画像同步 | `ResourcePreviewDrawer.QuizPreview` | 测验卡片 onClick → 打开 Drawer quiz 模式；已有"再试一次"逻辑 |
| Galaxy 3D + 学习匹配 + 轮询 | `SubjectOverview` 中的全部逻辑 | KnowledgeGalaxyPage / FullGalaxy 直接移植，不重写 |
| D3 学习图谱 | `D3GraphViewer` + `treeResponseToGraph` | LearningTreePage 复用 |
| SSE 对话流 | `useSSEStream` + `agentStore` | AgentChatPanel 已有，保持不变 |
| Heartbeat 轮询 | `useHeartbeat` | Dashboard、Galaxy 页接入 |

## 缺口：需新增的后端端点

以下端点后端函数已存在但缺 HTTP 路由包装，需在 `study_buddy_api.py` 中新增：

| 端点 | 封装函数 | 返回 |
|------|---------|------|
| `GET /api/study_buddy/tree?user_id=N&syllabus_id=N` | `load_buddy_tree(user_id, syllabus_id)` → reads `study_buddy/user_{id}/syllabus_{sid}/tree.json` | `{success, tree: BuddyTree\|null}` |
| `GET /api/study_buddy/memory?user_id=N&syllabus_id=N` | `load_memory_tags(user_id, syllabus_id)` → reads `study_buddy/user_{id}/syllabus_{sid}/buddy_memory.jsonl` | `{success, tags: [{tag, created_at, last_referenced_at}]}` |

## 缺口：API 方法修正

以下端点 spec 中原方法错误，以实际后端路由为准：

| spec 中错误写法 | 正确写法（后端实际路由） |
|----------------|---------------------|
| `POST /api/knowledge/search` `{query, top_k, user_id}` | `GET /api/knowledge/search?q=...&top_k=N&graph_name=...` |
| `POST /api/syllabus_save` | `POST /api/syllabus_update_draft`（草稿）或 `POST /api/syllabus_update`（已发布） |

## 缺口：QuizAttempts 聚合方式

`GET /api/quiz_attempts?user_id=N&resource_id=X` 是 per-resource 端点，不支持按 syllabus 聚合。QuizAttempts 页实现方式：
1. 先调 `fetchResourceList(userId, syllabusId, "quiz")` 获取该课程所有 quiz 资源的 `resource_id` 列表
2. 对每个 `resource_id` 调 `GET /api/quiz_attempts?user_id=N&resource_id=X`
3. 前端合并结果：有 attempt → 显示得分/正确数/薄弱点；无 attempt → "未作答"灰态
4. 点击任一 quiz → 打开已有 `ResourcePreviewDrawer` 的 `QuizPreview` 模式（含交互答题 + 提交 + 画像同步 + "再试一次"按钮）

## ADDED Requirements

### Requirement: Zero fake data — all data from real APIs
系统中 SHALL NOT 存在任何硬编码常量占位数据。API 调用失败时展示空状态 UI，不得使用硬编码假数据作为 fallback。

#### Scenario: No hardcoded fallback values
- **WHEN** 任何 API 调用返回空或失败
- **THEN** 组件展示空状态 UI（如"暂无数据"、"加载失败"）
- **AND** 不得使用字符串常量作为数据替代
- **AND** 不得传递空数据结构作为默认 props——必须在 API 调用前展示 loading 态

---

### Requirement: Complete interaction trace — every button/action on every page

以下为每页每个可交互元素的完整行为追踪链。格式：`触发 → 函数 → API → 状态 → UI 结果`。

---

#### Dashboard 页交互追踪 — 继承来源标注

##### 1. 页面加载
- **继承自**: `SubjectOverview.tsx` useEffect (syllabus_list + study_graph) + `RightSidebar.tsx` KBPage (knowledge/search) + `RightSidebar.tsx` FilesPage (generative_list)
- **触发**: 组件 mount
- **API (并行)**:
  a. `apiUrl("/api/syllabus_list")` POST `{user_id}` → `setSyllabuses(data.syllabuses)`
  b. `fetchResourceList(userId, undefined, undefined, 4)` → `setResources(data.materials)` — 继承自 RightSidebar.FilesPage 的 `fetchResourceList()` 调用方式
  c. `apiUrl("/api/knowledge/search?q=${encodeURIComponent(query)}&top_k=2")` GET — 继承自 RightSidebar.KBPage 的 `handleSearch()` 调用方式
  d. `apiUrl("/api/knowledge/github_search")` POST `{query, max_results:3}` — 后端新端点，query 从 syllabuses API 响应的 `title`/`subject_title` 字段提取并 join，不得硬编码
  e. `fetchStudyGraph(userId)` → `treeResponseToGraph()` — 继承自 SubjectOverview 的 study_graph 加载逻辑
- **UI 结果**: 各区块先展示骨架屏，数据到达后替换。API 失败区块展示"暂无数据"

##### 2. 搜索框输入回车
- **继承自**: `RightSidebar.tsx` KBPage 的搜索框 + `handleSearch()` + `onKeyDown Enter`
- **触发**: `onKeyDown` Enter
- **函数**: `apiUrl("/api/knowledge/search?q=${encodeURIComponent(inputValue)}&top_k=5")` GET
- **状态**: `searching: boolean`, `searchResults: any[]`
- **UI 结果**: 搜索结果列表。每项显示标题（`extractTitle(content)` 逻辑继承自 KBPage 同名函数）和来源文件（`extractSource(content)` 继承自 KBPage 同名函数）

##### 3. [+ 创建新学科] 按钮
- **继承自**: `SubjectOverview.tsx` 的 [创建新学科] 按钮 + `CreateSubject.tsx` 的完整创建流程
- **触发**: onClick
- **函数**: `setCreateModalOpen(true)` — 打开 AdminCreateSubjectModal（继承自 CreateSubject 的 Step 流程）
- **Modal 内 Step 1→2**: `apiUrl("/api/graph/list")` GET → `setGraphs(data.graphs)`
- **Modal 内 Step 3 提交**: ① `apiUrl("/api/file_upload_calendar")` POST → ② `apiUrl("/api/syllabus_build_draft")` POST
- **权限**: `authStore.permission === "operator"` 才可见（继承自 SubjectOverview 的权限判断）

##### 4. 课程卡片点击（整卡）
- **继承自**: `SubjectOverview.tsx` 的 `handleEnterLearning(syllabusId)` — `navigate(/learn/${syllabusId})`
- **触发**: onClick card body
- **行为**: `navigate(/learn/${syllabusId}/home)`

##### 5. [进入学习] 按钮（课程卡片内）
- **继承自**: `SubjectOverview.tsx` 的 `handleEnterLearning(syllabusId)`
- **触发**: onClick
- **行为**: `navigate(/learn/${syllabusId}/home)`

##### 6. [管理] 按钮（课程卡片内）
- **继承自**: `SubjectOverview.tsx` 的 `handleManage(subject)` — status==="published" → `/admin/subject/${id}`, draft → `/admin/create-subject/${id}`
- **触发**: onClick
- **行为**: status==="published" → `navigate(/admin/subject/${syllabusId})`; status==="draft" → `navigate(/admin/create-subject/${syllabusId})`
- **权限**: `authStore.permission === "operator"` 才可见

##### 7. [等待中] 按钮（草稿卡片内）
- **继承自**: SubjectOverview 草稿卡片逻辑（无 onClick，disabled 态）
- **触发**: 无（disabled）
- **行为**: 不响应点击

##### 8. [刷新] 按钮（最近资源区域）
- **继承自**: `RightSidebar.tsx` FilesPage 的资源重新加载逻辑
- **触发**: onClick
- **函数**: `fetchResourceList(userId, undefined, undefined, 4)` → `setResources(data.materials)`
- **状态**: `resLoading: boolean`
- **UI 结果**: spinner → 刷新 grid

##### 9. [刷新] 按钮（实训项目区域）
- **继承自**: 同上 FilesPage 刷新按钮的交互模式
- **触发**: onClick
- **函数**: `apiUrl("/api/knowledge/github_search")` POST `{query, max_results:3}` → `setRepos(data.repos)`

##### 10. 资源卡片点击（最近资源/推荐探索/AI生成资源）
- **继承自**: `RightSidebar.tsx` FilesPage 的资源卡片点击 → `fetchResourceDetail()` → 打开预览
- **触发**: onClick card
- **函数**: `fetchResourceDetail(userId, resourceId)` — `src/api/generativeApi.ts`
- **API**: `POST /api/generative_detail` `{user_id, resource_id}`
- **状态**: `ResourceDetail | null`
- **UI 结果**: 已有 `ResourcePreviewDrawer` 组件从右侧滑入（继承自 ResourcePreviewDrawer.tsx 的全部渲染逻辑：documents→Markdown, mindmap→Mermaid, quiz→QuizPreview, coding_practice→代码, ppt→PptViewer）

##### 11. GitHub 项目卡片点击
- **继承自**: 新逻辑（无旧对应），但行为明确
- **触发**: onClick card
- **行为**: `window.open(repo.html_url, "_blank")`

##### 12. GalaxyReveal [进入全屏知识总览 →] 链接
- **继承自**: `SubjectOverview.tsx` 的 galaxy 入口逻辑
- **触发**: onClick
- **行为**: `navigate("/galaxy")`

##### 13. [登出] 按钮（Header 内）
- **继承自**: `SubjectOverview.tsx` 的 `handleLogout()` — `authStore.logout()` + `navigate("/login")`
- **触发**: onClick
- **行为**: `authStore.logout()` → `navigate("/login")`

##### 13b. LifelongGraph D3 节点点击
- **继承自**: `D3GraphViewer` 的 `onNodeClick` prop — 已有 hover 高亮邻居 + tooltip 逻辑
- **触发**: onClick D3 node
- **行为**: 无 API — 节点数据已在本地 `study_graph/detail` 响应中
- **UI 结果**: 选中节点高亮 + 邻居节点高亮 + tooltip 显示（label + mastery_score + summary）

##### 13c. GalaxyReveal 滚动触发
- **继承自**: 新实现（IntersectionObserver），非旧代码
- **触发**: 页面滚动到 GalaxyReveal 区域（threshold 0.2）
- **行为**: 无 API — 纯 CSS transition + 2D SVG/CSS 渲染
- **UI 结果**: 背景渐变过渡（4 段色 `#f8fafc → #e2e8f0 → #334155 → #03040a`），SVG 星空 opacity 0→1

---

#### CourseLayout + Sidebar 交互追踪 — 继承来源标注

##### 14. 侧栏导航项点击
- **继承自**: `LeftSidebar.tsx` 的导航项切换逻辑（翻页按钮模式改造为垂直列表）
- **触发**: onClick nav item
- **行为**: `navigate(/learn/${syllabusId}/${path})`
- **UI 结果**: `<Outlet>` 渲染对应子路由；活跃项高亮（accent 背景 + 左侧 3px 竖线，继承自 02-course-home.svg 侧栏 active 态）

##### 15. 快捷入口 [课程进度]
- **继承自**: 新路由设计（无旧对应），行为明确
- **触发**: onClick
- **行为**: `navigate(/learn/${syllabusId}/syllabus)`

##### 16. 快捷入口 [我的测验]
- **触发**: onClick
- **行为**: `navigate(/learn/${syllabusId}/quizzes)`

##### 17. [← 返回首页] 面包屑
- **继承自**: `SubjectOverview.tsx` 的 `navigate("/")` 模式 + `AdminSubjectDetail.tsx` 的返回按钮
- **触发**: onClick
- **行为**: `navigate("/")`

##### 18. 顶栏面包屑 [联觉 LianJue]
- **触发**: onClick
- **行为**: `navigate("/")`

##### 19. 顶栏面包屑 [课程名]
- **触发**: onClick
- **行为**: `navigate(/learn/${syllabusId}/home)`

##### 20. 课程信息加载
- **继承自**: `SubjectOverview.tsx` 的 `fetch(apiUrl("/api/syllabus_list"), ...)` → `setSubjects()` → 从返回列表中提取 `title`/`status`/`graph_names` 字段
- **触发**: CourseLayout mount
- **函数**: `apiUrl("/api/syllabus_list")` POST `{user_id}` → `data.syllabuses.find(s => s.syllabus_id === sid)` → 提取 `title`（优先 `title` 字段，fallback `subject_title`）、`status`（`"draft"`/`"published"`/`"archived"`）
- **状态**: courseTitle 初始值 `""`, courseStatus 初始值 `"published"`
- **UI 结果**: Sidebar 标题更新为课程名，状态 badge 显示对应文字和颜色

##### 21. BuddyFAB 点击
- **继承自**: `RightSidebar.tsx` BuddyPanel 的展开/折叠逻辑
- **触发**: onClick FAB
- **函数**: `setBuddyOpen(!buddyOpen)`
- **UI 结果**: FloatWindow 弹出/关闭；FAB 红点 badge 清除为 0

##### 22. BuddyFloatWindow [发送] 按钮
- **继承自**: `RightSidebar.tsx` BuddyPanel 的 `sendBuddyMessage()` + `POST /api/study_buddy/chat`
- **触发**: onClick Send / Enter 键
- **函数**: `sendBuddyMessage(userId, syllabusId, text)` — `src/api/studyBuddyApi.ts`
- **API**: `POST /api/study_buddy/chat` `{user_id, syllabus_id, message}`
- **状态**: 乐观更新本地 `messages[]`，追加 `{from: "user", text, created_at}`
- **UI 结果**: 消息列表滚动到底部；输入框清空；下一轮轮询获取 buddy 回复

##### 23. Buddy 消息轮询
- **继承自**: `RightSidebar.tsx` BuddyPanel 的消息加载逻辑
- **触发**: CourseLayout mount + 15s setInterval
- **函数**: `fetchBuddyMessages(userId, syllabusId)` — `src/api/studyBuddyApi.ts`
- **API**: `GET /api/study_buddy/messages?user_id=N&syllabus_id=N`
- **状态**: `messages[]`, `unreadCount`
- **UI 结果**: 有新的非 user 消息时 FAB 红点数字 +1；最新一条主动消息（`source=proactive|event`）触发 BuddyPopupBubble 弹出

##### 24. BuddyPopupBubble 点击
- **触发**: onClick bubble body
- **行为**: `setBuddyOpen(true)` + `setBubbleVisible(false)`
- **UI 结果**: 气泡消失，FloatWindow 展开

##### 25. BuddyPopupBubble [关闭] 按钮
- **触发**: onClick X icon
- **行为**: `setBubbleVisible(false)` — FAB 红点保留不变
- **UI 结果**: 气泡消失

##### 26. BuddyPopupBubble 自动消失
- **触发**: setTimeout 5000ms（bubble visible 时启动）
- **行为**: `setBubbleVisible(false)` — FAB 红点保留不变
- **UI 结果**: 气泡消失

##### 27. BuddyFloatWindow [最小化] 按钮
- **触发**: onClick minimize icon
- **行为**: `setBuddyOpen(false)`
- **UI 结果**: FloatWindow 隐藏，FAB 保持（红点不变）

##### 28. BuddyFloatWindow [关闭] 按钮
- **触发**: onClick X icon
- **行为**: `setBuddyOpen(false)` — 同最小化行为

---

#### SubjectHome 页交互追踪 — 继承来源标注

##### 29. 页面加载
- **继承自**: `RightSidebar.tsx` FilesPage 的 `fetchResourceList()` + 新 video_search 端点
- **触发**: component mount
- **API (并行)**:
  a. `fetchResourceList(userId, syllabusId)` → `setResources(data.materials)` — 继承自 RightSidebar.FilesPage
  b. `apiUrl("/api/knowledge/video_search")` POST `{query: 从 syllabus.title 提取, max_results:6}` → `setVideos(data.videos)`
  c. `apiUrl("/api/syllabus_list")` POST `{user_id}` → 从返回列表找到当前 syllabusId 的项 → 提取该课程的 `subject_title`/`graph_names`/`status` 显示在页面标题区
- **UI 结果**: 课程资料区域（过滤 `resource_type=documents` 的资源）、AI 生成资源区域（其余类型）、视频区域。各区块先 skeleton 后数据

##### 30. 资源卡片点击（课程资料 — 知识文档）
- **继承自**: `RightSidebar.tsx` KBPage 的 `matched_sources[kind=knowledge_source]` → 文件下载逻辑
- **触发**: onClick 课程资料卡片
- **数据来源**: ① 课程资料卡片数据来自 `apiUrl("/api/syllabus_list")` POST 返回的 syllabus 元信息（`title`/`graph_names`）+ ② `apiUrl("/api/knowledge/search")` GET 返回的 `matched_sources[kind=knowledge_source]`（上传的知识文档）
- **行为**: 若 `matched_source` 有 `file_path` → `GET /api/file/download?file_id=X` 下载文件；若无 → 展示文件名和"该文件暂不可预览"提示
- **UI 结果**: 触发浏览器下载，或展示提示信息

##### 30b. 资源卡片点击（AI 生成资源 — mindmap/doc/quiz/code/ppt）
- **继承自**: `RightSidebar.tsx` FilesPage → `fetchResourceDetail()` → 打开预览
- **触发**: onClick AI 资源卡片
- **函数**: `fetchResourceDetail(userId, resourceId)` — `src/api/generativeApi.ts`
- **API**: `POST /api/generative_detail` `{user_id, resource_id}`
- **UI 结果**: 已有 `ResourcePreviewDrawer` 打开该资源（5 种类型完整预览：documents→Markdown, mindmap→Mermaid, quiz→QuizPreview, coding_practice→代码, ppt→PptViewer）

##### 31. 视频卡片点击
- **继承自**: 新端点，行为明确
- **触发**: onClick video card
- **行为**: `window.open(video.video_url, "_blank")`

---

#### SyllabusPage 交互追踪 — 继承来源标注

##### 32. 页面加载
- **继承自**: `RightSidebar.tsx` GanttPage 的 `ActivityGantt profile={p}` + `RightSidebar.tsx` SyllabusPage 的 `SyllabusTimeline weeks={...}`
- **触发**: component mount
- **API**: `fetchProfileDetail(userId, syllabusId)` — `src/api/learningProfileApi.ts` → `POST /api/learning_profile_detail` `{user_id, syllabus_id}`
- **状态**: `profile: LearningProfile | null`, `loading: boolean`
- **UI 结果**: 成功 → `ActivityGantt profile={profile}`, 三统计卡片数据从 `profile.signals` 字段提取（`active_days_7d`/`active_days_30d`/`avg_duration_minutes`）；失败 → "加载失败"空状态

##### 33. SyllabusTimeline 数据
- **继承自**: `RightSidebar.tsx` SyllabusPage 的 weeks 数据来源
- **数据来源**: 从 syllabus 后端获取 `period[]` 数组（通过 `apiUrl("/api/syllabus_detail")` 或 syllabus_list 中的 period 字段），映射为 `WeekItem[]`
- **UI 结果**: `SyllabusTimeline weeks={weeks}` 渲染教学进度条

---

#### LearningTreePage 交互追踪 — 继承来源标注

##### 34. 页面加载
- **继承自**: `LeftSidebar.tsx` KnowledgeTreeText 的数据来源 + `AdminSubjectDetail.tsx` 的 buddy_tree 加载
- **触发**: component mount
- **API (并行)**:
  a. `fetchStudyGraph(userId, syllabusId)` → `treeResponseToGraph()` → `setNodes/setEdges` + 从 `tree.nodes[].mastery.label` 计算 `weakNodes[]`，从 `tree.summary` 计算 `stats` — 继承自 LeftSidebar.KnowledgeTreeText 的 study_graph 数据
  b. `apiUrl("/api/study_buddy/tree")` GET `?user_id=N&syllabus_id=N` → `buddyRegionsToGraph()` → 合并 buddy_hint 节点 — 新端点
  c. `apiUrl("/api/study_buddy/memory")` GET `?user_id=N&syllabus_id=N` → `setMemoryTags(data.tags)` — 新端点
  d. `apiUrl("/api/study_buddy/synthesis")` GET `?user_id=N&syllabus_id=N` → `setSynthesis(data.synthesis)` — 已有端点
- **UI 结果**: D3 图谱（全部节点 + buddy_hint 紫色虚线节点含 glow filter）+ 右侧四面板填充

##### 35. 视图切换按钮
- **继承自**: `D3GraphViewer` 的 `layout` prop（"force" | "tree" | "dagre"），"学伴视角"为新增选项
- **触发**: onClick toggle button
- **行为**: `setView(mode)` → D3GraphViewer `layout={mode}`（"buddy" 时 `layout="force"`）
- **UI 结果**: 活跃按钮样式切换；图谱重渲染

##### 36. D3 图谱节点点击
- **继承自**: `D3GraphViewer` 的 `onNodeClick` prop（已有 hover 高亮邻居逻辑）
- **触发**: onClick node
- **行为**: 无 API — 节点数据已在本地
- **UI 结果**: 选中节点 + 邻居高亮

##### 37. [和智能体对话] CTA
- **触发**: onClick（ExploreGapList 内每个 explore 节点的 CTA）
- **行为**: `navigate(/learn/${syllabusId}/agent)`

---

#### AgentChatPanel 交互追踪 — 继承来源标注

##### 38. 消息发送
- **继承自**: 现有 `AgentChatPanel.tsx` 的完整 SSE 流式逻辑，不动
- **触发**: Enter / onClick Send
- **函数**: `useSSEStream().sendMessage(text, {user_id, syllabus_id})`
- **API**: `POST /api/total_agent/run` (SSE stream)
- **状态**: `agentStore.messages[]` 通过 `applyStreamEvent()` 增量更新
- **UI 结果**: `MessageBubble` 组件渲染（已有：Markdown + ToolCallTimeline + SubagentCard + ResourceCard 内联卡片）。保持不变。

##### 39. ProfileRadarPanel 展开/折叠
- **继承自**: `RightSidebar.tsx` RadarPage 的画像雷达数据 + ProfileRadarChart 组件
- **触发**: onClick panel header
- **行为**: `setOpen(!open)`
- **UI 结果**: 展开时渲染已有 `ProfileRadarChart` 组件；dimensions 来自 `useProfile()` 或 `fetchProfileDetail()` 的 `radar_dimensions` 字段

##### 40. KBSearchPanel 搜索
- **继承自**: `RightSidebar.tsx` KBPage 的完整搜索逻辑（`handleSearch` + `matched_sources` 分类 + 展开/折叠段落）
- **触发**: onClick [搜索] / Enter
- **函数**: `apiUrl("/api/knowledge/search?q=${encodeURIComponent(query)}&top_k=5&graph_name=...")` GET
- **API**: 同 RightSidebar.KBPage 的 `GET /api/knowledge/search?...`
- **状态**: `searching: boolean`, `results: KBSearchResult[]`, `matchedSources: KBMatchedSource[]`
- **UI 结果**: 搜索结果列表（继承自 KBPage 的 `renderParagraphBody` 逻辑：JSON 段落解析 + 纯文本展示）。`matched_sources` 分为 `generated_resource` 和 `knowledge_source` 两类展示，各有下载/预览链接

---

#### Galaxy 页交互追踪 — 继承来源标注

##### 41. 页面加载（FullGalaxy — `/galaxy`）
- **继承自**: `SubjectOverview.tsx` 的完整 galaxy 数据加载流程（逐行移植，不重写）
- **触发**: component mount
- **API (顺序)**:
  a. `apiUrl("/api/syllabus_list")` POST `{user_id}` → 提取 `graph_names[]` 去重 → `graphIds[]`
  b. `fetchGraphSnapshot(graphIds)` → `galaxyStore.setSnapshot(snapshot)` — 继承自 SubjectOverview 的 `fetchGraphSnapshot(graphIds).then(setSnapshot)`
  c. `fetchStudyGraph(userId)` → `treeResponseToGraph()` → `setStudyNodes()` — 继承自 SubjectOverview 的 study_graph 加载
  d. `useGraphMatch(studyNodes, snapshot.nodes)` → `{matchedNodeIds, nodeColors}` → 传入 `NebulaOverlay` — 继承自 SubjectOverview 的 `starLabels` + `nodeColors`
- **状态**: `galaxyStore` (snapshot, selectedNode, selectedDetail, hoveredNodeId, showEdges, layoutMode)
- **UI 结果**: `<KnowledgeGalaxy>` + `<NebulaOverlay>` + `<DetailPanel>` + `<GalaxyRotator>` + 银河/平面 toggle。与旧 SubjectOverview 相同的全部可视化能力。
- **轮询**: `useHeartbeat(userId, undefined, !!snapshot, handleHeartbeatChange)` — 继承自 SubjectOverview 的 heartbeat 逻辑，`changed.has('galaxy')` 时自动 `fetchGraphSnapshot` 刷新

##### 42. 页面加载（KnowledgeGalaxyPage — `/learn/:id/galaxy`）
- **继承自**: 同上 SubjectOverview 流程，`graphIds` 限定为当前 syllabus 的 `graph_names`
- **触发**: component mount
- **API**: 同 #41，`graphIds` 从当前课程提取
- **UI 结果**: 全部可视化组件嵌入 `<CourseLayout>` 的深色子窗口（`rounded-xl border border-white/10 bg-[#03040a]`）

##### 43. Galaxy 节点点击
- **继承自**: `SubjectOverview.tsx` 的 `handleSelectNode(nodeId)` — `selectNode(node)` + `fetchNodeDetail(nodeId, snapshot).then(setSelectedDetail)`
- **触发**: onClick 3D 节点 (KnowledgeGalaxy `onSelectNode`)
- **函数**: `galaxyStore.selectNode(node)` → `fetchNodeDetail(nodeId, snapshot)` → `galaxyStore.setSelectedDetail(detail)`
- **UI 结果**: DetailPanel 滑入（标题、`.kg-reason` 理由框、`.kg-evidence` 证据段含 `neighbors` 按钮、`.kg-neighbors` 邻居节点列表）。继承自 DetailPanel.tsx 的全部渲染逻辑。

##### 44. Galaxy 节点 hover
- **继承自**: `SubjectOverview.tsx` → `galaxyStore.setHoveredNode(nodeId)`
- **触发**: onPointerOver 3D 节点 (KnowledgeGalaxy `onHoverNode`)
- **行为**: `galaxyStore.setHoveredNode(nodeId)`
- **UI 结果**: 节点发光

##### 45. 银河/平面视图切换
- **继承自**: `SubjectOverview.tsx` → `galaxyStore.setLayoutMode(mode)`
- **触发**: onClick `.kg-segmented` toggle button
- **行为**: `galaxyStore.setLayoutMode(mode)`

##### 46. [终身学习图谱] toggle（KnowledgeGalaxyPage 底部 bar）
- **触发**: onClick
- **行为**: `navigate("/galaxy")`

##### 47. [返回首页] 按钮（FullGalaxy 顶栏）
- **触发**: onClick
- **行为**: `navigate("/")`

---

#### QuizAttempts 页交互追踪 — 继承来源标注

##### 48. 页面加载
- **继承自**: `ResourcePreviewDrawer.tsx` QuizPreview 的 quiz 加载 + 提交逻辑
- **触发**: component mount
- **API (两步)**:
  ① `fetchResourceList(userId, syllabusId, "quiz")` → 获取该课程所有 quiz 资源的 `resource_id[]` 列表
  ② 对每个 `resource_id` 调 `apiUrl("/api/quiz_attempts")` GET `?user_id=N&resource_id=X`（per-resource 端点，需迭代调用）
- **状态**: `attempts: QuizAttempt[]`（有 attempt → `{resource_id, score, correct_count, total_questions, weak_topics, attempted_at, status:"completed"}`；无 attempt → `{resource_id, status:"pending"}`）
- **UI 结果**: 列表渲染。已完成卡片显示得分/正确数/薄弱点标签 + "已完成"绿色 badge；未作答卡片显示灰色 "待完成" badge

##### 49. 测验卡片点击
- **继承自**: `ResourcePreviewDrawer.tsx` QuizPreview 组件的完整交互（答题 + 提交 + 画像同步 + "再试一次"）
- **触发**: onClick quiz card
- **函数**: `fetchResourceDetail(userId, resourceId)` → 获取 quiz 完整内容（`content.questions[]`）
- **UI 结果**: 已有 `ResourcePreviewDrawer` 以 quiz 模式打开。显示题目列表（继承自 QuizPreview：选项按钮、提交、结果分数、"反馈给 Agent"按钮、"再试一次"按钮——通过清除 `localStorage` 中的 `quiz_done_${resource_id}` key 重置）。`submitQuizAttempt()` 写入后端。`submitAndRefresh()` 更新画像。

---

#### Admin 页交互追踪 — 继承来源标注

##### 50. AdminDashboard 加载（`/admin/subject/:id` index）
- **继承自**: `AdminSubjectDetail.tsx` 的知识填充面板 + 大纲编辑面板（直接提取，不重写）
- **触发**: component mount
- **API**: `apiUrl("/api/syllabus_list")` POST `{user_id}` → 从返回列表中找到 syllabusId 匹配项 → `setSyllabusMeta({syllabus_id, title, graph_id, graph_name, status})`
- **UI 结果**: 知识填充面板（文件 `<input type="file">` + [创建填充任务] 按钮）+ 大纲编辑面板（`<textarea>` JSON editor + [保存大纲] 按钮）。继承自 AdminSubjectDetail 的 toolPanel 渲染逻辑。

##### 51. [创建填充任务] 按钮
- **继承自**: `AdminSubjectDetail.tsx` 的 `handleCreateKnowledgeJob()` — 筛选文件 + `apiUrl("/api/job_graph_create")` POST
- **触发**: onClick
- **函数**: `apiUrl("/api/job_graph_create")` POST `{graph_id, files: [...], ...}`
- **状态**: `loading: boolean`
- **UI 结果**: 按钮 loading 态 → 成功提示

##### 52. [保存大纲] 按钮
- **继承自**: `AdminSubjectDetail.tsx` 的 `handleSaveSyllabus()` — 根据 status 选择 `syllabus_update_draft` 或 `syllabus_update`
- **触发**: onClick
- **函数**: `apiUrl("/api/syllabus_update_draft")` POST（草稿）或 `apiUrl("/api/syllabus_update")` POST（已发布）
- **状态**: `loading: boolean`
- **UI 结果**: `setStatusMsg("大纲已保存。")`

##### 53. AdminStudents 加载（`/admin/subject/:id/students`）
- **继承自**: `AdminSubjectDetail.tsx` 的学生数据加载循环（`admin_api.py` 返回的 `{students: [{study_graph, buddy_tree, profile_summary}]}`）
- **触发**: component mount
- **API**: `apiUrl("/api/admin/...")` GET `?syllabus_id=N` — 同原 AdminSubjectDetail 的 admin API
- **状态**: `students: StudentProgress[]`, `total: number`
- **UI 结果**: 学生卡片 grid。每张卡片 = D3 图谱小图（`treeResponseToGraph(study_graph)` → `D3GraphViewer`）+ 画像摘要（`profile_summary` 字段：综合/活跃/均时/术语/事件/答题）+ 学伴树（`buddyRegionsToGraph(buddy_tree)` → `D3GraphViewer`）

##### 54. AdminGraph 加载（`/admin/subject/:id/graph`）
- **继承自**: `SubjectOverview.tsx` 的 galaxy 加载逻辑 + `AdminSubjectDetail.tsx` 的 graph_id 获取
- **触发**: component mount
- **API**: 从 syllabusMeta 获取 `graph_id` → `fetchGraphSnapshot([graphId])`
- **UI 结果**: 知识图谱视图（D3 或 Galaxy，取决于数据）

##### 55. AdminCreateSubjectModal — 完整 wizard
- **继承自**: `CreateSubject.tsx` 的 Step 流程（Step 1 初始化图谱 → Step 2 上传日历 → Step 3 编辑大纲 → Step 4 填充知识 → Step 5 增强 → Step 6 发布）。Modal 模式精简为 3 步。
- **触发**: Dashboard [创建新学科] onClick → `setCreateModalOpen(true)`
- **Step 1→2**: `apiUrl("/api/graph/list")` GET → `setGraphs(data.graphs)`
- **Step 3 提交（两步 API 顺序调用）**:
  ① `apiUrl("/api/file_upload_calendar")` POST `{file_name, file_bytes, title, user_id}` → 返回 `{syllabus_id}`
  ② `apiUrl("/api/syllabus_build_draft")` POST `{syllabus_id, graph_id, initial_prompt}` → 生成草稿
- **UI 结果**: Modal 关闭 → `navigate(/admin/subject/${syllabusId})`
