# 权限模型重构 & 管理端/用户端学科预览

> 来源: [docs/better_display_small_plan.md](better_display_small_plan.md)
> 版本: v2.0
> 日期: 2026-06-27
> 状态: 待审核

---

## 总体数据流 (跨阶段)

```
┌──────────┐  POST /api/user_login    ┌──────────┐  User.query  ┌──────────┐
│  Client  │ ───────────────────────> │  Flask   │ ──────────> │  MySQL   │
│  (React) │ <─────────────────────── │  API     │ <────────── │  ORM     │
└──────────┘  { user, permission }    └──────────┘             └──────────┘
     │                                     │
     │ permission='user'                   │ permission='operator'
     │ → syllabus_list (published only)    │ → syllabus_list (all)
     │ → lifelong_overview (force graph)   │ → create subject workflow
     │ → learning_init_personal_syllabus   │ → publish
     │                                     │ → students_progress
     ▼                                     ▼
  学习视角                              管理视角
```

---

## Phase 1: 数据层 (DB migration + model + enum)

### 0. 常量定义

```python
# constant.py — 删除
class SyllabusPermission(Enum):      # ✗ REMOVE
    USER = "user"
    OWNER = "owner"

# constant.py — 新增
class UserPermission(Enum):
    USER = "user"                    # 普通学习者
    OPERATOR = "operator"            # 平台管理员

class SyllabusStatus(Enum):
    DRAFT = "draft"                  # 创建中，学生不可见
    PUBLISHED = "published"          # 已发布，学生可见，大纲锁定
```

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `schemas/user.py` | **改** — 新增 `permission` 列 |
| `schemas/syllabus.py` | **改** — 新增 `status` 列 |
| `constant.py` | **改** — 删除 `SyllabusPermission`，新增 `UserPermission` + `SyllabusStatus` |
| `scripts/migrate_v2.sql` | **新** — DDL migration |

### 2. 数据流

```
DB Migration
  │
  ├── ALTER TABLE user ADD COLUMN permission VARCHAR(50) NOT NULL DEFAULT 'user'
  │   └── 存量行自动填充 'user'（与 DEFAULT 一致）
  │
  └── ALTER TABLE syllabus ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'
      └── 存量行自动填充 'draft'（需手动 UPDATE 已上线的学科为 'published'）
```

### 3. 函数收口

#### `schemas/user.py`

```python
class User(db.Model):
    __tablename__ = 'user'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    # 新增
    permission = db.Column(db.String(50), nullable=False, default='user')
    # 值域: 'user' | 'operator'
```

#### `schemas/syllabus.py`

```python
class Syllabus(db.Model):
    __tablename__ = 'syllabus'
    syllabus_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=True, default=None)
    edu_calendar_path = db.Column(db.String(255), nullable=True, unique=True, default=None)
    syllabus_draft_path = db.Column(db.String(255), nullable=True, unique=True, default=None)
    syllabus_path = db.Column(db.String(255), nullable=True, unique=True, default=None)
    file_id = db.Column(db.Integer, nullable=True)
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    day_one_time = db.Column(db.DateTime, nullable=True, default=None)
    # 新增
    status = db.Column(db.String(20), nullable=False, default='draft')
    # 值域: 'draft' | 'published'
```

#### `scripts/migrate_v2.sql`

```sql
ALTER TABLE user ADD COLUMN permission VARCHAR(50) NOT NULL DEFAULT 'user';
ALTER TABLE syllabus ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft';
-- 可选: 将存量已上线学科手动标为 published
-- UPDATE syllabus SET status = 'published' WHERE syllabus_path IS NOT NULL;
```

### 4. 测试用例 (Phase 1)

| 编号 | 测试点 | 前置 | 输入 | 期望 |
|---|---|---|---|---|
| UT-01 | User.permission 默认值 | 空 user 表 | `User(user_name='test', password_hash='x', email='t@t.com')` → db.session.commit() | `user.permission == 'user'` |
| UT-07 | Syllabus.status 默认值 | 空 syllabus 表 | `Syllabus(edu_calendar_path='/tmp/t.pdf')` → commit | `s.status == 'draft'` |
| UT-02 | UserPermission enum | — | `UserPermission.USER.value` | `'user'` |
| UT-02b | UserPermission enum | — | `UserPermission.OPERATOR.value` | `'operator'` |
| UT-08 | SyllabusStatus enum | — | `SyllabusStatus.DRAFT.value` | `'draft'` |
| UT-08b | SyllabusStatus enum | — | `SyllabusStatus.PUBLISHED.value` | `'published'` |

---

## Phase 2: 权限基础设施

### 0. 常量定义

无新增。依赖 Phase 1 的 `UserPermission`。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `utils/auth.py` | **新** — `require_operator` 装饰器 |
| `repositories/user_syllabus_repo.py` | **改** — 移除 `syllabus_permission` 参数和过滤 |

### 2. 数据流

```
Request
  │
  ├── @require_operator 装饰器
  │     ├── 从 request body 或 query string 提取 user_id
  │     ├── User.query.get(user_id)
  │     ├── user.permission == 'operator' → 放行
  │     └── 否则 → 403 { error_code: 'operator_required' }
  │
  └── user_syllabus_repo
        ├── list_user_syllabuses(user_id)        ← 移除 syllabus_permission 参数
        ├── list_user_syllabuses_by_syllabus(id) ← 移除 syllabus_permission 参数
        └── create_user_syllabus(user_id, syllabus_id)
            ← 移除 syllabus_permission 参数，default='user'
```

### 3. 函数收口

#### `utils/auth.py` — `require_operator`

