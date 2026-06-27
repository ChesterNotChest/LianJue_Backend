# better_display_small_plan — 权限模型重构 & 管理端/用户端学科预览

> 版本: v1.1
> 日期: 2026-06-27
> 参考: [_ref_tailwind-website-style-skill.md](../_ref_tailwind-website-style-skill.md)
> 参考源文件均在 `Lianjue_Frontend/_ref_tailwind-website-style-skill/` 目录下

---

## 一、边界 (Scope & Boundaries)

### 1.1 本次做的事

| 层级 | 内容 |
|---|---|
| **DB** | User 表新增 `permission` 字段 (`user` / `operator`)；废弃 `UserSyllabus.syllabus_permission` 的业务含义 |
| **后端 API** | (a) 清理 syllabus_permission 的过滤/序列化逻辑 (b) 新增 operator 权限校验装饰器 (c) 新增/调整学科预览、管理端学科工作流、用户进度总览等端点 |
| **前端** | 新增"所有学科预览"页面（星空风格）；operator 视角增加"创建新学科"按钮 + "查看/编辑学科"入口；operator 学科详情页（用户进度树预览 + 填知识/编辑大纲按钮） |

### 1.2 本次不做的事

- 不改造登录/注册流程的核心逻辑（仅补充 permission 字段返回）
- 不修改 LianJue 图数据库内核
- 不做前端路由重构（只新增/修改目标页面）
- 不做 RBAC 多角色系统（当前只有 user / operator 二元）
- 不迁移历史 `syllabus_permission` 数据到新模型（旧字段保留但不读取）

---

## 二、风险 (Risks)

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| **DB 迁移失败** | 低 | 高 | ALTER TABLE 加字段是低风险操作；先跑 dry-run SQL 验证 |
| **旧 syllabus_permission 逻辑残留** | 中 | 中 | Grep 全仓 `syllabus_permission` / `SyllabusPermission` 确保无遗漏；review 每个引用点 |
| **operator 权限校验遗漏** | 中 | 高 | 用装饰器统一校验，而非散落 if-else；写测试覆盖所有 admin 端点 |
| **前端设计实现偏离 skill 规范** | 中 | 低 | 以 `_ref_tailwind-website-style-skill.md` 为验收标准；每个页面截图对照 |
| **学习进度树数据量过大** | 低 | 中 | 管理员预览时做分页 + 聚合摘要，不一次性返回所有用户完整树 |
| **旧 API 调用方受影响** | 低 | 中 | `/api/syllabus_list` 去掉 `manage` 参数 → 前端同步修改；保持返回结构向后兼容 |

---

## 三、应补充的内容 (What's Missing / Needs Clarification)

1. **谁来当 operator？** — 首个 operator 需要手动 SQL 设置。建议增加一个 setup 脚本 `scripts/set_operator.sql` 或在 `/api/user_update` 中加入 operator 用户对另一个用户提权的能力。
2. **operator 能否降级？** — 需要明确 operator 是否能把另一个 operator 改成 user。建议：operator 可以提权/降权任何用户。
3. **学科删除？** — 当前需求未提学科删除。但"创建新学科"流程万一失败，是否需要回滚/删除半成品？建议先不做，仅在前端标记状态。
4. **星空背景的"星星数量"与性能** — 纯 CSS radial-gradient 方案在低端设备可能卡顿。建议保留 CSS 方案但做 GPU 加速（`will-change: background-position`）。
5. **前端框架？** — 当前需求未指定前端技术栈。后端提供 API；前端建议 React + Tailwind（与 skill 示例一致）。
6. **学科预览的排序/搜索？** — 学科多时需排序（按创建时间/标题）和搜索。建议后期迭代，第一版按创建时间倒序。

---

## 四、数据流与数据入口 (Data Flow & Entry Points)

### 4.1 整体数据流

```
┌──────────┐     login      ┌──────────┐    permission    ┌───────────────┐
│  Client  │ ──────────────> │  /api/   │ ──────────────> │  User DB      │
│  (React) │ <────────────── │  Flask   │ <────────────── │  permission    │
└──────────┘   user obj +    └──────────┘                 └───────────────┘
               permission
                    │
                    │  permission = "user"  → 学科预览(学习视角)
                    │  permission = "operator" → 学科预览(管理视角) + 创建学科 + 查看进度
                    │
                    v
           ┌──────────────────┐
           │  GET /api/subjects│  (统一学科列表, 按 permission 返回不同元数据)
           └──────────────────┘
```

