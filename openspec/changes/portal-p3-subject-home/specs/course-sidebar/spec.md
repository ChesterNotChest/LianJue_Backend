## ADDED Requirements

### Requirement: Sidebar shows course title as text without thumbnail banner
The sidebar SHALL display the course title as a `<text>` element (15px/700/#0f172a) without a CourseThumbnail banner (SVG lines 14-15).

#### Scenario: Sidebar renders text title and status badge only
- **WHEN** CourseSidebar renders with courseTitle="大数据概论" and courseStatus="published"
- **THEN** it shows text "大数据概论" at 15px/700/#0f172a and a status badge (52×20 rx=5 fill=#ede9fe) with "已发布" at 9px/600/#6366f1
- **AND** no CourseThumbnail banner is present

### Requirement: Active nav item has left color bar and background highlight
The active navigation item SHALL have a left vertical bar (3×38 rx=1.5 fill=#6366f1) and background (208×38 rx=8 fill=#6366f1 opacity=0.1), with text at 13px/700/#6366f1 (SVG lines 17-18).

#### Scenario: "学科首页" is active with purple left bar
- **WHEN** current route is /learn/{sid}/home
- **THEN** the "学科首页" item shows a 3px purple left bar and light purple background

### Requirement: Inactive nav items use plain text without icons
Inactive navigation items SHALL display as text only (13px/#475569) without lucide icons (SVG lines 19-22).

#### Scenario: "教学大纲" is inactive with gray text
- **WHEN** current route is /learn/{sid}/home
- **THEN** "教学大纲", "智能体", "学习成长图谱", "知识图谱" display at 13px/#475569 without icons

### Requirement: Nav labels match SVG exactly
Navigation labels SHALL be "学科首页", "教学大纲", "智能体", "学习成长图谱", "知识图谱" (SVG lines 18-22).

#### Scenario: All 5 nav items rendered with SVG labels
- **WHEN** CourseSidebar renders
- **THEN** the 5 nav items have labels exactly matching the SVG specification

### Requirement: Quick links section has divider and plain text links
A divider line (stroke=#f1f5f9) SHALL separate "快捷入口" (11px/600/#94a3b8) section containing "课程进度" and "我的测验" as text links (12px/#475569) without icons (SVG lines 24-27).