```python
from functools import wraps
from flask import request, jsonify
from schemas.user import User

def require_operator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or request.args.get('user_id')
        if not user_id:
            return jsonify({
                'success': False, 'error_message': 'missing user_id',
                'error_code': 'missing_fields'
            }), 400
        user = User.query.get(int(user_id))
        if not user or user.permission != 'operator':
            return jsonify({
                'success': False, 'error_message': 'operator permission required',
                'error_code': 'operator_required'
            }), 403
        return f(*args, **kwargs)
    return decorated
```

#### `repositories/user_syllabus_repo.py` — 清理 `syllabus_permission`

```python
# 收口前
def list_user_syllabuses(user_id: int, syllabus_permission: str = None) -> list[UserSyllabus]:
    q = UserSyllabus.query.filter_by(user_id=user_id)
    if syllabus_permission is not None:               # ← 移除
        q = q.filter_by(syllabus_permission=syllabus_permission)
    return q.all()

# 收口后
def list_user_syllabuses(user_id: int) -> list[UserSyllabus]:
    return UserSyllabus.query.filter_by(user_id=user_id).all()

# list_user_syllabuses_by_syllabus — 同上清理
# create_user_syllabus — 移除 syllabus_permission 参数，固定 default='user'
def create_user_syllabus(user_id: int, syllabus_id: int,
                         personal_syllabus_path: str = None,
                         personal_profile_path: str = None) -> UserSyllabus:
    existing = get_user_syllabus(user_id, syllabus_id)
    if existing:
        # 仅更新 personal_*_path，不再改 syllabus_permission
        ...
    us = UserSyllabus(user_id=user_id, syllabus_id=syllabus_id,
                       personal_syllabus_path=personal_syllabus_path,
                       personal_profile_path=personal_profile_path)
    ...
```

### 4. 测试用例 (Phase 2)

| 编号 | 测试点 | 前置 | 输入 | 期望 |
|---|---|---|---|---|
| UT-04 | require_operator 拒绝 user | user(permission='user'), operator_endpoint | POST body `{user_id: user.id}` | 403, `error_code: 'operator_required'` |
| UT-04b | require_operator 放行 operator | user(permission='operator'), operator_endpoint | POST body `{user_id: op.id}` | 200 |
| UT-03 | list_user_syllabuses 不过滤 permission | user 绑定了 3 个 syllabus | `list_user_syllabuses(user_id)` | 返回 3 条，无 permission 过滤 |
| UT-05 | create_user_syllabus 不用 OWNER | — | `create_user_syllabus(uid, sid)` | UserSyllabus 行存在，syllabus_permission 为默认值 |

---

## Phase 3: 任务层清理 + 增强

### 0. 常量定义

无新增。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tasks/user_task.py` | **改** — `register()` 移除 `SyllabusPermission` 引用 |
| `tasks/syllabus_task.py` | **改** — 清理 `syllabus_permission` 引用；`_serialize_teacher_syllabus` 移除 permission 字段；新增 `publish_syllabus()` |
| `tasks/study_graph/service.py` | **改** — 增强 `get_student_lifelong_overview()` |

### 2. 数据流

```
Phase 3 — 三条独立数据流:

A. register() 清理流
   register(user_name, password, email)
     ├── create_user(permission='user')     ← 不再导入 SyllabusPermission
     ├── list_all_syllabuses()              ← 返回所有 syllabus (含 draft + published)
     │   └── 讨论: 是否只绑 published? → 建议绑所有 (operator 视角的 draft 也算)
     ├── for each syllabus: create_user_syllabus(user_id, syllabus_id)
     └── return { user_id, user_name, email }

B. syllabus_task 清理流
   upload_calendar()
     ├── create_syllabus(status='draft')        ← 不再设 OWNER
     └── create_user_syllabus(uploader_id, syllabus_id)  ← 仅绑 uploader

   _serialize_teacher_syllabus(syllabus, user_binding)
     ├── 移除 syllabus_permission 字段
     ├── 新增 status: syllabus.status
     └── 新增 bound_users: count(UserSyllabus where syllabus_id)

   _list_manageable_syllabuses()  ← 废弃，用 status 替代

   list_all_syllabuses_brief_info(user_id, manage)
     ├── manage 参数保留但语义改变
     ├── user_id=None → 返回所有 (teacher-style, 无 user 过滤)
     ├── user_id + user.permission='user' → 仅返回 status='published'
     └── user_id + user.permission='operator' → 返回所有，含 status 字段

C. lifelong_overview 增强流
   get_student_lifelong_overview(user_id)
     ← 当前: { tree_id, type, syllabi: [{syllabus_id, subject_title, node_count}] }
     → 增强后:
       1. StudyGraphTree.query.filter_by(user_id).order_by(updated_at.desc()).all()
       2. 生成 user_root node: { id, type:'user_root', label, fx:0, fy:0, radius:18 }
       3. for each tree:
            subject_node = { id: f"subject:{syllabus_id}", type:'subject',
                             label: tree.subject_title, group:'chapter', radius:12 }
            nodes += list_nodes(tree_id), 前缀 syllabus_id 防冲突
            edges += list_edges(tree_id) 保持 parent_of
            edges += { source: 'user_root', target: subject_node.id, type:'enrolled' }
       4. return { tree_id, type:'student', user_id,
                   nodes: [user_root + all_subjects + all_knowledge],
                   edges: [enrolled_edges + all_parent_of_edges] }
```

### 3. 函数收口

#### `tasks/user_task.py` — `register()`

```python
# 输入
user_name: str          # 用户名
password: str            # 明文密码
email: str               # 邮箱

# 内部逻辑
def register(user_name, password, email) -> Optional[dict]:
    # 1. 检查重复（不变）
    if get_user_by_username(user_name) or get_user_by_email(email):
        return None
    # 2. 创建用户（permission='user' 由 model default 保证）
    ph = generate_password_hash(password)
    u = create_user(user_name, ph, email)
    if not u: return None
    # 3. 绑定所有现有 syllabus（不再导入 SyllabusPermission）
    for syllabus in list_all_syllabuses():
        create_user_syllabus(user_id=u.user_id, syllabus_id=syllabus.syllabus_id)
    # 4. 返回
    return {'user_id': u.user_id, 'user_name': u.user_name, 'email': u.email}