### 4.2 数据入口矩阵

| 入口 | 当前端点 | 变更类型 | 说明 |
|---|---|---|---|
| 用户登录 | `POST /api/user_login` | **改** | 返回值增加 `permission: "user"\|"operator"` |
| 用户注册 | `POST /api/user_register` | **改** | 新用户自动 `permission="user"`；不再写 `SyllabusPermission.USER` |
| 学科列表 | `POST /api/syllabus_list` | **改** | 移除 `manage` 参数；根据 `user_id` 的 permission 返回不同视图 |
| 终身学习全景图 | `GET /api/study_graph/detail?user_id=X` | **改** | **直接增强** `get_student_lifelong_overview()` → 以用户为中央恒星、学科为行星、知识点为环绕星体的合并 **force 图** |
| 图谱创建 | `POST /api/job_graph_create` | **改** | 加 `@require_operator` 装饰器 |
| 日历上传 | `POST /api/file_upload_calendar` | **改** | 加 `@require_operator` 装饰器；不再写 OWNER 绑定 |
| 大纲草稿构建 | `POST /api/syllabus_build_draft` | **改** | 加 `@require_operator` 装饰器 |
| 大纲增强 | `POST /api/syllabus_build` | **改** | 加 `@require_operator` 装饰器 |
| 知识填充(Job) | `POST /api/job_create` | **改** | 加 `@require_operator` 装饰器 |
| 编辑大纲 | `POST /api/syllabus_update` / `syllabus_update_draft` | **改** | 加 `@require_operator` 装饰器；`status == 'published'` 时返回 `syllabus_locked` |
| 发布学科 | *(新)* `POST /api/admin/syllabus/<id>/publish` | **新增** | operator 发布学科：校验 syllabus_path 存在 → 批量绑定所有 user → `status = 'published'` |
| 学科用户进度总览 | *(新)* `GET /api/admin/syllabus/<id>/students_progress` | **新增** | operator 查看某学科下所有学员的 StudyGraphTree 摘要 + BuddyTree regions（匿名化，card-stack 数据源） |
| 用户提权/降级 | *(新)* `POST /api/admin/set_permission` | **新增** | operator 设置某用户的 permission |

### 4.3 数据模型变更

#### User 表 (schemas/user.py)

```python
# 新增字段
permission = db.Column(db.String(50), nullable=False, default='user')
# 值: 'user' | 'operator'
```

#### Syllabus 表 (schemas/syllabus.py)

```python
# 新增字段
status = db.Column(db.String(20), nullable=False, default='draft')
# 值: 'draft' | 'published'
```

#### constant.py

```python
# 删除
class SyllabusPermission(Enum):
    USER = "user"
    OWNER = "owner"

# 新增
class UserPermission(Enum):
    USER = "user"
    OPERATOR = "operator"

class SyllabusStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
```

#### UserSyllabus 表 (schemas/user_syllabus.py)

- `syllabus_permission` 字段 **保留但不读取**（避免 DDL 变更风险）
- 所有新绑定默认值改为空字符串或直接移除 default

### 4.4 终身学习全景图 — 合并力导向图改造

**入口**：`GET /api/study_graph/detail?user_id=X`（无 syllabus_id）已路由 → `get_student_lifelong_overview()`。

**当前**：返回 `{ tree_id, type, user_id, syllabi: [{ syllabus_id, subject_title, node_count }] }` — 只有摘要。

**改造后**：直接增强为返回合并 nodes + edges，前端用 `layout="force"` 渲染：

```
user_root: { id: "user_root:{user_id}", label: "学习全景", group: "user_root",
             fx: 0, fy: 0,  radius: 18 }   ← 中央恒星，锁定不动
  ├─ forceLink → subject: { group: "chapter", radius: 12 }   ← 行星轨道
  │    ├─ forceLink (parent_of) → ⬤ mastered (radius 8, 绿, 高 opacity)
  │    ├─ forceLink (parent_of) → ◉ learning (radius 6, 蓝)
  │    └─ forceLink (parent_of) → ○ weak    (radius 4, 黄, 低 opacity)
  └─ ...
```

**合并步骤**：
1. 查询 `StudyGraphTree` 所有该用户的记录
2. 生成 user_root node（设 `fx/fy` 固化居中）
3. 对每个 tree：生成 subject node + `list_nodes(tree_id)` + `list_edges(tree_id)`
4. ID 前缀 `{syllabus_id}:` 防冲突
5. 边：`user_root → subject`（`forceLink`），及各学科内部 `parent_of` 边保持
6. 力参数：`charge: -400`, `link distance: 90`, `collision radius+8`
7. 前端 `treeResponseToGraph()` 消费，subject 节点配 `group: "chapter"` 色

