# Resource Card Click

SubjectHome 中的课程资料卡片和 AI 生成资源卡片添加点击跳转。

## 影响文件

- `src/components/subject/CourseMaterials.tsx`
- `src/components/subject/GeneratedResources.tsx`

## Requirements

### GeneratedResources

| 需求 | 说明 |
|------|------|
| 卡片从 `<div>` 改为 `<button>` (或 `div onClick`) | cursor-pointer, hover:shadow-md, hover:border-accent/30 |
| onClick | `store.openResource(authStore.student.userId, r.resource_id)` |
| resource_id 来源 | `ResourceSummary.resource_id` (来自 `/api/generative_list`) |
| ResourcePreviewDrawer 自动打开 | store.openResource 内部调用 `fetchResourceDetail`  → 设置 drawerResource → CourseLayout 中 Drawer 自动渲染 |

### CourseMaterials

| 需求 | 说明 |
|------|------|
| 文件类型判断 | 从 path/filename 后缀推断：`.pdf` → PDF 预览，`.md`/`.txt` → 文本预览，`.pptx`/`.zip` 等 → 直接下载 |
| PDF 预览 | `store.openFilePreview(url, title)` → `<FilePreviewModal>` 中 `<iframe src={url}>` 浏览器原生 PDF 查看器 |
| 文本预览 | `<FilePreviewModal>` 中 `<pre>` 渲染 MD/TXT 内容 |
| 不可预览格式 | `window.open(download_url, '_blank')` 直接下载 |
| 无 URL | 保持静态卡片 |
| 视觉 | 可点击时 cursor-pointer + hover:shadow-md |

### FilePreviewModal (新增，嵌入 resourcePreviewStore)

| 需求 | 说明 |
|------|------|
| Store state | `filePreviewOpen`, `filePreviewUrl`, `filePreviewTitle`, `filePreviewType` ("pdf" \| "text" \| null) |
| Store action | `openFilePreview(url, title)` — 从后缀推断 type → set state |
| PDF 渲染 | `<iframe src={url} className="w-full h-[80vh]">` |
| 文本渲染 | `<pre className="overflow-auto max-h-[80vh] p-4">{content}</pre>` — 需 fetch 文本内容 |
| Modal UI | 半透明遮罩 + max-w-4xl + 顶栏 (title + 关闭 + "新窗口打开") |
| 渲染位置 | CourseLayout 中 (与 ResourcePreviewDrawer/NodeDetailPanel 并列) |
| ⚠️ 跨域 | 文件 URL 需同域或服务端配 CORS (由 /api/file_list_graph_files 返回的 path 决定) |

### API 依赖

- `fetchResourceDetail(userId, resourceId)` from `api/generativeApi` — 已在 store.openResource 中调用
- `authStore.student.userId` — 已有
- `ResourceSummary.resource_id` — 已有 (来自 fetchResourceList)