# 输出
{'user_id': int, 'user_name': str, 'email': str} | None
```

#### `tasks/syllabus_task.py` — `upload_calendar()`

```python
# 输入
file_path: str           # 校历文件路径
file_name: str           # 文件名
file_bytes: bytes|None   # 文件内容
upload_time: str|None    # 上传时间 ISO
user_id: int|None        # 上传者 (operator)

# 内部逻辑 (改动点)
def upload_calendar(...) -> Syllabus:
    ...
    syllabus = create_syllabus(edu_calendar_path=path, file_id=file_id)
    # ← status='draft' 由 model default 保证
    if syllabus and user_id:
        create_user_syllabus(user_id, syllabus_id)  # 不再传 OWNER
    return syllabus

# 输出
Syllabus ORM object | Exception
```

#### `tasks/syllabus_task.py` — `_serialize_teacher_syllabus()`

```python
# 输入
syllabus: Syllabus ORM
user_binding: UserSyllabus | None   # 调用方可传 None

# 内部逻辑
def _serialize_teacher_syllabus(syllabus, user_binding=None) -> dict:
    graph_id, graph_name = _get_primary_graph_info(syllabus.syllabus_id)
    return {
        'syllabus_id': syllabus.syllabus_id,
        'title': syllabus.title,
        'status': syllabus.status,              # ← 新增
        'edu_calendar_path': syllabus.edu_calendar_path,
        'syllabus_draft_path': syllabus.syllabus_draft_path,
        'syllabus_path': syllabus.syllabus_path,
        'day_one_time': _serialize_day_one_time(syllabus.day_one_time),
        'graph_id': graph_id,
        'graph_name': graph_name,
        # ← 移除 syllabus_permission
    }

# 输出
dict: 如上
```

#### `tasks/syllabus_task.py` — `list_all_syllabuses_brief_info()` (重构)

```python
# 输入
user_id: int|None
manage: bool               # 保留参数但语义改变

# 内部逻辑
def list_all_syllabuses_brief_info(user_id=None, manage=False) -> list[dict]:
    if user_id is None:
        # 无用户上下文 → 返回所有（teacher 视角）
        return [_serialize_teacher_syllabus(s) for s in list_all_syllabuses()]

    user = get_user_by_id(user_id)
    if not user:
        return []

    if user.permission == 'operator':
        # operator → 返回所有，额外含 bound_users 计数
        syllabuses = list_all_syllabuses()
        return [_serialize_operator_syllabus(s) for s in syllabuses]
    else:
        # 普通 user → 仅返回 status='published'
        bindings = list_user_syllabuses(user_id)
        result = []
        for b in bindings:
            s = get_syllabus_by_id(b.syllabus_id)
            if s and s.status == 'published':
                result.append(_serialize_student_syllabus(s, b))
        return result

# 新增 helper: _serialize_operator_syllabus
def _serialize_operator_syllabus(syllabus) -> dict:
    d = _serialize_teacher_syllabus(syllabus)
    d['bound_users'] = UserSyllabus.query.filter_by(
        syllabus_id=syllabus.syllabus_id
    ).count()
    return d

# 输出
list[dict]  # 每项含 syllabus_id, title, status, isLearning (student), bound_users (operator)
```

#### `tasks/study_graph/service.py` — `get_student_lifelong_overview()` (增强)

```python
# 输入
user_id: int

# 内部逻辑
def get_student_lifelong_overview(user_id: int) -> dict:
    trees = StudyGraphTree.query.filter_by(
        user_id=user_id
    ).order_by(StudyGraphTree.updated_at.desc()).all()

    user_root = {
        'node_id': f'user_root:{user_id}',
        'tree_id': f'student_{user_id}',
        'type': 'user_root',
        'title': '学习全景',
        'label': '学习全景',
        'group': 'user_root',
        'virtual': False,
        'radius': 18,
        'mastery': {},
    }

    all_nodes = [user_root]
    all_edges = []
    syllabi_summary = []

    for tree in trees:
        subject_id = f'subject:{tree.syllabus_id}'
        all_nodes.append({
            'node_id': subject_id,
            'type': 'subject',
            'title': tree.subject_title or f'学科 {tree.syllabus_id}',
            'label': tree.subject_title or f'学科 {tree.syllabus_id}',
            'group': 'chapter',
            'radius': 12,
            'mastery': {},
        })
        all_edges.append({
            'source': user_root['node_id'],
            'target': subject_id,
            'edge_type': 'enrolled',
        })

        # 取出该学科的完整节点 + 边
        raw_nodes = list_nodes(tree.tree_id)
        raw_edges = list_edges(tree.tree_id)

        for n in raw_nodes:
            n['original_node_id'] = n.get('node_id', '')
            n['node_id'] = f"{tree.syllabus_id}:{n.get('node_id', '')}"
            # 重写 parent_node_id 以匹配新 ID
            if n.get('parent_node_id'):
                n['parent_node_id'] = f"{tree.syllabus_id}:{n['parent_node_id']}"
            all_nodes.append(n)

        for e in raw_edges:
            e['source'] = f"{tree.syllabus_id}:{e.get('source', '')}"
            e['target'] = f"{tree.syllabus_id}:{e.get('target', '')}"
            all_edges.append(e)

        node_count = len(raw_nodes)
        syllabi_summary.append({
            'syllabus_id': tree.syllabus_id,
            'subject_title': tree.subject_title,
            'tree_id': tree.tree_id,
            'node_count': node_count,
        })

    return {
        'success': True,
        'tree': {
            'tree_id': f'student_{user_id}',
            'type': 'student',
            'user_id': user_id,
            'nodes': all_nodes,
            'edges': all_edges,
            'syllabi': syllabi_summary,
        }
    }

