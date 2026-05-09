# USER_PROFILE_SAVE_PLAN

## 1. 改前现状（改后删除）

当前画像入口是 `POST /api/user_learning_profile`，API 位于 `blueprint/user_api.py`，业务收口在 `tasks/learning_profile_task.py::build_learning_profile(...)`。

现有流程大体是：

1. API 接收 `user_id`、可选 `syllabus_id`、`dialogue_text`、`learning_goal`、`learning_records`、`answer_records`、`resource_usage`。
2. `build_learning_profile(...)` 读取用户、用户课程关系、课程标题，并构建本次运行的 `state`。
3. `run_learning_profile_agent(state)` 启动 `learning_profile_agent`。
4. Agent 通过工具顺序完成：
   - `load_history_context`
   - `load_personal_syllabus_context`
   - `normalize_events`
   - `compute_features`
   - `assemble_profile`
5. 最终画像被放在 `state["profile"]`，然后由 `build_learning_profile(...)` 直接返回给 API。

也就是说，当前画像是“即时计算结果”：

- 会读取 `history/{syllabus_id}_{user_id}.json` 作为历史问答上下文。
- 会读取 `user_syllabus.personal_syllabus_path` 指向的个人大纲 JSON。
- 会结合本次请求传入的学习记录、答题记录、资源使用记录。
- 但不会读取“上一次画像结果”。
- 也不会把本次画像写回数据库或本地 JSON。

因此你的判断基本成立：画像每次调用都会重新评估；现有实现没有本地持久化画像，也没有基于已有画像做增量更新的工具链。要做“实时更新画像”，合理落点是给 `user_syllabus` 增加 `personal_profile_path`，将画像落盘到类似 `profiles/{syllabus_id}-{user_id}.json` 的文件，再让画像 Agent 在后续运行中先读已有画像，并在最后通过 update/save tool 写回。

## 2. 阶段一：路径常量与数据库字段

### 0. 新增的常量定义

在 `constant.py::BasePath` 中新增：

```python
PERSONAL_PROFILE_ROOT = "/profiles"
```

语义：

- 基底目录为项目根目录下的 `profiles/`。
- 单个画像文件命名为 `{syllabus_id}-{user_id}.json`。
- 最终保存绝对路径到 `user_syllabus.personal_profile_path`。

### 1. 影响的文件范围

- `constant.py`
- `schemas/user_syllabus.py`
- `repositories/user_syllabus_repo.py`
- 数据库迁移脚本或 SQL 变更记录
- `profiles/.gitkeep`
- 测试侧可能需要更新 `tests/conftest.py` 的临时 JSON 清理范围

### 2. 函数级收口的完整数据流

字段层数据流：

1. 数据库为 `user_syllabus` 新增 `personal_profile_path` 字段。
2. ORM 模型 `UserSyllabus` 增加同名字段。
3. repo 层提供读取/更新该字段的函数。
4. 画像构建完成后，通过 repo 层把画像文件绝对路径写回 `user_syllabus.personal_profile_path`。
5. 后续画像构建时，通过 `list_user_syllabuses(...)` 或 `get_user_syllabus(...)` 读到该路径。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑

新增或调整：

```python
class BasePath(Enum):
    PERSONAL_PROFILE_ROOT = "/profiles"
```

输入：无。

输出：枚举值字符串 `"/profiles"`。

内部逻辑：无，作为统一路径来源，避免在业务逻辑中硬编码 `profiles`。

```python
class UserSyllabus(db.Model):
    personal_profile_path = db.Column(db.String(255), nullable=True, unique=True, default=None)
```

输入：数据库行字段。

输出：ORM 对象属性 `personal_profile_path`。

内部逻辑：保持和 `personal_syllabus_path` 一致，允许为空；是否 `unique=True` 建议沿用 `personal_syllabus_path` 的风格。

```python
def set_personal_profile_path(user_id: int, syllabus_id: int, path: str) -> Optional[UserSyllabus]
```

输入：

- `user_id`
- `syllabus_id`
- `path`：画像 JSON 绝对路径

输出：

