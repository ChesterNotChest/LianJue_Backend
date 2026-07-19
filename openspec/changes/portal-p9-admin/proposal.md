## Why

Admin 区域含 4 个 SVG mockups:
- `09-admin-dashboard.svg` — 管理后台首页
- `10-admin-create-subject.svg` — 创建新学科
- `11-admin-students.svg` — 学生管理
- `12-admin-graph.svg` — 图谱管理

需逐 SVG 对照验证 AdminLayout + 子页面。

## What Changes

| 文件 | 操作 |
|------|------|
| `src/layouts/AdminLayout.tsx` | 验证侧栏导航 |
| `src/pages/AdminSubjectDetail.tsx` | 对照 09-admin-dashboard |
| `src/pages/CreateSubject.tsx` | 对照 10-admin-create-subject |
| AdminStudents page | 对照 11-admin-students |
| AdminGraph page | 对照 12-admin-graph |

## Impact

- **修改文件**: 4-5 个
- **SVG 对照**: 4 个 SVG 全量