# 输出
{
    'success': True,
    'tree': {
        'tree_id': str,      # "student_{user_id}"
        'type': 'student',
        'user_id': int,
        'nodes': [           # user_root + 所有学科 subject + 所有 knowledge
            { 'node_id': str, 'type': str, 'title': str, 'label': str,
              'group': str, 'radius': float, 'mastery': dict },
            ...
        ],
        'edges': [           # enrolled + parent_of
            { 'source': str, 'target': str, 'edge_type': str },
            ...
        ],
        'syllabi': [         # 摘要（向后兼容）
            { 'syllabus_id': int, 'subject_title': str, 'tree_id': str, 'node_count': int }
        ]
    }
}
```

### 4. 测试用例 (Phase 3)

| 编号 | 测试点 | 前置 | 输入 | 期望 |
|---|---|---|---|---|
| UT-05 | register 不导入 SyllabusPermission | 代码层面 | grep `SyllabusPermission` in `tasks/user_task.py` | 0 结果 |
| UT-06 | upload_calendar 不传 OWNER | operator 上传 | `upload_calendar(..., user_id=op_id)` | UserSyllabus 行存在，syllabus_permission 为默认值 |
| UT-03 | list_all_syllabuses_brief_info 不过滤 permission | 有 published 和 draft | `list_all_syllabuses_brief_info()` | 返回所有，不因 syllabus_permission 遗漏 |
| IT-03b | lifelong_overview 返回合并图 | user 有 2+ 棵 StudyGraphTree | `get_student_lifelong_overview(user_id)` | nodes 含 user_root + 2 subject + all knowledge; edges 含 enrolled + parent_of |

---

## Phase 4: API 层

### 0. 常量定义

无新增。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `blueprint/user_api.py` | **改** — `login_api` 返回 `permission` 字段 |
| `blueprint/syllabus_material_api.py` | **改** — `list_syllabuses_api` 重构；`update_syllabus_api` / `update_syllabus_draft_api` 加锁 |
| `blueprint/knowledge_build_api.py` | **改** — 加 `@require_operator` |
| `blueprint/file_transmit_api.py` | **改** — `file_upload_calendar` 加 `@require_operator` |
| `blueprint/study_graph_api.py` | **改** — 无参数时走增强 lifelong |
| `blueprint/admin_api.py` | **新** — operator 管理端点 |

### 2. 数据流

```
Phase 4 — API 层数据流:

A. 用户登录 → permission
   POST /api/user_login { user_name, password }
     → login() → User.query → check_password_hash
     → 返回 { success, user: { user_id, user_name, email, permission } }
        ← 新增 permission 字段

B. 学科列表 (核心重构)
   POST /api/syllabus_list { user_id }
     → User.query.get(user_id)
     ├─ permission='user' →
     │    list_user_syllabuses(user_id)
     │    → for each: get_syllabus → 仅保留 status='published'
     │    → _serialize_student_syllabus() → { isLearning, title, ... }
     │
     └─ permission='operator' →
          list_all_syllabuses()
          → _serialize_operator_syllabus() → { status, bound_users, ... }

C. 学科发布 (新)
   POST /api/admin/syllabus/<id>/publish { user_id }
     → @require_operator → 403 | 放行
     → Syllabus.query.get(id)
     ├─ syllabus.syllabus_path is None → 400 syllabus_incomplete
     ├─ syllabus.status == 'published' → 400 already_published
     └─ OK:
          users = list_all_users_brief()
          for each: create_user_syllabus(user.user_id, id)
          syllabus.status = 'published'; db.session.commit()
          return { success: true, syllabus_id, bound_users: len(users) }

D. 学科编辑锁定
   POST /api/syllabus_update { user_id, syllabus_id, ... }
   POST /api/syllabus_update_draft { user_id, syllabus_id, ... }
     → @require_operator → 403 | 放行
     → Syllabus.query.get(syllabus_id)
     ├─ syllabus.status == 'published' → 403 syllabus_locked
     └─ OK: 原有逻辑继续

E. 学科用户进度总览 (新)
   GET /api/admin/syllabus/<id>/students_progress?user_id=X
     → @require_operator → 403 | 放行
     → 查询 UserSyllabus where syllabus_id=id
     → for each binding:
          user_index = 匿名索引 (1, 2, 3...)
          study_graph_tree = get_tree(user_id, syllabus_id)
          buddy_tree = load_buddy_tree(user_id, syllabus_id)  # 文件系统
          result.append({ user_index, study_graph: StudyGraphTree, buddy_tree: BuddyTree })
     → 返回 { students: [...], total: N }

F. 用户提权/降级 (新)
   POST /api/admin/set_permission { user_id (operator), target_user_id, permission }
     → @require_operator → 403 | 放行
     → User.query.get(target_user_id)
     → target.permission = permission
     → db.session.commit()
     → return { success: true, user: { user_id, user_name, permission } }

G. 文件上传/图谱/Job — 统一加 @require_operator
   POST /api/file_upload_calendar      ← 加装饰器
   POST /api/job_graph_create          ← 加装饰器
   POST /api/syllabus_build_draft      ← 加装饰器
   POST /api/syllabus_build            ← 加装饰器
   POST /api/job_create                ← 加装饰器
```

### 3. 函数收口

#### `blueprint/user_api.py` — `login_api()` (修改)

```python
# 输入 (JSON body)
{ 'user_name': str, 'password': str }