- 成功：更新后的 `UserSyllabus`
- 失败：`None`

内部逻辑：

1. 调用 `get_user_syllabus(user_id, syllabus_id)`。
2. 如果不存在，调用 `create_user_syllabus(...)` 创建关系，并写入 `personal_profile_path`。
3. 如果存在，更新 `personal_profile_path` 并 `db.session.commit()`。
4. 异常时 rollback 并返回 `None`。

同步调整：

```python
def create_user_syllabus(..., personal_profile_path: str = None)
```

输入新增 `personal_profile_path`。

输出仍为 `UserSyllabus`。

内部逻辑：创建新关系或更新已有关系时，同时处理 `personal_profile_path`。

### 4. 测试用例的构建描述

新增 repo/模型层测试：

- 给已有 `UserSyllabus` 调用 `set_personal_profile_path(...)`，断言字段被更新。
- 给不存在的 user-syllabus 关系调用 `set_personal_profile_path(...)`，断言关系被创建且路径写入。
- `create_user_syllabus(...)` 传入 `personal_profile_path` 时，断言不会影响既有 `personal_syllabus_path` 行为。

数据库迁移验证：

- 本地空库建表后确认 `user_syllabus.personal_profile_path` 存在。
- 老数据迁移后该字段允许为空，不阻塞现有个人大纲流程。

## 3. 阶段二：画像文件路径与读写工具函数

### 0. 新增的常量定义

复用阶段一新增的：

```python
BasePath.PERSONAL_PROFILE_ROOT
```

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `repositories/user_syllabus_repo.py`
- `constant.py`
- `tests/test_learning_profile_toolchain.py`
- `tests/test_learning_profile.py`

### 2. 函数级收口的完整数据流

路径与文件数据流：

1. `build_learning_profile(...)` 根据 `user_id + syllabus_id` 确定画像 scope。
2. `_resolve_personal_profile_path(user_id, syllabus_id)` 生成本地画像路径。
3. `_load_existing_profile(user_id, syllabus_id)` 优先读取 `user_syllabus.personal_profile_path`，没有时回退到约定路径。
4. Agent 在 `load_existing_profile_context` 工具中把已有画像放入 `state["existing_profile"]`。
5. 最终画像完成后，`save_or_update_profile` 工具写入 JSON 文件。
6. 写入成功后，repo 层把绝对路径更新到 `user_syllabus.personal_profile_path`。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑

```python
def _profile_root_dir() -> str
```

输入：无。

输出：项目根目录下 `profiles` 的绝对路径。

内部逻辑：

1. 读取 `BasePath.PERSONAL_PROFILE_ROOT.value`。
2. 去掉前导 `/`，通过 `os.path.join(os.getcwd(), ...)` 生成跨平台路径。
3. 返回绝对路径。

```python
def _build_personal_profile_path(user_id: int, syllabus_id: int) -> str
```

输入：

- `user_id`
- `syllabus_id`

输出：

- `profiles/{syllabus_id}-{user_id}.json` 的绝对路径

内部逻辑：

1. 调用 `_profile_root_dir()`。
2. 确保目录存在。
3. 返回 `os.path.abspath(os.path.join(root, f"{syllabus_id}-{user_id}.json"))`。

```python
def _load_existing_profile(user_id: int, syllabus_id: Optional[int]) -> tuple[Optional[dict], Optional[str]]
```

输入：

- `user_id`
- `syllabus_id`

输出：

- `(profile_dict, profile_path)`
- 无已有画像时返回 `(None, candidate_path_or_none)`

内部逻辑：

1. 如果没有 `syllabus_id`，不做课程级画像持久化，返回 `(None, None)`。
2. 通过 `get_user_syllabus(user_id, syllabus_id)` 获取关系行。
3. 如果行内有 `personal_profile_path` 且文件存在，读取 JSON。
4. 如果 DB 路径不存在或文件无效，回退到 `_build_personal_profile_path(user_id, syllabus_id)`。
5. 若回退路径文件存在且是 dict，则读取。
6. 读取失败不抛出，返回空画像，让主流程继续实时生成。

