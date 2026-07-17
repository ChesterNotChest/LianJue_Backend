## Why

`frontend-portal-redesign` 首轮实施完成 79/82 任务，但探索阶段暴露三类严重差距：(1) 3 条 admin 子路由缺失，设计稿要求的侧栏导航子页未独立拆分；(2) 新页面大量使用裸 `fetch()` 替代已有 API client 层，未接入 Zustand store 和 heartbeat 轮询，数据流硬编码；(3) SVG 设计稿（15 个文件）中的顶栏、卡片、标注覆盖层、搜索控件等大量视觉元素被简化或缺失，与设计稿保真度差距大。

需在本轮集中补齐，使前端实现达到与 `01-dashboard.svg` ~ `12-admin-graph.svg` 一致的交互和视觉标准。

## What Changes

### 路由补齐
- 将 `AdminSubjectDetail` 拆分为含侧栏导航的三个子路由：`/admin/:id`（学科总览）、`/admin/:id/students`（学生进度）、`/admin/:id/graph`（知识图谱），统一 `← 返回首页` 面包屑

### API 层接入（消除硬编码）
- 所有新页面统一使用 `src/api/` 模块中的 API client 函数（`fetchStudyGraph`, `fetchResourceList`, `fetchProfileDetail`, `fetchBuddyMessages` 等），替换裸 `fetch()`
- Galaxy 页面接入 `galaxyStore` + `useGraphMatch` + `useHeartbeat`，恢复学习进度叠加到银河节点的 NebulaOverlay 效果
- Buddy 组件接入 `studyBuddyApi` 模块，不再绕过 API client 层
- SyllabusPage 通过 `fetchProfileDetail` 加载真实数据，替换 `weeks={[]}` / `profile={null}`

### SVG 设计稿视觉对齐（逐页）
- Dashboard：紫色渐变 Header、搜索框、课程卡片细粒度统计、草稿虚线边框态、资源卡片匹配度标签、刷新按钮
- 学科首页：文档卡片的折角 SVG 细节、AI 资源类型色顶边、视频网格 SVG 视觉规格
- 学习成长图谱：D3 图上的"当前步骤"浮动标签、"薄弱集群 · N 节点"虚线框标注、三级面包屑、Stats bar 分隔竖线布局
- Agent 页：BuddyFAB 悬浮窗的精确尺寸/动画、自动弹出气泡的 SVG 对齐
- 所有页面：统一顶栏面包屑 `联觉 LianJue / 课程名 / 子页名` 格式、卡片 `filter="url(#cs)"` / `filter="url(#ts)"` 投影效果对应 Tailwind shadow

## Capabilities

### New Capabilities
- `admin-subroutes`: `/admin/:id` 拆分为学科总览/学生进度/知识图谱三个子路由，各含侧栏导航和面包屑
- `api-integration`: 所有新页面统一接入 `src/api/` 模块和 Zustand stores，消除裸 fetch
- `svg-visual-alignment`: 逐页对照 15 个 SVG 设计稿 补齐缺失视觉元素（顶栏、搜索框、卡片细节、标注覆盖层、面包屑）

### Modified Capabilities
<!-- No existing spec modifications needed — all changes are implementation-level fixups within the already-approved design -->

## Impact

- **路由**: `src/App.tsx` 新增 3 条 admin 子路由；`AdminSubjectDetail` 拆分为 3 个视图
- **API 层**: `Dashboard`, `CourseLayout`, `SubjectHome`, `SyllabusPage`, `LearningTreePage`, `KnowledgeGalaxyPage`, `FullGalaxy`, `QuizAttempts` 全部改为使用 `src/api/` 模块
- **Store 接入**: Galaxy 页面接入 `galaxyStore` + `useHeartbeat`；Buddy 组件接入 `studyBuddyApi`
- **视觉**: 15+ 个组件按 SVG 设计稿 逐元素对齐（卡片布局、投影、间距、色标、标注覆盖层）
- **回归风险**: 低——已有 API client 层和 stores 接口稳定，仅改变新页面的数据获取方式