# 内部逻辑
@bp.route('/user_login', methods=['POST'])
def login_api():
    data = request.get_json(silent=True) or {}
    username = data.get('user_name') or data.get('username')
    password = data.get('password')
    ...
    u = login(username, password)
    if not u: return 401
    return jsonify({
        'success': True,
        'user': u,  # ← 已包含 permission (login() 返回 dict 需加字段)
        ...
    })

# login() 在 tasks/user_task.py 需同步修改:
def login(user_name, password) -> Optional[dict]:
    u = get_user_by_username(user_name)
    if not u or not check_password_hash(u.password_hash, password):
        return None
    return {
        'user_id': u.user_id, 'user_name': u.user_name,
        'email': u.email,
        'permission': u.permission  # ← 新增
    }

# 输出
{ 'success': True, 'user': { 'user_id', 'user_name', 'email', 'permission' } }
```

#### `blueprint/admin_api.py` — `publish_syllabus_api()` (新)

```python
# 输入 (URL param + JSON body)
URL: /api/admin/syllabus/<int:syllabus_id>/publish
Body: { 'user_id': int }   # operator 的 ID

# 内部逻辑
@bp.route('/admin/syllabus/<int:syllabus_id>/publish', methods=['POST'])
@require_operator
def publish_syllabus_api(syllabus_id):
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return jsonify({'success': False, 'error_code': 'not_found'}), 404
    if not syllabus.syllabus_path:
        return jsonify({
            'success': False,
            'error_message': '最终大纲未生成，无法发布',
            'error_code': 'syllabus_incomplete'
        }), 400
    if syllabus.status == 'published':
        return jsonify({
            'success': False,
            'error_message': '学科已发布',
            'error_code': 'already_published'
        }), 400

    users = list_all_users_brief()
    bound = 0
    for u in users:
        try:
            create_user_syllabus(u['user_id'], syllabus_id)
            bound += 1
        except Exception:
            pass

    syllabus.status = 'published'
    db.session.commit()

    return jsonify({
        'success': True,
        'syllabus_id': syllabus_id,
        'bound_users': bound,
        'status': 'published'
    })

# 输出
{ 'success': True, 'syllabus_id': int, 'bound_users': int, 'status': 'published' }
```

#### `blueprint/admin_api.py` — `students_progress_api()` (新)

```python
# 输入 (URL params)
GET /api/admin/syllabus/<int:syllabus_id>/students_progress?user_id=X&limit=50

# 内部逻辑
@bp.route('/admin/syllabus/<int:syllabus_id>/students_progress', methods=['GET'])
@require_operator
def students_progress_api(syllabus_id):
    limit = min(int(request.args.get('limit', 50)), 100)

    bindings = list_user_syllabuses_by_syllabus(syllabus_id)
    students = []
    for idx, binding in enumerate(bindings[:limit]):
        user_id = binding.user_id
        tree = get_tree(user_id, syllabus_id)
        buddy_tree = load_buddy_tree(user_id, syllabus_id)
        students.append({
            'user_index': idx + 1,
            'study_graph': tree,          # StudyGraphTree dict (nodes+edges+summary)
            'buddy_tree': buddy_tree,     # BuddyTree dict (regions) or None
        })

    return jsonify({
        'success': True,
        'syllabus_id': syllabus_id,
        'students': students,
        'total': len(bindings),
    })

# 输出
{
    'success': True,
    'syllabus_id': int,
    'students': [
        { 'user_index': int, 'study_graph': dict|None, 'buddy_tree': dict|None },
        ...
    ],
    'total': int
}
```

#### `blueprint/admin_api.py` — `set_permission_api()` (新)

```python
# 输入 (JSON body)
{ 'user_id': int, 'target_user_id': int, 'permission': 'user'|'operator' }

# 内部逻辑
@bp.route('/admin/set_permission', methods=['POST'])
@require_operator
def set_permission_api():
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_user_id')
    new_perm = data.get('permission')
    if not target_id or new_perm not in ('user', 'operator'):
        return jsonify({'success': False, 'error_code': 'invalid_fields'}), 400

    target = User.query.get(int(target_id))
    if not target:
        return jsonify({'success': False, 'error_code': 'not_found'}), 404

    target.permission = new_perm
    db.session.commit()

    return jsonify({
        'success': True,
        'user': {'user_id': target.user_id, 'user_name': target.user_name, 'permission': target.permission}
    })