**无新路由，无新方法**。仅增强现有函数的返回值结构。前端无需改 API 调用路径。

### 4.5 用户-学科生命周期 & 发布流程

**学科状态机**：

```
draft ─────[发布]─────▶ published
  │                        │
  ├ 学生不可见              ├ 学生可见 (syllabus_list)
  ├ 可编辑                  ├ 大纲锁定 (syllabus_update → 403)
  ├ 可删                    ├ 不可删
  ├ 仅 operator 可见        ├ 全员可见 (包括新注册自动绑)
  └ 无 UserSyllabus 绑定    └ 所有现有 user 均已绑定
```

**学生侧状态机** (per syllabus)：

```
新用户注册 ──▶ 遍历所有 published syllabus → 全绑 (UserSyllabus 行存在)
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │ 未进入        │ personal_syllabus_path = NULL
                                 │ isLearning=F  │
                                 └──────┬───────┘
                                        │ 点击 [进入学习] → learning_init_personal_syllabus
                                        ▼
                                 ┌──────────────┐
                                 │ 已进入        │ personal_syllabus_path 已设置
                                 │ isLearning=T  │ StudyGraphTree 空, BuddyTree 空
                                 └──────┬───────┘
                                        │ 跟 Agent 交互 → agent events
                                        ▼
                                 ┌──────────────┐
                                 │ 学习中        │ StudyGraphTree.nodes > 0
                                 │ active       │ BuddyTree 有 regions, updated_at 7d 内
                                 └──────┬───────┘
                                        │ 长时间无活动
                                        ▼
                                 ┌──────────────┐
                                 │ 沉寂          │ updated_at > 14d
                                 │ stale        │ 有 stale_topics
                                 └──────────────┘
```

**新学科上线 → 已有学生绑定**：

| 触发点 | 行为 |
|---|---|
| **发布 (publish)** | 遍历 `list_all_users_brief()` — 每个 user `create_user_syllabus(user_id, syllabus_id)` |
| **新用户注册 (register)** | 遍历 `list_all_syllabuses()` — 已包含 published 学科，自动绑 |
| **draft 阶段** | 不绑任何普通 user（仅 operator 通过 upload_calendar 绑定） |

**发布 API**：`POST /api/admin/syllabus/<id>/publish`

```
校验:
  - operator 权限
  - syllabus_path 非空（最终大纲已生成）
  - status == 'draft'（未重复发布）

执行:
  1. list_all_users_brief()
  2. 对每个 user: create_user_syllabus(user_id, syllabus_id)
  3. UPDATE syllabus SET status = 'published'
  4. 返回 { success: true, syllabus_id, bound_users: N }
```

**锁定逻辑**：

- `syllabus_update` / `syllabus_update_draft` 入口处检查 `status == 'published'` → 返回 403 `{ error_code: 'syllabus_locked' }`
- `syllabus_list` 对普通 user（`permission='user'`）：仅返回 `status='published'` 的学科
- operator 视角：返回所有学科，draft 标记 `status: 'draft'` + `bound_users: 0`

---

## 五、前端落地规范（对照 skill 源文件）

以下所有页面必须遵循 `examples/style.css` 的精确 CSS + `example-page.jsx` 的组件树结构：

### 5.0 页面骨架（所有页面通用）

```
<main className="app-shell">           ← style.css .app-shell
  <div className="space-background" /> ← 自闭合，7 层 gradient + movingStarsNear
  <section className="relative z-10 mx-auto max-w-7xl">
    <nav>...</nav>                     ← 导航在 section 内，不在外面
    ...内容...
  </section>
</main>
```

| 组件 | CSS 来源 | 关键数值 |
|---|---|---|
| 星空背景 | `style.css` `.space-background` | 7 层 gradient，`background-size` 149px–457px，48s 动画 |
| 折叠卡片堆叠 | `style.css` `.card-stack` / `.stack-card` | 收起 112px → 展开 220px，perspective 1200px |
| 卡片详情揭示 | `style.css` `.card-details` | `max-h-0 opacity-0` → `max-h-40 opacity-100` |
| 学科网格卡片 | **扩展**：基于 `.stack-card` 改平铺 grid | 复用 `rounded-[28px] border border-white bg-black` 外壳 |
| 管理表格 | SKILL.md §Tables | `max-h-[calc(100vh-330px)]` 内滚动，`font-black text-cyan-100` 表头 |
| 按钮 Primary | SKILL.md §Buttons | `rounded-full bg-cyan-300 text-zinc-950` |
| 按钮 Secondary | SKILL.md §Buttons | `rounded-full border border-white bg-black` |
| 输入框 | SKILL.md §Inputs | `rounded-2xl border border-white bg-black focus:border-cyan-200` |

