## ADDED Requirements

### Requirement: Admin sub-route navigation
`/admin/subject/:syllabusId` SHALL 拥有含侧栏导航的三条子路由，每条有独立 URL 供深层链接和浏览器前进/后退。

#### Scenario: Navigate admin sub-routes
- **WHEN** 用户在 `/admin/subject/:syllabusId` 页的侧栏点击导航项
- **THEN** 主内容区切换到对应子路由页面
- **AND** URL 变更为 `/admin/subject/:syllabusId/<subroute>`
- **AND** 浏览器后退按钮可返回上一子路由

#### Scenario: Admin dashboard sub-route
- **WHEN** 用户访问 `/admin/subject/:syllabusId`（index 路由）
- **THEN** 显示学科总览页——包含知识填充面板（文件上传 + 创建填充任务按钮）和大纲编辑面板（JSON textarea + 保存按钮）
- **AND** 侧栏导航三个项可见：学科总览（激活）/ 学生进度 / 知识图谱

#### Scenario: Admin students sub-route
- **WHEN** 用户访问 `/admin/subject/:syllabusId/students`
- **THEN** 显示学生进度 grid——每个学生显示学习图谱 D3 小图 + 画像摘要统计 + 学伴成长树

#### Scenario: Admin graph sub-route
- **WHEN** 用户访问 `/admin/subject/:syllabusId/graph`
- **THEN** 显示知识图谱管理员视图——D3 或 Galaxy 图谱 + 图谱元信息

### Requirement: Admin sidebar
Admin 视图 SHALL 在左侧渲染导航侧栏，内容为：
- 学科名称 + 状态 badge
- 三个导航链接：学科总览 / 学生进度 / 知识图谱，各有图标
- 底部 `← 返回首页` 面包屑链接

#### Scenario: Admin sidebar active state
- **WHEN** 用户在当前 admin 子页面
- **THEN** 侧栏中对应导航项高亮（accent 背景 + 左侧竖线指示器）
- **AND** 其他项显示为灰色文本

### Requirement: Admin breadcrumb
所有 admin 子页面 SHALL 在顶栏显示 `← 返回首页` 面包屑，点击导航到 `/`（Dashboard）。

#### Scenario: Click admin breadcrumb
- **WHEN** 用户点击 admin 页面的 `← 返回首页`
- **THEN** 导航到 Dashboard 门户页