# 输出
{ 'success': True, 'user': { 'user_id', 'user_name', 'permission' } }
```

### 4. 测试用例 (Phase 4)

| 编号 | 测试点 | 前置 | 输入 | 期望 |
|---|---|---|---|---|
| IT-01 | user 登录返回 permission='user' | 预置 user | `POST /api/user_login {user_name, password}` | `response.user.permission == 'user'` |
| IT-02 | operator 登录返回 permission='operator' | 预置 operator | `POST /api/user_login {op_name, password}` | `response.user.permission == 'operator'` |
| IT-03 | user 仅看到已发布学科 | 有 draft + published 学科, user 已登录 | `POST /api/syllabus_list {user_id}` | 返回项全为 `status='published'` |
| IT-04 | operator 看到全部学科含 draft | operator 已登录 | `POST /api/syllabus_list {op_id}` | 返回含 draft 项，带 `status` + `bound_users` |
| IT-05 | user 不能调 admin 端点 | user 登录 | `POST /api/admin/set_permission` | 403 |
| IT-06 | 创建学科完整流程 | operator 登录 | graph_create → upload_calendar → syllabus_build_draft → job_create → syllabus_build | 全部 200 |
| IT-07 | syllabus_build_draft 无 graph 拒绝 | operator 登录, 无 graph_id | `POST /api/syllabus_build_draft {syllabus_id, graph_id=999}` | 400/500, 报错 |
| IT-07b | publish 批量绑定 | 2 个 user, 1 个 draft 学科 (已建好 syllabus_path) | `POST /api/admin/syllabus/<id>/publish` | bound_users=2, status='published', UserSyllabus 新增 2 行 |
| IT-07c | 重复 publish 拒绝 | published 学科 | `POST /api/admin/syllabus/<id>/publish` | 400 `already_published` |
| IT-07d | syllabus_path 空拒绝 publish | 仅有 draft 无 final 的学科 | publish | 400 `syllabus_incomplete` |
| IT-07e | published 后编辑被锁 | published 学科 | `POST /api/syllabus_update {syllabus_id, ...}` | 403 `syllabus_locked` |
| IT-07f | user 看不到 draft | draft 学科 | `POST /api/syllabus_list {user_id}` | 不包含该 draft |
| IT-07g | operator 看 draft 标记 | draft 学科 | `POST /api/syllabus_list {op_id}` | 含 `status: 'draft'`, `bound_users: 0` |
| IT-08 | students_progress 返回两个树 | published 学科, 2 个学员有交互 | `GET /api/admin/syllabus/<id>/students_progress?user_id=op` | students[0].study_graph 含 nodes/edges, students[0].buddy_tree 含 regions |
| IT-09 | 无学员学科返回空 | 刚 publish 无学生进入的学科 | students_progress | `students: []`, `total: 0` |

---

## Phase 5: 前端

### 0. 常量定义

无后端常量。前端组件树结构参见 `_ref_tailwind-website-style-skill.md`。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `src/pages/SubjectOverview.tsx` | **新** — 学科预览页（用户+管理员双模式） |
| `src/pages/CreateSubject.tsx` | **新** — 创建学科 5 步流程 |
| `src/pages/AdminSubjectDetail.tsx` | **新** — 学科管理详情（card-stack + D3 graph） |
| `src/components/graph/D3GraphViewer.tsx` | **不改**（复用，可能适配暗色背景） |
| `src/api/studyGraphApi.ts` | **改** — `treeResponseToGraph()` 可复用；新增 `buddyRegionsToGraph()` |
| `src/api/authApi.ts` | **改** — login 响应类型增加 `permission` 字段 |
| `src/api/syllabusApi.ts` | **改** — `syllabus_list` 响应类型增加 `status` 字段 |
| `src/stores/authStore.ts` | **改** — store 增加 `permission` 字段 |
| `examples/style.css` | **复用到** `src/styles/lianjue.css` + 追加扩展样式 |

### 2. 数据流

```
前端数据流:

App.tsx
  ├── authStore.permission === 'user'
  │     └── <SubjectOverview mode="user" />
  │           ├── 左:学科卡片网格
  │           │     ← POST /api/syllabus_list {user_id}
  │           │     ← 每卡: title, isLearning, personal_progress
  │           │     ← 点击卡片 → navigate(`/learn/${syllabus_id}`)
  │           └── 右:D3GraphViewer (layout=force, 360px)
  │                 ← GET /api/study_graph/detail?user_id=X
  │                 ← treeResponseToGraph(lifelong_tree)
  │
  └── authStore.permission === 'operator'
        └── <SubjectOverview mode="operator" />
              ├── [+ 创建新学科] 按钮 → navigate('/admin/create-subject')
              ├── 左:学科卡片网格 (管理版)
              │     ← POST /api/syllabus_list {op_id}
              │     ← 每卡: title, status(draft/published), bound_users
              │     ← draft: [管理] → /admin/subject/{id}
              │     ← published: [学习] → /learn/{id}, [管理] → /admin/subject/{id}
              └── 右:D3GraphViewer (同用户版, operator 自己的全景图)

/admin/create-subject
  └── <CreateSubject />
        ├── Step1: Input 图谱名 → POST /api/job_graph_create
        ├── Step2: 选图谱 + 上传校历 → POST /api/file_upload_calendar
        │          → POST /api/syllabus_build_draft
        ├── Step3: 上传知识文件 → POST /api/job_create
        ├── Step4: → POST /api/syllabus_build
        └── Step5: → POST /api/admin/syllabus/{id}/publish

/admin/subject/{id}
  └── <AdminSubjectDetail />
        ├── nav: [填充知识] [编辑大纲]
        └── 学员 card-stack 网格
              ← GET /api/admin/syllabus/{id}/students_progress
              ← 每组卡:
                  Card1: D3GraphViewer(tree layout, StudyGraphTree)
                    ← treeResponseToGraph(student.study_graph)
                  Card2: D3GraphViewer(force layout, BuddyTree)
                    ← buddyRegionsToGraph(student.buddy_tree)
```

### 3. 函数收口（关键前端函数）

#### `buddyRegionsToGraph()` (新)

```typescript
// 输入
buddyTree: {
  regions: {
    trunk: Array<{ step_id: string; title: string; status: string; outcomes: string[] }>,
    learned: Array<{ title: string; signal: string; score: number; associated_trunk: string[] }>,
    explore: Array<{ title: string; signal: string; score: number; associated_trunk: string[]; associated_learned: string[] }>,
  }
}