### 5.0b 组件语义标签规范

| 用途 | 标签 | 参考来源 |
|---|---|---|
| 页面外壳 | `<main className="app-shell">` | example-page.jsx:7 |
| 导航 | `<nav>` | example-page.jsx:11 |
| 卡片容器（堆叠） | `<aside className="card-stack">` | example-page.jsx:30 |
| 单张卡片 | `<article className="stack-card">` | example-page.jsx:32 |
| 卡片索引/编号 | `<div>` + `text-[10px] tracking-[0.24em]` | example-page.jsx:33 |
| 学科网格容器 | `<section>` + grid classes | 扩展（skill 中无对应） |

---

## 六、界面设计 ASCII 表达

### 6.1 所有学科预览页（用户视角）

> **布局**: 参考 `example-page.jsx` 的 `md:grid-cols-[1fr_360px]`。
> 左侧学科卡片网格，右侧**终身学习全景图** — 力导向星系图，用户居中央如恒星，学科如行星环绕，
> 知识点如星体散布轨道。掌握度控制亮度和大小，与星空背景融合。

```
┌──────────────────────────────────────────────────────────────┐
│  [星空动画背景]                                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 联觉 LianJue                      [用户] [退出]        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 主区域 grid: [学科卡片 1fr] [终身学习全景图 360px] ────┐ │
│  │                                                          │ │
│  │  ┌─ 学科卡片 ──────────────────┐  ┌─ 学习星系 ────────┐ │ │
│  │  │ ┌─────────┐ ┌─────────┐    │  │ ┌────────────────┐ │ │ │
│  │  │ │📚大数据  │ │📚机器学习│    │  │ │ D3GraphViewer  │ │ │ │
│  │  │ │ 导论     │ │ 基础     │    │  │ │ layout=force   │ │ │ │
│  │  │ │ ████░░78%│ │ ██░░░ 28%│   │  │ │                │ │ │ │
│  │  │ │[进入学习]│ │[进入学习]│    │  │ │  ⬤⬤     ⬤     │ │ │ │
│  │  │ └─────────┘ └─────────┘    │  │ │    ↖  👤  ↗    │ │ │ │
│  │  │ ┌─────────┐ ┌─────────┐    │  │ │  📚  ←·→  📚  │ │ │ │
│  │  │ │📚深度学习│ │📚NLP    │    │  │ │ ╱  ○  ⬤  ◉ ╲ │ │ │ │
│  │  │ │ ...     │ │ ...     │    │  │ │⬤  ○   ◉  ⬤ ○│ │ │ │
│  │  │ └─────────┘ └─────────┘    │  │ │  ⬤    ○    ⬤  │ │ │ │
│  │  └────────────────────────────┘  │ └────────────────┘ │ │ │
│  │                                  └────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**力导向节点映射**：
| 节点 | 语义 | radius | 配色 | 说明 |
|---|---|---|---|---|
| 👤 user_root | 中央恒星 | 18 | `cyan` glow | 用户学习宇宙中心，fix 在视口中央 |
| 📚 subject | 行星 | 12 | `chapter` (靛蓝) | 围绕用户，学科间互斥 |
| ⬤ mastered | 亮星 | 8 | `#22c55e` 绿 | 高 opacity，表示已掌握 |
| ◉ learning | 中亮星 | 6 | `#3b82f6` 蓝 | 中 opacity，学习中 |
| ○ weak | 暗星 | 4 | `#f59e0b` 黄 | 低 opacity，薄弱待加强 |

**数据获取**：
- 学科卡片：`POST /api/syllabus_list {user_id}` — 现有端点
- 全景图：`GET /api/study_graph/detail?user_id=X`（无 syllabus_id）→ `get_student_lifelong_overview()` **增强版**：返回合并 nodes+edges，user_root 节点 fix 居中
- 左/右布局比例：桌面端 `1fr 360px`，移动端堆叠

