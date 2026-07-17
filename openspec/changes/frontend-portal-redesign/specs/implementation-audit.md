# Implementation Audit: Frontend Portal Redesign

最终实施前自查。覆盖新增常量、文件范围、数据流、函数签名、测试用例。

---

## 0. 新增常量 / 表结构

### 0.1 D3GraphViewer 新增分组

```
文件: src/components/graph/D3GraphViewer.tsx
常量: GROUP_COLORS
新增:
  buddy_hint: { fill: "#ede9fe", stroke: "#7c3aed", halo: "rgba(124,58,237,0.20)" }
```

节点渲染时 `group === "buddy_hint"` → 使用虚线 stroke-dasharray="3,3", 较小半径 (12px)。

### 0.2 Buddy 新增消息类型

```
文件: tasks/study_buddy/contracts.py  (新增常量)
常量: BUDDY_MESSAGE_SOURCE_SYNTHESIS = "synthesis"
```

存储: `buddy_messages.jsonl` 追加行 `{from: "proactive", source: "synthesis", text: "...", ...}`

### 0.3 后端新增端点

| 端点 | 方法 | 入参 | 出参 |
|------|------|------|------|
| `/api/knowledge/video_search` | POST | `{query, topic?, max_results:3}` | `{videos: [{title, thumbnail_url, video_url, duration, source, author, play_count?, description?}]}` |
| `/api/knowledge/github_search` | POST | `{query, topic?, max_results:6, min_stars?:50}` | `{repos: [{full_name, description, html_url, stars, language, license}]}` |
| `/api/file_upload_calendar` | POST | `{file_name, file_bytes, title?, user_id?}` — 已有端点, 新增可选 `title` 参数 | `{file: {file_id}, syllabus: {syllabus_id}}` |

### 0.4 无新增 DB 表

所有新端点复用现有表结构 (`Syllabus`, `Graph`, `RecommendationSnapshot`)。Synthesis 消息复用 `buddy_messages.jsonl`。不需要 migration。

---

## 1. 影响文件范围

### 1.1 后端 (新增/修改)

| 文件 | 操作 | 说明 |
|------|------|------|
| `blueprint/learning_api.py` | 修改 | 新增 `video_search` 路由 |
| `blueprint/knowledge_build_api.py` | 修改 | 新增 `github_search` 路由 |
| `blueprint/file_transmit_api.py` | 修改 | `file_upload_calendar` 新增可选 `title` 参数 |
| `tasks/study_buddy/buddy_agent.py` | 修改 | 新增 `synthesis_proactive_message()` 函数 |
| `tasks/study_buddy/contracts.py` | 修改 | 新增 `BUDDY_MESSAGE_SOURCE_SYNTHESIS` |
| `tasks/study_buddy_task.py` | 修改 | 暴露 synthesis 入口 |
| `blueprint/study_buddy_api.py` | 修改 | 新增 `GET /api/study_buddy/synthesis?user_id=N&syllabus_id=N` |

### 1.2 前端 (新建)

| 文件 | 说明 |
|------|------|
| `src/pages/Dashboard.tsx` | 门户页 |
| `src/components/dashboard/DashboardHeader.tsx` | 顶栏 |
| `src/components/dashboard/CourseCardGrid.tsx` | 课程卡片 |
| `src/components/dashboard/RecentResources.tsx` | 最近资源 (296×160 卡片) |
| `src/components/dashboard/RecommendedExploration.tsx` | 推荐探索 |
| `src/components/dashboard/GitHubProjects.tsx` | 实训项目 |
| `src/components/dashboard/LifelongGraph.tsx` | 终身图谱 |
| `src/components/dashboard/GalaxyReveal.tsx` | 银河揭示 |
| `src/layouts/CourseLayout.tsx` | 课程布局 |
| `src/layouts/CourseSidebar.tsx` | 课程侧栏 |
| `src/pages/SubjectHome.tsx` | 学科首页 |
| `src/components/subject/CourseMaterials.tsx` | 课程资料 |
| `src/components/subject/GeneratedResources.tsx` | AI 生成资源 |
| `src/components/subject/VideoGrid.tsx` | 视频网格 |
| `src/pages/SyllabusPage.tsx` | 大纲页 |
| `src/pages/LearningTreePage.tsx` | 学习成长图谱 |
| `src/components/tree/WeaknessAnalysis.tsx` | 薄弱点分析 |
| `src/components/tree/ExploreGapList.tsx` | 待探索列表 |
| `src/components/tree/BuddyObservations.tsx` | 学伴观察 |
| `src/components/tree/BuddyMemoryCloud.tsx` | 学伴记忆云 |
| `src/components/tree/BuddySuggestion.tsx` | 学伴综合建议 |
| `src/components/buddy/BuddyFAB.tsx` | 悬浮按钮 |
| `src/components/buddy/BuddyFloatWindow.tsx` | 悬浮聊天窗 |
| `src/components/buddy/BuddyPopupBubble.tsx` | 自动弹出气泡 |
| `src/components/thumbnails/CourseThumbnail.tsx` | 课程封面 |
| `src/components/thumbnails/DocThumbnail.tsx` | 文档缩略图 |
| `src/components/admin/AdminCreateSubjectModal.tsx` | 创建学科向导 |
| `src/pages/QuizAttempts.tsx` | 测验记录 |
| `src/pages/FullGalaxy.tsx` | 终身银河 (复用 SubjectOverview) |

