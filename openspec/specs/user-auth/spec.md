# User Auth

用户认证与权限管理模块。

## API Endpoints

### POST /api/user_register
注册新用户。
- **Input**: `{user_name, password, email?}`
- **Output**: `{user_id, user_name, email, permission}`

### POST /api/user_login
用户登录。
- **Input**: `{user_name, password}`
- **Output**: `{user_id, user_name, email, permission, token?}`

### POST /api/user_change_password
修改密码（需旧密码）。
- **Input**: `{user_id, old_password, new_password}`

### POST /api/user_reset_password
管理员重置用户密码。
- **Input**: `{user_id}` (operator only)
- **Output**: `{new_password}` (temporary)

### POST /api/user_update
更新用户信息。
- **Input**: `{user_id, user_name?, email?}`

### POST /api/user_detail
获取用户详情。
- **Input**: `{user_id}`
- **Output**: `{user_id, user_name, email, permission, ...}`

### GET /api/user_list
列出所有用户（简要信息）。

### POST /api/admin/set_permission
切换用户权限（user ↔ operator）。
- **Auth**: operator only

## Data Model

```
user
├── user_id (PK)
├── user_name
├── password_hash
├── email
└── permission: "user" | "operator"
```

## Auth

- `@require_operator` 装饰器用于管理端点
- 通过 `utils/auth.py` 验证

## Integration

- 被所有其他模块依赖（user_id 作为外键）
- 学习画像模块通过 `user_syllabus` 表关联 user 和 syllabus
