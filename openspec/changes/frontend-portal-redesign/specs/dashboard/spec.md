# Dashboard

前端门户仪表盘，课程卡片展示、学习进度聚合、银河总览入口。

## ADDED Requirements

### Requirement: Course card grid
Dashboard SHALL 以卡片 grid 展示用户绑定的所有已发布课程（syllabus），每个卡片显示课程标题、关联图谱名和总体学习进度。

#### Scenario: User with multiple courses
- **WHEN** 用户已绑定 3 门课程
- **THEN** Dashboard 显示 3 张课程卡片，排列为响应式 grid（3 列 → 2 列 → 1 列）
- **AND** 每张卡片显示课程标题、图谱名、进度条
- **AND** "进入"按钮导航到 `/learn/:syllabusId/home`

#### Scenario: User with no courses
- **WHEN** 用户未绑定任何课程
- **THEN** Dashboard 显示空状态提示："暂无课程，请联系管理员或创建新学科"
- **AND** 显示 [+ 创建新学科] CTA 按钮（operator 可见）

### Requirement: Create CTA
Dashboard SHALL 在顶部提供 [+ 创建新学科] 按钮（仅 operator 权限可见），导航到 `/admin/create-subject`。

#### Scenario: Operator user
- **WHEN** 用户权限为 operator
- **THEN** 显示 [+ 创建新学科] 按钮

#### Scenario: Regular user
- **WHEN** 用户权限为 user
- **THEN** 不显示创建按钮

### Requirement: Galaxy preview scroll
Dashboard SHALL 在课程卡片下方提供 scroll-triggered reveal 区域：用户向下滚动越过卡片区域后，背景渐变过渡到深色太空色，银河星图（2D 静态渲染）渐显。该区域非点击式入口——是滚动浏览的自然延续。

#### Scenario: Scroll to reveal galaxy
- **WHEN** 用户向下滚动越过课程卡片区域
- **THEN** 页面背景从 `#f8fafc` 渐变到 `#0f172a` 深色
- **AND** 知识全景星图（SVG/Canvas 2D，非 3D）opacity 渐显
- **AND** 底部显示 subtle text "进入全屏知识总览 →" 链接
- **AND** 链接导航到 `/galaxy`

### Requirement: Agent theme
Dashboard SHALL 使用 Agent 页面浅色主题（Indigo accent, white surfaces, slate text），与 Galaxy 深色主题区分。

#### Scenario: Visual consistency
- **WHEN** 用户在 Dashboard、学科首页、AI 学习页之间导航
- **THEN** 配色方案保持一致（Indigo #6366f1 accent）
- **AND** 仅 Galaxy 页面使用深色太空主题