```python
def _save_personal_profile(user_id: int, syllabus_id: int, profile: dict) -> Optional[str]
```

输入：

- `user_id`
- `syllabus_id`
- `profile`

输出：

- 成功：画像 JSON 绝对路径
- 失败：`None`

内部逻辑：

1. 校验 `profile` 是 dict。
2. 调用 `_build_personal_profile_path(...)`。
3. 给保存对象补充持久化元信息，例如：
   - `profile_schema_version`
   - `profile_path`
   - `saved_at`
   - `previous_updated_at`，如果存在旧画像
4. 使用 UTF-8、`ensure_ascii=False`、`indent=2` 写入 JSON。
5. 调用 `set_personal_profile_path(user_id, syllabus_id, abs_path)`。
6. 成功返回绝对路径，失败返回 `None`。

### 4. 测试用例的构建描述

新增文件读写层测试：

- 无 `personal_profile_path` 时，`_load_existing_profile(...)` 返回空画像和约定路径。
- DB 有路径且文件存在时，能读出已有画像。
- DB 路径坏掉但约定路径存在时，能回退读取。
- `_save_personal_profile(...)` 能创建 `profiles/{syllabus_id}-{user_id}.json`，JSON 内容包含核心画像字段。
- `_save_personal_profile(...)` 写入后会调用 `set_personal_profile_path(...)`。

测试注意：

- `tests/conftest.py` 需要把 `profiles/` 加入测试 JSON 清理目录，避免测试污染本地持久化文件。

## 4. 阶段三：Agent 工具链接入已有画像与保存画像

### 0. 新增的常量定义

本阶段不新增常量，继续复用：

```python
BasePath.PERSONAL_PROFILE_ROOT
```

### 1. 影响的文件范围

- `tasks/learning_profile_task.py`
- `docs/learning_profile_agent_workflow.md`
- `tests/test_learning_profile_toolchain.py`
- `tests/test_learning_profile_agent_choice.py`
- `tests/test_learning_profile.py`

### 2. 函数级收口的完整数据流

Agent 数据流调整为：

1. `build_learning_profile(...)` 初始化 `state` 时加入：
   - `existing_profile`
   - `existing_profile_path`
   - `existing_profile_loaded`
   - `profile_saved`
   - `profile_path`
2. Agent 先调用 `load_existing_profile_context`。
3. 再调用既有上下文工具：
   - `load_history_context`
   - `load_personal_syllabus_context`
4. 再归一化、算特征、组装画像。
5. `assemble_profile` 内部或后置 `save_or_update_profile` 工具将已有画像与新画像合并后保存。
6. `build_learning_profile(...)` 返回保存后的最新画像，并可在 profile 中带上 `profile_path`。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑

新增 Agent tool：

```python
def _tool_load_existing_profile_context(state: Dict[str, Any]) -> Dict[str, Any]
```

输入：

- `state["user_id"]`
- `state["syllabus_id"]`

输出：

```python
{
    "tool": "load_existing_profile_context",
    "has_existing_profile": bool,
    "profile_path": str | None,
    "existing_updated_at": int | None
}
```

内部逻辑：

1. 调用 `_load_existing_profile(...)`。
2. 写入：
   - `state["existing_profile"]`
   - `state["existing_profile_path"]`
   - `state["existing_profile_loaded"] = True`
3. 不存在旧画像时也标记 loaded，避免重复调用。

新增合并函数：

```python
def _merge_profile_update(existing_profile: Optional[dict], new_profile: dict) -> dict
```

输入：

- `existing_profile`
- `new_profile`

输出：

- 合并后的 profile dict

内部逻辑建议：

1. 新画像作为主版本，因为它来自最新事件和个人大纲状态。
2. 旧画像只补充新画像没有的信息，或作为元信息保留：
   - `previous_profile_updated_at`
   - `previous_confidence`
   - `profile_revision`
3. 对数组字段保持新画像优先：
   - `concept_gaps`
   - `resource_preference`
   - `recent_anomaly`
   - `evidence`
4. 对统计字段保持新画像优先：
   - `knowledge_mastery`
   - `dropout_risk`
   - `signals`