### 1.3 前端 (修改)

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/App.tsx` | 重写路由 | 新路由架构 |
| `src/components/graph/D3GraphViewer.tsx` | 新增分组 | GROUP_COLORS.buddy_hint |
| `src/components/chat/AgentChatPanel.tsx` | 重构 | 精简为 2 栏 |
| `src/pages/SubjectOverview.tsx` | 重构 | → FullGalaxy，去侧栏 |
| `src/layouts/AgentLayout.tsx` | 重构 | → CourseLayout |
| `src/pages/AdminSubjectDetail.tsx` | 主题改 | dark → light |
| `src/styles/lianjue.css` | 新增类 | light theme 类 |

### 1.4 前端 (移除)

| 文件 | 说明 |
|------|------|
| `src/layouts/RightSidebar.tsx` | 6 tab 拆散到各子页面 |
| `src/pages/CreateSubject.tsx` | 替换为 AdminCreateSubjectModal |

---

## 2. 数据流

### 2.1 Dashboard 页面

```
Dashboard 加载
  ├─ POST /api/syllabus_list {user_id}
  │   → syllabuses[{syllabus_id, title, status, graph_names}]
  │   → CourseCardGrid 渲染
  │
  ├─ GET /api/study_graph/detail?user_id=N  (no syllabus_id → lifelong)
  │   → tree + sibling_trees
  │   → LifelongGraph (D3 force)
  │
  ├─ POST /api/generative_list {user_id}  (跨课程, 无 syllabus_id)
  │   → materials[] 按 created_at 倒序取 4
  │   → RecentResources (296×160 cards, DocThumbnail by resource_type)
  │
  ├─ GET /api/study_graph/features?user_id=N&syllabus_id=N  (取首个课程的 weak_topics)
  │   → weak_topics → query 拼接
  │   → POST /api/knowledge/search?q=<weak_topics>&top_k=2
  │   → RecommendedExploration (296×160 cards, match% + reason)
  │
  └─ POST /api/knowledge/github_search {query: course_titles, topic, max_results:3}
      → GitHubProjects (296×160 cards)
```

### 2.2 LearningTreePage (/learn/:id/tree)

```
LearningTreePage 加载
  ├─ GET /api/study_graph/detail?user_id=N&syllabus_id=N
  │   → tree.nodes[{node_id, title, mastery.{label,score}, summary}]
  │   → tree.edges[{source, target, edge_type}]
  │   → D3GraphViewer(layout="force") 渲染图谱
  │
  ├─ BuddyTree (文件系统: study_buddy/user_{id}/syllabus_{id}/tree.json)
  │   → regions: {trunk:[], learned:[], explore:[]}
  │   → nodes[{title, mastery, summary, buddy_notes[{note,created_at,mastery_hint}]}]
  │   → explore nodes → 标记 group="buddy_hint", 合并入 D3 数据
  │   → WeaknessAnalysis: 从 study_graph weak_topics + buddy_tree nodes 交叉查
  │   → ExploreGapList: regions.explore → 节点标题+摘要+关联主干(edges 反查)
  │
  ├─ BuddyMemory (buddy_memory.jsonl)
  │   → tags[{tag, created_at}]
  │   → BuddyMemoryCloud 渲染
  │
  ├─ BuddyMessages (buddy_messages.jsonl)
  │   → 最新一条 source="synthesis" 消息
  │   → BuddySuggestion 渲染
  │   → 如无 synthesis 或过期 → 触发 GET /api/study_buddy/synthesis
  │
  └─ POST /api/learning_profile_detail {user_id, syllabus_id?}
      → profile: {overall_score, dropout_risk, signals.active_days_7d, learning_records.length}
      → Stats header 渲染