**后端改动**：增强 `get_student_lifelong_overview()`，合并逻辑：
```
user_root: { id: "user_root:{user_id}", label: "学习全景", group: "user_root", fx: 0, fy: 0 }
├── subject: { id: "subject:{syllabus_id}", label: "大数据导论", group: "chapter" }
│   ├── Knowledge A (mastered, score 0.9) → force charge -400
│   ├── Knowledge B (learning, score 0.6)
│   └── Knowledge C (weak, score 0.2)
│       (parent_of edges → force link distance 90)
```
- user_root 设 `fx/fy` 固定居中，subject 用 `forceLink` 连到 user_root
- 知识节点复用 `parent_of` 边，力导向自然聚拢同科节点

### 6.2 所有学科预览页（管理员视角）

> 与用户视角同布局。差异：学科卡片显示管理信息（学员数、大纲状态），上方多 [+ 创建新学科] 按钮。
> 右侧全景图为 operator **自己的**学习全景（如 operator 也是学员）。

```
┌──────────────────────────────────────────────────────────────┐
│  [星空动画背景]                                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 🦁 LianJue   [管理面板]              [operator] [退出] │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [+ 创建新学科]  (pill: bg-cyan-300 text-zinc-950)            │
│                                                              │
│  ┌─ 主区域 grid: [学科卡片 1fr] [终身学习全景图 360px] ────┐ │
│  │                                                          │ │
│  │  ┌─ 学科卡片(管理) ────────────┐  ┌─ 学习全景图 ──────┐ │ │
│  │  │ ┌─────────┐ ┌─────────┐    │  │ (同用户视角)       │ │ │
│  │  │ │📚大数据  │ │📚ML基础  │    │  │                    │ │ │
│  │  │ │学员15人  │ │学员8人   │    │  │                    │ │ │
│  │  │ │大纲✅增强│ │大纲📝草稿│    │  │                    │ │ │
│  │  │ │[学习][管]│ │[学习][管]│    │  │                    │ │ │
│  │  │ └─────────┘ └─────────┘    │  │                    │ │ │
│  │  └────────────────────────────┘  └────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 创建新学科页（管理员）

```
┌────────────────────────────────────────────────────────────┐
│  [星空动画背景]                                             │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ← 返回学科列表       创建新学科                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─ Step 1: 初始化图谱 ──────────────────────────────────┐ │
│  │  图谱名称: [__________________]  (input: rounded-2xl)  │ │
│  │  [初始化图谱]  (secondary button)                      │ │
│  │  ✅ 图谱 "example_graph" 创建成功                       │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌─ Step 2: 上传教学日历 ────────────────────────────────┐ │
│  │  选择图谱: [下拉: example_graph ▼]                     │ │
│  │  上传校历: [选择文件] calendar.pdf                     │ │
│  │  [上传并解析]                                         │ │
│  │  ⏳ 正在解析教学日历...                                 │ │
│  │  ✅ 教学大纲草稿生成成功 — 学科 "大数据导论" 已创建！    │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌─ Step 3: 填充知识 ────────────────────────────────────┐ │
│  │  上传知识文件: [选择文件] chapter1.pdf (+ 添加更多)     │ │
│  │  [开始知识填充]  (触发 job_create)                     │ │
│  │  📊 Job #42: pdf_to_md → ⏳ md_to_triples → ...       │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌─ Step 4: 增强教学大纲 ────────────────────────────────┐ │
│  │  [生成增强大纲]  (触发 syllabus_build)                  │ │
│  │  ✅ 大纲增强完成 — 已关联 45 个知识点                    │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌─ Step 5: 发布学科 ────────────────────────────────────┐ │
│  │  确认发布后将:                                         │ │
│  │  · 绑定所有 23 名现有学生到此学科                        │ │
│  │  · 大纲锁定，不可再编辑                                 │ │
│  │  [发布]  (primary: bg-cyan-300)                        │ │
│  │  ✅ 学科 "大数据导论" 已发布！23 名学生已获得访问权限     │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

> **流程依赖**: Step 1→2→3→4 依次解锁，Step 5 在 Step 4 完成后可用。
> 发布前可反复迭代 Step 3-4。发布后返回学科列表页。

### 6.4 学科详情管理页（管理员）