// 内部逻辑
function buddyRegionsToGraph(buddyTree): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // trunk → chain of nodes
  const trunk = buddyTree.regions.trunk || [];
  trunk.forEach((step, i) => {
    nodes.push({
      id: `trunk:${step.step_id}`,
      label: step.title,
      group: 'active',          // 靛蓝
      radius: 8,
      meta: { status: step.status, region: 'trunk' }
    });
    if (i > 0) {
      edges.push({
        source: `trunk:${trunk[i-1].step_id}`,
        target: `trunk:${step.step_id}`,
        type: 'trunk_chain'
      });
    }
  });

  // learned → connect to associated trunk nodes
  const learned = buddyTree.regions.learned || [];
  learned.forEach((item, i) => {
    const id = `learned:${i}`;
    nodes.push({
      id, label: item.title, group: 'mastered', radius: 6 + item.score * 4,
      meta: { signal: item.signal, score: item.score, region: 'learned' }
    });
    (item.associated_trunk || []).forEach(trunkId => {
      edges.push({ source: `trunk:${trunkId}`, target: id, type: 'associated' });
    });
  });

  // explore → connect to trunk or learned
  const explore = buddyTree.regions.explore || [];
  explore.forEach((item, i) => {
    const id = `explore:${i}`;
    nodes.push({
      id, label: item.title, group: 'weak', radius: 4 + item.score * 2,
      meta: { signal: item.signal, score: item.score, region: 'explore' }
    });
    (item.associated_trunk || []).forEach(trunkId => {
      edges.push({ source: `trunk:${trunkId}`, target: id, type: 'associated' });
    });
  });

  return { nodes, edges };
}

// 输出
{ nodes: GraphNode[], edges: GraphEdge[] }
```

#### `SubjectOverview` 页面组件 (新)

```typescript
// 输入 (props)
mode: 'user' | 'operator'
// 从 authStore 读取: user_id, permission

// 内部逻辑 (简化)
function SubjectOverview({ mode }: { mode: 'user' | 'operator' }) {
  const [subjects, setSubjects] = useState([]);
  const [lifelongGraph, setLifelongGraph] = useState(null);

  useEffect(() => {
    // 1. fetch subjects
    api.post('/api/syllabus_list', { user_id }).then(setSubjects);
    // 2. fetch lifelong graph
    api.get(`/api/study_graph/detail?user_id=${user_id}`).then(res => {
      if (res.graph?.tree?.nodes) {
        setLifelongGraph(res.graph.tree);
      }
    });
  }, [user_id]);

  return (
    <main className="app-shell">
      <div className="space-background" />
      <section className="relative z-10 mx-auto max-w-7xl">
        <nav>...</nav>
        <div className="grid gap-8 px-5 py-10 md:grid-cols-[1fr_360px]">
          <SubjectCardGrid subjects={subjects} mode={mode} />
          <aside>
            {lifelongGraph && (
              <D3GraphViewer
                nodes={treeResponseToGraph(lifelongGraph).nodes}
                edges={treeResponseToGraph(lifelongGraph).edges}
                layout="force"
                height={600}
              />
            )}
          </aside>
        </div>
      </section>
    </main>
  );
}

// 输出
React component — 学科预览页
```

### 4. 测试用例 (Phase 5 验收)

| 编号 | 验收点 | 前置 | 操作 | 期望 |
|---|---|---|---|---|
| AT-01 | 星空背景渲染 | 页面加载 | 观察 | 7 层 gradient，星星漂移动画可见，<30% GPU |
| AT-02 | 暗色主题一致性 | 各页面 | 检查元素 | 黑底 `#05030f`，白字，cyan 强调，pill 按钮，无毛玻璃 |
| AT-03 | 用户视角：显示已发布学科 + 进入学习 | user 登录, 有 published 学科 | 观察页面 | 卡片显示标题、进度、[进入学习]；无管理按钮 |
| AT-03b | 用户视角：不显示 draft 学科 | 存在 draft 学科 | 观察页面 | draft 学科不出现在卡片网格 |
| AT-04 | 管理员视角：显示全部学科含状态 | operator 登录 | 观察页面 | draft 标 📝草稿，published 标 ✅已发布；显示 bound_users |
| AT-04b | 管理员视角：[+ 创建新学科] 按钮 | operator 登录 | 观察页面顶部 | 仅 operator 看到此按钮 |
| AT-05 | 全景图渲染 | user 登录, 有学习记录 | 观察右侧 | D3 force 图，user 居中，subject 环绕，mastery 着色 |
| AT-06 | 创建学科 5 步流程 | operator | 依次执行 Step 1-5 | Step 依次解锁；Step 5 发布后显示 bound_users 计数 |
| AT-07 | 学科管理详情 card-stack | operator, published 学科 | hover 学员卡片 | 展开 2 卡，Card1=StudyGraphTree 图，Card2=BuddyTree 图 |
| AT-08 | 响应式 | 各页面 | 缩小窗口至 375px | 卡片单列堆叠，全景图移到卡片下方 |

---

## Phase 6: 测试 & 验收

### 0. 常量

无新增。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tests/test_phase1_model.py` | **新** — Phase 1 单元测试 |
| `tests/test_phase2_auth.py` | **新** — Phase 2 单元测试 |
| `tests/test_phase3_task.py` | **新** — Phase 3 单元测试 |
| `tests/test_phase4_api.py` | **新** — Phase 4 集成测试 |
| `tests/test_regression.py` | **新** — 回归测试 |

### 2. 测试执行顺序

```
Phase 6 (测试与各 Phase 并行 — 每阶段完成后立即测)

Phase 1 → tests/test_phase1_model.py
Phase 2 → tests/test_phase2_auth.py
Phase 3 → tests/test_phase3_task.py
Phase 4 → tests/test_phase4_api.py
Phase 5 → 手动验收 + 截图对照
全部完成 → tests/test_regression.py
```

### 3. 函数收口

#### `tests/test_phase1_model.py`

```python
# 测试: UT-01, UT-02, UT-07, UT-08
class TestPhase1Model:
    def test_user_permission_default(self):
        """新建 User 自动获得 permission='user'"""
        u = User(user_name='test_p1', password_hash='x', email='p1@t.com')
        db.session.add(u); db.session.commit()
        assert u.permission == 'user'

    def test_syllabus_status_default(self):
        """新建 Syllabus 自动获得 status='draft'"""
        s = Syllabus(edu_calendar_path='/tmp/test.pdf')
        db.session.add(s); db.session.commit()
        assert s.status == 'draft'

    def test_user_permission_enum(self):
        assert UserPermission.USER.value == 'user'
        assert UserPermission.OPERATOR.value == 'operator'

    def test_syllabus_status_enum(self):
        assert SyllabusStatus.DRAFT.value == 'draft'
        assert SyllabusStatus.PUBLISHED.value == 'published'