5. 如果需要真正增量，可在后续版本把 `existing_profile["signals"]` 作为衰减先验加入 `_compute_learning_profile_bundle(...)`，但第一版建议先做“读旧画像 + 新证据重算 + 版本化写回”。

新增 Agent tool：

```python
def _tool_save_or_update_profile(state: Dict[str, Any]) -> Dict[str, Any]
```

输入：

- `state["profile"]`
- `state["existing_profile"]`
- `state["user_id"]`
- `state["syllabus_id"]`

输出：

```python
{
    "tool": "save_or_update_profile",
    "saved": bool,
    "profile_path": str | None,
    "profile_revision": int | None
}
```

内部逻辑：

1. 如果没有 `syllabus_id`，不保存课程级画像，返回 `saved=False`。
2. 如果没有 `state["profile"]`，先调用 `_tool_assemble_profile(state)`。
3. 调用 `_merge_profile_update(...)` 生成最终画像。
4. 调用 `_save_personal_profile(...)`。
5. 保存成功后写入：
   - `state["profile"]`
   - `state["profile_path"]`
   - `state["profile_saved"] = True`
6. 保存失败时不影响 API 返回，但结果中应保留 `profile_saved=False` 以便日志定位。

调整 Agent 注册：

```python
@agent.tool(sequential=True)
def load_existing_profile_context(...)

@agent.tool(sequential=True)
def save_or_update_profile(...)
```

调整 `_build_learning_profile_tool_prompt(...)`：

- 可用工具新增：
  - `load_existing_profile_context`
  - `save_or_update_profile`
- 决策规则新增：
  - 如果 `syllabus_id` 存在且尚未读取旧画像，优先读取旧画像。
  - 如果 `profile` 已完成但尚未保存，调用 `save_or_update_profile`。
  - 保存完成后再 finalize。

调整 `_fallback_next_learning_profile_tool(state)`：

```python
if state.get("syllabus_id") is not None and not state.get("existing_profile_loaded"):
    return {"action": "tool", "tool_name": "load_existing_profile_context", ...}
...
if state.get("profile") and state.get("syllabus_id") is not None and not state.get("profile_saved"):
    return {"action": "tool", "tool_name": "save_or_update_profile", ...}
```

### 4. 测试用例的构建描述

工具链测试：

- `test_learning_profile_toolchain_builds_profile_without_llm` 增加保存工具调用，断言：
  - `state["profile_saved"] is True`
  - `state["profile_path"]` 指向 `profiles/{syllabus_id}-{user_id}.json`
  - 文件内容中的 `user_id`、`syllabus_id`、`confidence` 正确。

Agent 选择测试：

- 当 `syllabus_id` 存在且 `existing_profile_loaded=False`，fallback 选择 `load_existing_profile_context`。
- 当 `profile` 已存在但 `profile_saved=False`，fallback 选择 `save_or_update_profile`。
- 当无 `syllabus_id` 时，fallback 不选择保存工具，保持兼容全局画像即时返回。

回归测试：

- mock agent 手动调用完整工具链：
  - load existing
  - load history
  - load personal syllabus
  - normalize
  - compute
  - assemble
  - save/update
- 断言 API 返回仍包含 `profile`，且 profile 内新增 `profile_path` 不破坏原字段。

## 5. 阶段四：API 返回与下游消费约定

### 0. 新增的常量定义

本阶段不新增常量。

### 1. 影响的文件范围

- `blueprint/user_api.py`
- `tasks/learning_profile_task.py`
- `docs/learning_profile_agent_workflow.md`
- 前端或总 Agent 调用文档

### 2. 函数级收口的完整数据流

API 数据流：

1. 调用方仍请求 `POST /api/user_learning_profile`。
2. `build_learning_profile(...)` 返回最新画像。
3. 如果 `syllabus_id` 存在，返回的画像应该已经写入本地文件。
4. API 响应中可以继续只返回 `profile`，也可以显式增加：
   - `profile_path`
   - `profile_saved`

建议保持向后兼容：