> **核心设计**: 每学员 = 一组 `.card-stack`（2 张卡），每张卡内嵌 **D3 graph view**。
> 复用现有 `D3GraphViewer` 组件。默认收起仅露 StudyGraphTree graph，hover 弹开学伴 Buddy Tree graph。
>
> **两个独立维护的树**：
> | | StudyGraphTree (学习进度树) | Buddy Tree (学伴学习记录树) |
> |---|---|---|
> | **持久化** | MySQL ORM — `StudyGraphTree` + `StudyGraphNode` + `StudyGraphEdge` | 文件系统 — `study_buddy/user_{id}/syllabus_{id}/tree.json` |
> | **结构** | nodes (title/mastery_label/mastery_score) + edges (parent_of) + virtual_root | 3 regions: trunk (steps), learned (mastered nodes), explore (weak/stale nodes) |
> | **摘要** | `summary_json`: learned/mastered/weak counts + tree_growth | `regions.{trunk,learned,explore}.length` |
> | **更新** | Student Agent (`submit_learning_tree_changes`) | `proactive_buddy_message()` 对比新旧 → `save_buddy_tree()` 原子写 |
>
> **card-stack 2 层**：
> | 层 | 数据源 | 渲染 | layout | 配色 |
> |---|---|---|---|---|
> | Card 1 (顶) | `StudyGraphTree` → `treeResponseToGraph()` | `<D3GraphViewer>` | `tree` | mastered=绿 learning=蓝 weak=黄 |
> | Card 2 (底) | `BuddyTree` → `buddyRegionsToGraph()` (新) | `<D3GraphViewer>` | `force` | trunk=靛蓝 learned=绿 explore=黄 |

