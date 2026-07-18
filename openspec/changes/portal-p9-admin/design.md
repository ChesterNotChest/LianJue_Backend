## Context

Admin 区域含 4 个页面，共享 AdminLayout（管理侧栏导航）。4 个 SVG mockups:
- `09-admin-dashboard.svg` — 管理后台首页：stats 卡片 + 学科列表
- `10-admin-create-subject.svg` — 创建新学科表单
- `11-admin-students.svg` — 学生管理表格
- `12-admin-graph.svg` — 图谱编辑器

## 数据流

### AdminDashboard
```
AdminLayout → AdminDashboard
  ├── POST /api/syllabus_list → 学科列表 + stats
  └── Render: stats cards + syllabus table
```

### CreateSubject
```
AdminLayout → CreateSubject
  ├── POST /api/syllabus_create {title, subject_title, ...} → create
  └── Render: form fields + submit button
```

### AdminStudents
```
AdminLayout → AdminStudents
  ├── GET /api/admin/students?page=N&search=Q → student list
  └── Render: table + search + pagination
```

### AdminGraph
```
AdminLayout → AdminGraph
  ├── GET /api/study_graph/detail → graph data
  └── Render: D3 editor + node/edge CRUD
```