```

#### `tests/test_phase2_auth.py`

```python
# 测试: UT-03, UT-04, UT-05
class TestPhase2Auth:
    def test_require_operator_rejects_user(self, client, user):
        """user 调 operator 端点 → 403"""
        ...

    def test_require_operator_allows_operator(self, client, operator):
        """operator 调 operator 端点 → 200"""
        ...

    def test_list_user_syllabuses_no_permission_filter(self, user, syllabuses):
        """list_user_syllabuses 不过滤 syllabus_permission"""
        ...
```

#### `tests/test_phase3_task.py`

```python
# 测试: UT-05, UT-06, IT-03b
class TestPhase3Task:
    def test_register_no_syllabus_permission_import(self):
        """register() 不导入 SyllabusPermission"""
        ...

    def test_upload_calendar_default_permission(self, operator, syllabus):
        """upload_calendar 不设 OWNER"""
        ...

    def test_lifelong_overview_merged_graph(self, user_with_2_trees):
        """get_student_lifelong_overview 返回合并图"""
        result = get_student_lifelong_overview(user_id)
        assert len(result['tree']['nodes']) >= 3  # user_root + 2 subjects
        assert 'user_root' in result['tree']['nodes'][0]['type']
```

#### `tests/test_phase4_api.py`

```python
# 测试: IT-01 ~ IT-09
class TestPhase4API:
    def test_login_returns_permission(self, client, user):
        """POST /api/user_login → permission in response"""
        ...

    def test_user_only_sees_published(self, client, user, published_s, draft_s):
        """POST /api/syllabus_list → 仅 published"""
        ...

    def test_publish_binds_all_users(self, client, operator, users, draft_s):
        """POST /api/admin/syllabus/<id>/publish → bound_users=N"""
        ...

    def test_publish_rejects_if_no_syllabus_path(self, client, operator, draft_s):
        """publish 对 syllabus_path=null → 400"""
        ...

    def test_update_blocked_after_publish(self, client, operator, published_s):
        """syllabus_update 对 published → 403"""
        ...
```

#### `tests/test_regression.py`

```python
# 测试: RT-01 ~ RT-05
class TestRegression:
    def test_register_binds_all_syllabi(self):
        """新用户注册后 UserSyllabus 包含所有现有学科"""
        ...

    def test_learning_flow_unchanged(self):
        """login → syllabus_list → init_personal_syllabus → detail 全链路"""
        ...

    def test_study_graph_unchanged(self):
        """GET /api/study_graph/detail?user_id=X&syllabus_id=Y"""
        ...

    def test_study_buddy_chat_unchanged(self):
        """POST /api/study_buddy/chat"""
        ...

    def test_file_upload_download_unchanged(self):
        """POST /api/file_upload → GET /api/file_download"""
        ...
```

### 4. 测试用例（完整清单）

已在 Phase 1-4 中详列。Phase 6 测试总量：

| 类别 | 数量 | 编号范围 |
|---|---|---|
| 单元测试 | 8 | UT-01 ~ UT-08 |
| 集成测试 | 15 | IT-01 ~ IT-09b |
| 回归测试 | 5 | RT-01 ~ RT-05 |
| 前端验收 | 8 | AT-01 ~ AT-08 |
| **合计** | **36** | |

---

## 附录 A: 文件变更总清单

| 文件 | Phase | 操作 |
|---|---|---|
| `constant.py` | P1 | 改 — 删除 SyllabusPermission，新增 UserPermission + SyllabusStatus |
| `schemas/user.py` | P1 | 改 — 新增 permission 列 |
| `schemas/syllabus.py` | P1 | 改 — 新增 status 列 |
| `scripts/migrate_v2.sql` | P1 | 新 — DDL |
| `utils/auth.py` | P2 | 新 — require_operator 装饰器 |
| `repositories/user_syllabus_repo.py` | P2 | 改 — 移除 syllabus_permission |
| `tasks/user_task.py` | P3 | 改 — register() 清理；login() 加 permission |
| `tasks/syllabus_task.py` | P3 | 改 — 清理 permission；rework list；新序列化函数 |
| `tasks/study_graph/service.py` | P3 | 改 — 增强 get_student_lifelong_overview() |
| `blueprint/user_api.py` | P4 | 改 — login 返回 permission |
| `blueprint/syllabus_material_api.py` | P4 | 改 — list 重构；update 加锁 |
| `blueprint/knowledge_build_api.py` | P4 | 改 — 加 @require_operator |
| `blueprint/file_transmit_api.py` | P4 | 改 — 加 @require_operator |
| `blueprint/admin_api.py` | P4 | 新 — publish + students_progress + set_permission |
| `src/pages/SubjectOverview.tsx` | P5 | 新 |
| `src/pages/CreateSubject.tsx` | P5 | 新 |
| `src/pages/AdminSubjectDetail.tsx` | P5 | 新 |
| `src/api/studyGraphApi.ts` | P5 | 改 — buddyRegionsToGraph() |
| `src/api/authApi.ts` | P5 | 改 — permission 字段 |
| `src/stores/authStore.ts` | P5 | 改 — permission 字段 |
| `src/styles/lianjue.css` | P5 | 新 — 复用 examples/style.css |
| `tests/test_phase1_model.py` | P6 | 新 |
| `tests/test_phase2_auth.py` | P6 | 新 |
| `tests/test_phase3_task.py` | P6 | 新 |
| `tests/test_phase4_api.py` | P6 | 新 |
| `tests/test_regression.py` | P6 | 新 |