```
┌──────────────────────────────────────────────────────────────┐
│  [星空动画背景]                                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ← 学科列表    大数据导论    [填充知识] [编辑大纲]       │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 学员卡片网格 (grid 2-3列, max-h calc滚动) ─────────────┐ │
│  │                                                          │ │
│  │  ┌ 学员 #1 ──────────────────┐  ┌ 学员 #2 ─────────────┐│ │
│  │  │ .card-stack               │  │ .card-stack           ││ │
│  │  │ ┌────────────────────────┐│  │ ┌────────────────────┐││ │
│  │  │ │ 学习进度树   top(z2)   ││  │ │ 学习进度树          │││ │
│  │  │ │ ┌────────────────────┐ ││  │ │ ┌────────────────┐ │││ │
│  │  │ │ │  D3GraphViewer    │ ││  │ │ │ D3GraphViewer  │ │││ │
│  │  │ │ │  layout=tree      │ ││  │ │ │ layout=tree    │ │││ │
│  │  │ │ │  ●→◉→○           │ ││  │ │ │ ●→●→◉→○       │ │││ │
│  │  │ │ │  🟢 🟡           │ ││  │ │ │ 🟢🟢🟡         │ │││ │
│  │  │ │ └────────────────────┘ ││  │ │ └────────────────┘ │││ │
│  │  │ │ 已学23 掌握12 薄弱3   ││  │ │ 已学45 掌握30 薄弱2 │││ │
│  │  │ └────────────────────────┘│  │ └────────────────────┘││ │
│  │  │ ┌ hover 展开 ↓ ──────────┐│  │ ┌ hover 展开 ↓ ──────┐││ │
│  │  │ │ 学伴学习记录树 z1      ││  │ │ 学伴学习记录树      │││ │
│  │  │ │ ┌────────────────────┐ ││  │ │ ┌────────────────┐ │││ │
│  │  │ │ │  D3GraphViewer    │ ││  │ │ │ D3GraphViewer  │ │││ │
│  │  │ │ │  layout=force     │ ││  │ │ │ layout=force   │ │││ │
│  │  │ │ │  trunk─learned    │ ││  │ │ │  trunk↘learned │ │││ │
│  │  │ │ │      ↘explore     │ ││  │ │ │  →explore      │ │││ │
│  │  │ │ └────────────────────┘ ││  │ │ └────────────────┘ │││ │
│  │  │ └────────────────────────┘│  │ └────────────────────┘││ │
│  │  └───────────────────────────┘  └──────────────────────┘│ │
│  │                                                          │ │
│  │  ┌ 学员 #3 (空树) ───────────┐  ┌ 学员 #4 ─────────────┐│ │
│  │  │ .card-stack               │  │ .card-stack           ││ │
│  │  │ ┌────────────────────────┐│  │ ┌────────────────────┐││ │
│  │  │ │ 学习进度树             ││  │ │ 学习进度树          │││ │
│  │  │ │ (空图 — 未开始学习)    ││  │ │ D3GraphViewer...   │││ │
│  │  │ └────────────────────────┘│  │ └────────────────────┘││ │
│  │  │ (无第二卡)                │  │ (hover 展开学伴树)    ││ │
│  │  └───────────────────────────┘  └──────────────────────┘│ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**交互说明**：
- 默认：每组仅露 Card 1（StudyGraphTree D3 graph，tree layout），概览知识掌握拓扑
- hover：双卡展开，Card 2 下移 140px 显示 Buddy Tree graph（force layout，trunk→learned→explore 三色节点）
- 展开时 `border-cyan-200`，Card 2 由 `max-h-0 opacity-0` → `max-h-80 opacity-100`
- 空树学员无第二卡，显示 "未开始学习" 占位

**数据获取**：
- `GET /api/admin/syllabus/<id>/students_progress`
- 响应：`{ students: [{ user_index, study_graph: StudyGraphTree, buddy_tree: BuddyTree }] }`
  - `StudyGraphTree` 含 nodes + edges + summary（前端用 `treeResponseToGraph()` 转换）
  - `BuddyTree` 含 `regions: { trunk, learned, explore }`（前端新增 `buddyRegionsToGraph()` 转换为 nodes + edges）

**前端改动范围**：
| 组件 | 改动 |
|---|---|
| `D3GraphViewer` | 无（复用），可能需适配暗色主题背景 |
| `treeResponseToGraph()` | 无（复用） |
| `buddyRegionsToGraph()` | **新增**：trunk 节点串链 + learned/explore 节点按 associated_trunk 连线 |
| `AdminSubjectDetail` | **新增**：card-stack 网格 + 内嵌 D3GraphViewer（每卡 ~200px 高） |

---

## 七、基本测试计划

### 7.1 单元测试

| 编号 | 测试点 | 验证内容 |
|---|---|---|
| UT-01 | User.permission 默认值 | 新建 User 自动获得 `permission='user'` |
| UT-02 | UserPermission enum | `UserPermission.USER.value == 'user'`, `UserPermission.OPERATOR.value == 'operator'` |
| UT-03 | syllabus_permission 移除 | `list_all_syllabuses_brief_info` 不再按 syllabus_permission 过滤 |
| UT-04 | require_operator 装饰器 | user 访问 admin 端点 → 403；operator 访问 → 通过 |
| UT-05 | 注册不再写 OWNER | `register()` 调用 `create_user_syllabus` 时 permission 参数为 user 或默认 |
| UT-06 | upload_calendar 不再写 OWNER | operator 上传日历后 UserSyllabus 绑定为默认值 |
| UT-07 | Syllabus.status 默认值 | 新建 Syllabus 自动获得 `status='draft'` |
| UT-08 | SyllabusStatus enum | `SyllabusStatus.DRAFT.value == 'draft'`, `SyllabusStatus.PUBLISHED.value == 'published'` |

### 7.2 集成测试

| 编号 | 测试点 | 验证内容 |
|---|---|---|
| IT-01 | user 登录返回 permission | `POST /api/user_login` → response 包含 `permission: "user"` |
| IT-02 | operator 登录返回 permission | `POST /api/user_login` → response 包含 `permission: "operator"` |
| IT-03 | user 获取学科列表 | `POST /api/syllabus_list {user_id}` → 返回包含 `isLearning` 的学习视角数据 |
| IT-03b | user 获取终身全景图 | `GET /api/study_graph/detail?user_id=X` → 返回合并图 { root: user, nodes: [...all subjects' knowledge nodes], edges: [...] } |
| IT-04 | operator 获取学科列表 | `POST /api/syllabus_list {user_id}` → 返回包含 `user_count`、`draft_status` 的管理视角数据 |
| IT-05 | user 调用 admin 端点被拒 | user 调 `POST /api/admin/set_permission` → 403 |
| IT-06 | 创建学科完整流程 | graph_create → upload_calendar → syllabus_build_draft → job_create → syllabus_build 全部成功 |
| IT-07 | 学科未建图不能创建 | 直接调用 syllabus_build_draft 不先建 graph → 应返回明确错误（缺失 graph 信息） |
| IT-07b | 发布学科 → 批量绑定 | `POST /api/admin/syllabus/<id>/publish` → 所有现有 user 获得 UserSyllabus 绑定，status 变 published |
| IT-07c | 重复发布拒绝 | 对已 published 学科再次 publish → 返回 `already_published` |
| IT-07d | 未完成大纲不能发布 | syllabus_path 为空的学科 publish → 返回 `syllabus_incomplete` |
| IT-07e | 发布后编辑被拒 | 对 published 学科调 syllabus_update → 返回 403 `syllabus_locked` |
| IT-07f | user 只看到已发布学科 | `POST /api/syllabus_list {user_id}` → 仅返回 `status='published'` 的学科 |
| IT-07g | operator 看到全部学科 | `POST /api/syllabus_list {user_id}` → 返回所有学科含 draft，draft 标记 status + bound_users=0 |
| IT-08 | 管理员查看学员进度+学伴 | `GET /api/admin/syllabus/<id>/students_progress` → 返回匿名化学员摘要列表，含 StudyGraph 摘要 + BuddyTree regions |
| IT-09 | 空学科无学员 | `students_progress` 对无绑定学员的学科 → 返回 `students: []` |

### 7.3 回归测试

| 编号 | 测试点 | 验证内容 |
|---|---|---|
| RT-01 | 用户注册后绑定所有学科 | 新用户注册后，`UserSyllabus` 表中有所有现有学科的绑定记录 |
| RT-02 | 普通用户学习流程正常 | login → syllabus_list → learning_init_personal_syllabus → learning_personal_syllabus_detail 全链路无报错 |
| RT-03 | 学习进度树正常 | `GET /api/study_graph/detail?user_id=X&syllabus_id=Y` → 正常返回 |
| RT-04 | 学伴对话正常 | `POST /api/study_buddy/chat` → 正常返回 |
| RT-05 | 文件上传下载正常 | `POST /api/file_upload` / `GET /api/file_download` → 正常 |

### 7.4 前端验收

| 编号 | 验收点 | 标准 |
|---|---|---|
| AT-01 | 星空背景渲染 | 页面加载后可见不规则漂移星星；不卡顿 (<30% GPU) |
| AT-02 | 暗色主题一致性 | 所有新增页面：黑底、白字、cyan 强调色、pill 按钮、无毛玻璃 |
| AT-03 | 用户视角学科卡片 | 显示标题、进度条、[进入学习] 按钮；无管理按钮 |
| AT-04 | 管理员视角学科卡片 | 显示标题、学员数、大纲状态；[进入学习] + [查看/编辑学科] |
| AT-05 | 创建新学科按钮 | 仅 operator 可见，位于学科列表上方 |
| AT-06 | 创建学科分步流程 | 4 步依次解锁；前一步成功才可进行下一步 |
| AT-07 | 响应式 | 移动端单列堆叠；桌面端 grid 2-3 列；max-w-7xl 居中 |

---

## 八、实施顺序建议

```
Phase 1: 数据层（DB migration + model + enum）
  ├── schemas/user.py 加 permission 字段
  ├── schemas/syllabus.py 加 status 字段
  ├── constant.py: SyllabusPermission → UserPermission + SyllabusStatus
  └── DB migration SQL