```

### 2.3 AgentChatPanel (/learn/:id/agent)

```
AgentChatPanel 加载
  ├─ SSE: run_total_agent (现有, 不变)
  │   → 消息流 + tool_call timeline
  │   → inline recommendation card (复用 MiniGraphPanel 逻辑)
  │
  ├─ MiniGraphPanel → 推荐网络 (现有, 不变)
  │   → candidates[] → 编号药片选择器
  │   → D3GraphViewer + highlightPath + dimNodeIds
  │   → "确认路径" → POST /api/recommendations/:id/accept
  │   → "全屏" → GraphModal + CandidatePathSelector (React Flow DAG)
  │
  ├─ 学习计划 (现有, 不变)
  ├─ 学习画像 (折叠, 现有)
  ├─ KB搜索 (折叠, 现有)
  │
  ├─ BuddyFAB (右下角, 通知红点)
  │   → 点击 → BuddyFloatWindow (340×420, 固定右下)
  │   → 新消息到达 → BuddyPopupBubble (5s 自动消失)
  │   → GET/POST /api/study_buddy/messages, /api/study_buddy/chat
  │
  └─ AgentStatsBar (顶栏 stats: 掌握度/活跃/薄弱/当前步骤)
```

### 2.4 AdminCreateSubjectModal

```
Modal 打开 (Dashboard "+ 创建新学科")
  ├─ GET /api/graph/list
  │   → graphs[{graph_id, graphId}]
  │   → 图谱选择卡片
  │
  ├─ POST /api/job_graph_create {graph_name}  (可选, 自行创建图谱)
  │
  └─ 提交 (两步):
      ① POST /api/file_upload_calendar {file_name, file_bytes, title, user_id}
         → 保存日历文件 → create_syllabus(title, file_id) → 返回 {file_id, syllabus_id}
      ② POST /api/syllabus_build_draft {syllabus_id, graph_id, initial_prompt}
         → pdf_to_md job → LLM 生成 period → 持久化草稿 → 内部 create_syllabus_graph
         → 跳转 /admin/subject/:syllabus_id
```

---

## 3. 关键函数签名

### 3.1 后端新增

```python
# tasks/study_buddy/buddy_agent.py

def synthesis_proactive_message(
    user_id: int,
    syllabus_id: int,
    plan: dict | None = None,
    study_graph_features: dict | None = None,
) -> str | None:
    """生成学伴综合学习建议。
    
    内部逻辑:
    1. build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    2. load_memory_tags(user_id, syllabus_id)
    3. 构建 prompt: explore 节点 + weak_topics + buddy_notes
    4. agent.run_sync(prompt) → reply
    5. 持久化到 buddy_messages.jsonl (source="synthesis")
    6. 返回 reply[:500] 或 None
    """
```

```python
# blueprint/file_transmit_api.py — 已有端点, 新增可选 title 参数

@bp.route('/file_upload_calendar', methods=['POST'])
@require_operator
def upload_calendar():
    """上传教学日历文件并创建 Syllabus 记录。

    输入: {file_name, file_bytes (base64), upload_time?, user_id?, title?}  ← title 为新增可选参数
    内部:
    1. 保存日历文件 → file_id + edu_calendar_path
    2. create_syllabus(edu_calendar_path, file_id, title=title)  ← 传入 title
    3. 可选绑定 user
    返回: {file: {file_id}, syllabus: {syllabus_id}}
    """

# 前端 wizard "创建学科"按钮调用流程:
#   ① POST /api/file_upload_calendar {file_name, file_bytes, title}
#   ② POST /api/syllabus_build_draft {syllabus_id, graph_id, initial_prompt}
```

### 3.2 前端新增

```typescript
// src/components/buddy/BuddyFAB.tsx
interface BuddyFABProps {
  unreadCount: number;
  onClick: () => void;           // → open BuddyFloatWindow
  latestMessage?: BuddyMessage;  // → BuddyPopupBubble 内容
}

// src/components/buddy/BuddyFloatWindow.tsx
interface BuddyFloatWindowProps {
  open: boolean;
  onClose: () => void;
  messages: BuddyMessage[];
  onSend: (text: string) => void;
  memoryTagsWritten: MemoryTag[];
}

// src/components/buddy/BuddyPopupBubble.tsx
interface BuddyPopupBubbleProps {
  message: BuddyMessage;
  visible: boolean;
  onDismiss: () => void;
  onClick: () => void;           // → open BuddyFloatWindow
  autoDismissMs: number;         // 5000
}

// src/components/thumbnails/CourseThumbnail.tsx
function generateCourseBanner(title: string): {
  bgColor: string;               // PALETTE[djb2(title) % 8]
  geometry: "diagonal" | "stacked" | "ripple" | "triangles";
  textColor: string;             // white
}  // → 渲染 360×136 SVG

