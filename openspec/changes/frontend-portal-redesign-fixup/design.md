## Context

`frontend-portal-redesign` 首轮实施创建了 28 个新文件、修改了 3 个文件，TypeScript 编译通过且 Vite build 成功。但在对照 15 个 SVG 设计稿 和已有代码库的 API 层进行探索审计时，发现三类结构性差距：

1. **路由不完整**: `AdminSubjectDetail` 原为单体页面（含知识填充/大纲编辑/学生进度/图谱四个功能面板），但设计稿 09-12 要求拆分为侧栏导航的三个独立子路由
2. **数据流绕过已有层**: 新页面直接用 `fetch("/api/...")` 硬编码，未使用 `src/api/*.ts` 中的类型化 API client 函数，也未接入 Zustand stores（`galaxyStore`, `agentStore`）和 `useHeartbeat` 轮询
3. **视觉偏离**: 卡片尺寸/布局/投影、顶栏面包屑、搜索框、D3 覆盖层标注等大量元素未对齐 SVG 像素级设计

本 fixup 不改变 `frontend-portal-redesign` design.md 中已有的路由架构、组件树、主题策略等高层决策。仅在实现层面补齐合规性。

## Goals / Non-Goals

**Goals:**
- 将 `/admin/:id` 拆分为三个子路由，每个有独立视图和一致的侧栏导航
- 所有新页面统一使用 `src/api/` 模块和 `apiUrl()` 包装器
- Galaxy 页面复原 `galaxyStore` + `useGraphMatch` + `useHeartbeat` 集成
- 逐页对照 SVG 设计稿 补齐缺失视觉元素：顶栏渐变、搜索框、卡片细节、标签、分隔线、覆盖层标注、面包屑
- 消除 `weeks={[]}` / `profile={null}` 等空数据传递

**Non-Goals:**
- 不新增后端端点
- 不修改 `frontend-portal-redesign` design.md 中已确定的路由拓扑和组件树
- 不引入新的 npm 依赖
- 不改变数据模型

## Decisions

### Decision 1: Admin 子路由拆分方式

```
当前 AdminSubjectDetail（单体，toolPanel 切换）    新架构
──────────────────────────────────────────        ─────────────────────────
/admin/subject/:syllabusId                         /admin/subject/:syllabusId
  ├─ toolPanel="knowledge" (填充知识)                ├─ index → AdminDashboard (学科总览)
  ├─ toolPanel="syllabus"  (编辑大纲)                ├─ students → AdminStudents
  ├─ students grid         (学生卡片)                └─ graph → AdminGraph
  └─ buddy trees           (学伴树)
```

**方法**: 创建 `AdminLayout` 组件（侧栏 + Outlet），三个子页面各从原 `AdminSubjectDetail` 提取对应逻辑。原 `AdminSubjectDetail` 在迁移完成后删除。

**备选方案**: 保持单页 + tab 切换——被否决，因为设计稿要求独立路由供深层链接。

### Decision 2: API 接入策略

所有新页面遵循已有代码库的两层模式：
```
组件 → src/api/<module>.ts → apiUrl() → /api/...
       (类型化函数)          (BASE URL包装)
```

具体映射：
| 新页面 | 当前（硬编码） | 改为 |
|--------|-------------|------|
| Dashboard | `fetch("/api/syllabus_list", ...)` | 已有 `apiUrl()` + POST body |
| Dashboard | `fetch("/api/knowledge/search", ...)` | 同上 |
| Dashboard | `fetch("/api/knowledge/github_search", ...)` | 同上 |
| Dashboard | 裸 `fetchStudyGraph` | 已有（`src/api/studyGraphApi.ts`） |
| CourseLayout | `fetch("/api/syllabus_list", ...)` | `apiUrl()` |
| CourseLayout | `fetch("/api/study_buddy/messages", ...)` | `fetchBuddyMessages()` |
| SubjectHome | `fetch("/api/knowledge/video_search", ...)` | `apiUrl()` |
| SyllabusPage | `weeks={[]}`, `profile={null}` | `fetchProfileDetail()` → 真实数据 |
| LearningTreePage | 裸 `fetch("/api/study_buddy/tree", ...)` | `apiUrl()` |
| KnowledgeGalaxyPage | 空 `snapshot={{nodes:[],edges:[]}}` | `fetchGraphSnapshot()` |
| FullGalaxy | 空 `snapshot` | `fetchGraphSnapshot()` + `galaxyStore` |
| QuizAttempts | `fetch("/api/generative_list", ...)` | `fetchResourceList()` |
| AgentChatPanel | (已保留原逻辑，本次不动) | — |

### Decision 3: SVG 视觉对齐方法

SVG 设计稿 的 `filter="url(#cs)"` / `filter="url(#ts)"` 对应 Tailwind `shadow-sm` / `shadow-md`。
SVG 中的精确像素尺寸（384×266 课程卡片、296×160 资源卡片、252×135 文档卡片）作为 Tailwind 的 `w-[384px]` 等任意值设置。

逐页对照策略：
1. 提取 SVG 中的布局数值（x/y/width/height）、颜色、字号、圆角
2. 映射到 Tailwind class 或 `style` 内联
3. 保持已有组件结构，增量补齐缺失元素

### Decision 4: Galaxy 页数据流恢复

```
KnowledgeGalaxyPage / FullGalaxy
  → galaxyStore.setSnapshot()
    → fetchGraphSnapshot(graphIds)      // 已有 API client
  → useGraphMatch(studyNodes, snapshot.nodes)  // 已有 hook
    → NebulaOverlay(matchedNodeIds, nodeColors) // 已有组件
  → useHeartbeat(userId, undefined, !!snapshot) // 已有 hook
    → 数据变更时自动 refresh
```

三个已有模块复原即可，无需新建。

## Risks / Trade-offs

- **AdminSubjectDetail 拆分风险**: 原组件较复杂（~400 行），拆分时需仔细提取共享逻辑 → 创建 `useAdminSyllabus` hook 管理共享状态
- **Galaxy 数据可能为空**: 部分课程无图谱 → 保持已有空状态 UI（`kg-loading` class）
- **SVG 对齐工时大**: 15 个设计文件 逐元素对齐 → 按页优先级分轮次，Dashboard → CourseHome → Tree → Galaxy → Agent → Admin → Quiz

## Open Questions

- Admin 子路由是嵌套在 `/admin/subject/:syllabusId/` 下还是 `/admin/:syllabusId/` 下？——建议保持现有 `/admin/subject/:syllabusId/` 前缀，子路由追加以免破坏已有书签
- 搜索框是否需要真实功能还是视觉占位？——前期视觉占位即可，后期可接入 `/api/knowledge/search`