Phase 2: 权限基础设施
  ├── utils/auth.py: require_operator 装饰器
  └── repositories/user_syllabus_repo.py: 清掉 syllabus_permission 过滤

Phase 3: 任务层清理 + 增强
  ├── tasks/user_task.py: register() 不再用 SyllabusPermission
  ├── tasks/syllabus_task.py: 清理 syllabus_permission 引用
  ├── tasks/syllabus_task.py: 新增 operator 专用查询方法
  └── tasks/study_graph/service.py: 增强 get_student_lifelong_overview() — 合并所有学科 trees 的 nodes+edges，用户为根

Phase 4: API 层
  ├── blueprint/user_api.py: login 返回 permission
  ├── blueprint/syllabus_material_api.py: syllabus_list 重构（draft 过滤 + status 字段）
  ├── blueprint/syllabus_material_api.py: syllabus_update/draft 加 syllabus_locked 检查
  ├── blueprint/knowledge_build_api.py: 加 require_operator
  ├── blueprint/admin_api.py (新): publish + set_permission + students_progress
  └── 其他蓝图加 require_operator

Phase 5: 前端
  ├── 基础样式: 直接复用 examples/style.css + 新增 LianJue 扩展样式
  ├── 星空风格基础组件 (per §5.0 骨架 + semantic 标签规范)
  ├── 学科预览页 (用户版 + 管理员版) — 学科网格卡片 + 折叠卡片堆叠
  ├── 创建新学科页 (4-step workflow: 手风琴式步骤展开)
  └── 学科详情管理页 (用户进度表 + 学伴进度表 — 表格规范)

Phase 6: 测试 & 验收
  ├── 后端单元/集成测试
  ├── 前端验收对照
  └── 回归测试
```