// src/components/thumbnails/DocThumbnail.tsx
function DocThumbnail({ type, size }: {
  type: "documents" | "mindmap" | "quiz" | "coding_practice" | "ppt";
  size?: { width: number; height: number };  // default 296×100
})  // → 渲染对应类型 SVG 缩略图
```

### 3.3 D3GraphViewer 修改

```typescript
// src/components/graph/D3GraphViewer.tsx
// 修改: GROUP_COLORS 新增
const GROUP_COLORS: Record<string, { fill: string; stroke: string; halo: string }> = {
  // ... existing groups ...
  buddy_hint: { fill: "#ede9fe", stroke: "#7c3aed", halo: "rgba(124,58,237,0.20)" },
};

// 修改: nodeRadius() 感知 buddy_hint
const nodeRadius = (n: GraphNode) => {
  if (n.group === "buddy_hint") return 12;
  return n.radius ?? (8 + Math.min(edgeCount, 10) * 2);
};

// 修改: buddy_hint 节点渲染虚线 stroke
// 在 nodeSel 的 circle 渲染中:
//   if (d.group === "buddy_hint") { stroke-dasharray: "3,3" }
```

---

## 4. 测试用例

### 4.1 后端

```
test_video_search_returns_normalized_results
  - mock B站 API → 验证 {videos: [{title, url, thumbnail, duration, source}]}
  - 8s timeout → 返回 partial/empty, 不崩溃

test_github_search_filters_by_stars
  - query="big data", min_stars=50 → 验证 repos 按 stars 倒序
  - 空结果 → {repos: [], success: true}

test_syllabus_create_and_draft
  - POST {title:"测试学科", weeks:16, graph_id:1}
  - 验证 syllabus 记录创建, status="draft"
  - 验证 build_draft 被调用, 返回 syllabus_id

test_buddy_synthesis_message_persisted
  - 调用 synthesis_proactive_message(1, 18)
  - 验证 buddy_messages.jsonl 新增一条 source="synthesis"
  - 验证 reply 非空, ≤500 chars

test_buddy_synthesis_cache_skip
  - 首次调用 → 生成 synthesis
  - 5分钟内再次调用 → 返回已有 synthesis, 不调 LLM
```

### 4.2 前端

```
test_course_thumbnail_deterministic
  - djb2("大数据概论") → 固定 hash → 固定颜色+几何
  - 验证两次调用返回相同 SVG

test_doc_thumbnail_by_type
  - DocThumbnail({type:"mindmap"}) → 包含绿色 (#059669) + 节点连线
  - DocThumbnail({type:"quiz"}) → 包含琥珀色 (#d97706) + 选项框

test_buddy_fab_unread_badge
  - unreadCount=3 → 红点显示 "3"
  - unreadCount=0 → 红点隐藏

test_buddy_popup_bubble_auto_dismiss
  - visible=true, autoDismissMs=5000
  - 5s 后 visible → false
  - 手动点击关闭 → 立即 visible=false

test_learning_tree_buddy_hint_nodes
  - study_graph nodes 5个 + buddy_tree explore nodes 3个
  - 合并后 graph nodes=8, buddy_hint 节点 group="buddy_hint", stroke-dasharray

test_graph_modal_candidate_selector
  - candidates=[{path:["n1","n2"], rank:1, selected:true}, {path:["n3"], rank:2}]
  - 路径 1 紫色选中边框, 路径 2 灰色
  - 点击路径 2 → onSelect({path:["n3"], rank:2})
```

---

## 5. 实施就绪检查

| 检查项 | 状态 |
|--------|------|
| 所有 SVG mockup 已完成 (14 个文件) | ✅ |
| 所有 API 口岸已确认 (4 新 + 全部复用) | ✅ |
| D3GraphViewer 能力映射已写入 spec | ✅ |
| GraphModal + CandidatePathSelector 模式已确认 | ✅ |
| 推荐路径网络数据结构已验证 (RecommendationSnapshot DB) | ✅ |
| Galaxy 复用/去除策略已明确 | ✅ |
| Buddy 悬浮窗 + 自动气泡 spec 已完整 (6 个 Scenario) | ✅ |
| 学伴 synthesis 消息 spec 已完整 (2 个 Scenario + 缓存) | ✅ |
| 缩略图配色已最终确定 (5 种类型) | ✅ |
| Tasks.md 共 82 项, 覆盖 15 个章节 | ✅ |
| 移动端适配延后 (不在本轮) | ✅ |
| enhance-buddy-tree-mockups 已归档合并 | ✅ |

**结论: 已达到 apply 条件。** 所有缺口已填补, 数据口岸一一对应, 无阻塞项。