```json
{
  "success": true,
  "profile": {},
  "profile_path": "...",
  "profile_saved": true,
  "error_message": "",
  "error_code": ""
}
```

如果不想改响应顶层结构，也可以只把 `profile_path` 和 `profile_saved` 放入 `profile` 内部。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑

```python
def build_learning_profile(...) -> Optional[dict]
```

输入保持不变。

输出：

- 原先：画像 dict 或 `None`
- 调整后：画像 dict 或 `None`，当 `syllabus_id` 存在且保存成功时，画像内包含：
  - `profile_path`
  - `profile_saved`
  - `profile_revision`

内部逻辑：

1. 初始化 state 时加入画像持久化字段。
2. agent 完成后优先返回 `state["profile"]`。
3. 如果 agent 没有调用保存工具，但已有 `state["profile"]` 且存在 `syllabus_id`，可以在函数尾部兜底调用 `_tool_save_or_update_profile(state)`，避免模型漏调工具导致没有持久化。
4. 如果保存失败，仍返回实时画像，但 `profile_saved=False`。

```python
def user_learning_profile_api()
```

输入保持不变。

输出建议新增顶层字段：

- `profile_path`
- `profile_saved`

内部逻辑：

1. 调用 `build_learning_profile(...)`。
2. 从返回的 `profile` 中取 `profile_path/profile_saved`。
3. 保持旧的 `profile` 返回结构不变。

### 4. 测试用例的构建描述

API 测试：

- 有 `syllabus_id` 时调用 `/api/user_learning_profile`，断言：
  - `success=True`
  - `profile` 非空
  - `profile.profile_saved=True`
  - 文件存在
  - DB 中 `personal_profile_path` 被更新
- 无 `syllabus_id` 时调用接口，断言：
  - 仍可返回画像
  - 不创建课程级画像文件
  - 不要求更新 `user_syllabus`
- 保存失败时，mock `_save_personal_profile` 返回 `None`，断言：
  - API 仍返回 `success=True`
  - `profile_saved=False`
  - 不影响即时画像结果

## 6. 阶段五：文档、兼容性与清理

### 0. 新增的常量定义

本阶段不新增常量。

### 1. 影响的文件范围

- `docs/learning_profile_agent_workflow.md`
- `README.md` 中如有接口索引则同步更新
- `USER_PROFILE_SAVE_PLAN.md`

### 2. 函数级收口的完整数据流

文档数据流：

1. 记录画像从“即时计算”升级为“课程级持久化快照 + 实时更新”。
2. 说明 `personal_profile_path` 与 `personal_syllabus_path` 的职责区别：
   - `personal_syllabus_path`：课程周次/能力进度状态。
   - `personal_profile_path`：画像汇总、偏好、风险、知识掌握与证据。
3. 说明总 Agent 后续只需要牵动 `/api/user_learning_profile` 或内部 `build_learning_profile(...)`，即可刷新画像。

### 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑

文档需要明确：

```text
输入：新一轮学习行为、问答、答题、资源使用或个人大纲变化
处理：读取旧画像 + 读取上下文 + 计算新画像 + 合并元信息 + 写回 profile JSON
输出：最新 profile dict + profile_path
```

对外约定：

- `profiles/{syllabus_id}-{user_id}.json` 是课程级用户画像快照。
- 每次画像 Agent 被调用都会尝试刷新该文件。
- 如果调用方没有传 `syllabus_id`，则保持即时画像行为，不做课程级保存。

### 4. 测试用例的构建描述

最终回归测试建议：

- 运行 `pytest tests/test_learning_profile.py tests/test_learning_profile_toolchain.py tests/test_learning_profile_agent_choice.py`。
- 如新增 repo 测试，补充运行对应文件。
- 手动检查：
  - `profiles/` 目录会按需创建。
  - 文件名为 `{syllabus_id}-{user_id}.json`。
  - `user_syllabus.personal_profile_path` 存的是绝对路径。
  - 重复调用同一个用户课程时，旧文件被更新而不是创建多份。

实现完成后，删除本计划第一节“改前现状（改后删除）”，并把剩余内容收束为最终实现说明或迁移记录。
