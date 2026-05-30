# Learning Profile Facade Refactor Plan

本文档是临时实施计划，用于把 `tasks/learning_profile_task.py` 拆成外层门面和包内实现。目标不是改业务行为，而是降低画像构建、个人大纲维护、Agent 工具链之间的耦合。

最终目标结构：

```text
tasks/learning_profile_task.py
tasks/learning_profile/
  service.py
  personal_syllabus.py
  agent_runtime.py
  agent_tools.py
  alignment.py
  profile_builder.py
  storage.py
  models.py
  __init__.py
```

外部模块和 API 统一从 `tasks.learning_profile_task` 调用。包内文件只承载实现细节。

## Phase 1: 下沉个人大纲维护

### 0. 新增的常量定义

不新增常量。

继续使用现有常量：

- `BasePath.PERSONAL_SYLLABUS_ROOT`
- `PersonalSyllabus.PROGRESS_MAX`
- `PersonalSyllabus.PROGRESS_MIN`
- `ProfilePersonalSyllabusSuggestionSource`
- `ProfilePersonalSyllabusSuggestionThreshold`

### 1. 影响的文件范围

新增：

```text
tasks/learning_profile/personal_syllabus.py
```

修改：

```text
tasks/learning_profile_task.py
tasks/learning_profile/__init__.py
tests/test_profile_personal_syllabus_tools.py
tests/test_profile_personal_syllabus_full_chain.py
tests/test_learning_profile.py
tests/test_learning_profile_toolchain.py
tasks/learning_task.py
```

原则：

- `learning_profile_task.py` 继续导出个人大纲相关公共函数。
- 真实实现移动到 `tasks.learning_profile.personal_syllabus`。
- 现有外部调用方不直接改到包内实现，除非测试需要 monkeypatch 内部细节。

### 2. 函数级收口的完整数据流

个人大纲初始化：

```text
learning_task / learning_profile_task
  -> init_profile_personal_syllabus(user_id, syllabus_id)
     -> personal_syllabus.init_profile_personal_syllabus
        -> get_syllabus_by_id
        -> load_json_file(syllabus.syllabus_path)
        -> build default personal syllabus period
        -> write schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json
        -> set_personal_syllabus_path
        -> return personal_syllabus bundle
```

个人大纲读取：

```text
learning_task / learning_profile_task / Agent tool
  -> read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
     -> personal_syllabus.read_profile_personal_syllabus
        -> get_user_syllabus
        -> load_json_file(personal_syllabus_path)
        -> optionally hydrate from original syllabus JSON
        -> return personal_syllabus dict
```

画像建议更新个人大纲：

```text
Learning Profile Agent / tests / learning_task
  -> append_profile_personal_syllabus_suggestion(user_id, syllabus_id, suggestion)
     -> normalize_profile_personal_syllabus_suggestion
     -> read_profile_personal_syllabus
     -> init_profile_personal_syllabus if missing
     -> append suggested_competance_list and suggestion_history
     -> maybe_apply_profile_personal_syllabus_progress
     -> write personal syllabus JSON
     -> return applied/update summary
```

### 3. 精确到输入输出的函数级收口

#### `read_profile_personal_syllabus(user_id: int, syllabus_id: int, hydrate: bool = True) -> dict | None`

输入：

- `user_id`
- `syllabus_id`
- `hydrate`: 是否用原始 syllabus 补齐 `content/enhanced_content/importance`

输出：

- 成功：个人大纲 JSON dict
- 失败：`None`

内部逻辑：

- 校验 `user_id/syllabus_id` 为正整数。
- 读取 `user_syllabus.personal_syllabus_path`。
- 路径不存在或 JSON 非 dict 时返回 `None`。
- `hydrate=True` 时调用 `_hydrate_profile_personal_syllabus(...)`。

#### `init_profile_personal_syllabus(user_id: int, syllabus_id: int) -> dict | None`

输入：

- `user_id`
- `syllabus_id`

输出：

```json
{
  "personal_syllabus_path": "...",
  "personal_syllabus": {}
}
```

失败返回 `None`。

内部逻辑：

- 读取原始 syllabus JSON。
- 从 `period` 生成个人大纲 `period`。
- 每个 week 初始化：
  - `competance = "none"`
  - `competance_progress = 0`
  - `suggested_competance_list = []`
  - `suggestion_review_count = 0`
  - `suggestion_history = []`
  - `updated_at = 0`
- 写入 `schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json`。
- 调用 `set_personal_syllabus_path` 绑定 DB 路径。

#### `normalize_profile_personal_syllabus_suggestion(suggestion: dict, default_source: str = "profile_agent") -> dict | None`

输入：

```json
{
  "week_index": 1,
  "suggested_competance": "weak",
  "confidence": 0.72,
  "reason": "...",
  "evidence": [],
  "source": "profile_agent"
}
```

输出：

- 标准化 suggestion dict
- 低置信度、非法 week、非法 competance 返回 `None`

内部逻辑：

- `week_index` 转正整数。
- `suggested_competance` 归一化到：
  - `weak_far`
  - `weak`
  - `normal`
  - `master`
  - `master_far`
- `confidence` 使用 `alignment.clip`。
- 小于 `ProfilePersonalSyllabusSuggestionThreshold.CONFIDENCE_MIN` 时拒绝。
- `evidence` 统一为 list[str]。
- 补 `source` 和 `created_at`。

#### `append_profile_personal_syllabus_suggestion(user_id: int, syllabus_id: int, suggestion: dict) -> dict | None`

输入：

- `user_id`
- `syllabus_id`
- suggestion dict

输出：

```json
{
  "personal_syllabus": {},
  "personal_syllabus_path": "...",
  "suggestion": {},
  "applied": false,
  "week_index": 1,
  "suggestion_review_count": 1,
  "competance": "weak",
  "competance_progress": 0
}
```

失败返回 `None`。

内部逻辑：

- 标准化 suggestion。
- 读取个人大纲，不存在则初始化。
- 定位 `week_index`。
- 追加：
  - `suggested_competance_list`
  - `suggestion_history`
  - `suggestion_review_count`
- 控制 `suggestion_history` 最大长度。
- 达到 `WEEK_REVIEW_THRESHOLD` 后调用 `maybe_apply_profile_personal_syllabus_progress`。
- 写回个人大纲 JSON。

#### `maybe_apply_profile_personal_syllabus_progress(personal_syllabus: dict, week_index: int) -> tuple[dict, bool]`

输入：

- personal syllabus dict
- `week_index`

输出：

- 更新后的 personal syllabus
- 是否实际推进 competance

内部逻辑：

- 未达到 `WEEK_REVIEW_THRESHOLD` 时不更新。
- 对 `suggested_competance_list` 求平均分。
- 用 `profile_builder.level_from_score` 得到建议等级。
- 调用 `_apply_profile_personal_syllabus_level`。
- 清空 suggestion 累积列表和 review count。

### 4. 测试用例的构建描述

继续使用并微调：

```text
tests/test_profile_personal_syllabus_tools.py
tests/test_profile_personal_syllabus_full_chain.py
```

覆盖：

- `read_profile_personal_syllabus` 只读，不创建文件。
- `init_profile_personal_syllabus` 根据原始 syllabus 生成默认个人大纲。
- 低置信度 suggestion 被拒绝。
- suggestion history 追加并保留最大长度。
- 达到阈值后推进 `competance/competance_progress`。
- `learning_task` 仍通过 `learning_profile_task` 门面调用个人大纲入口。

运行命令：

```bash
python -m pytest -q tests/test_profile_personal_syllabus_tools.py tests/test_profile_personal_syllabus_full_chain.py -m "not llm"
```

## Phase 2: 下沉 Agent tools

### 0. 新增的常量定义

不新增常量。

### 1. 影响的文件范围

新增：

```text
tasks/learning_profile/agent_tools.py
```

修改：

```text
tasks/learning_profile_task.py
tasks/learning_profile/agent_runtime.py
tests/test_learning_profile_toolchain.py
tests/test_learning_profile.py
tests/test_learning_profile_agent_choice.py
```

### 2. 函数级收口的完整数据流

```text
run_learning_profile_agent(state)
  -> get_learning_profile_agent()
     -> registered pydantic-ai tools
        -> agent_tools.tool_load_existing_profile_context
        -> agent_tools.tool_load_history_context
        -> agent_tools.tool_load_personal_syllabus_context
        -> agent_tools.tool_normalize_events
        -> agent_tools.tool_compute_features
        -> agent_tools.tool_assemble_profile
        -> agent_tools.tool_save_or_update_profile
  -> state is mutated by tools
  -> LearningProfileResult
```

### 3. 精确到输入输出的函数级收口

#### `tool_load_existing_profile_context(state: dict) -> dict`

输入：

- `state.user_id`
- `state.syllabus_id`

输出：

```json
{
  "tool": "load_existing_profile_context",
  "has_existing_profile": true,
  "profile_path": "...",
  "existing_updated_at": 1760000000
}
```

内部逻辑：

- 调用 `load_existing_profile`。
- 写入：
  - `state.existing_profile`
  - `state.existing_profile_path`
  - `state.existing_profile_loaded`

#### `tool_load_history_context(state: dict) -> dict`

输入：

- `state.user_id`
- `state.syllabus_id`

输出：

```json
{
  "tool": "load_history_context",
  "history_count": 0,
  "has_history": false
}
```

内部逻辑：

- 调用 service 层 `collect_history_entries`。
- 写入 `state.history_entries/history_loaded`。

#### `tool_load_personal_syllabus_context(state: dict) -> dict`

输入：

- `state.user_id`
- `state.syllabus_id`
- `state.profile_scope`

输出：

```json
{
  "tool": "load_personal_syllabus_context",
  "personal_syllabus_count": 1,
  "initialized": false
}
```

内部逻辑：

- 调用 service 层 `load_personal_syllabus_rows`。
- 若指定课程但个人大纲缺失，调用 `personal_syllabus.init_profile_personal_syllabus`。
- 写入 `state.loaded_personal_syllabuses/personal_syllabus_loaded`。

#### `tool_normalize_events(state: dict) -> dict`

输入：

- `history_entries`
- `learning_records`
- `answer_records`
- `resource_usage`
- `dialogue_texts`

输出：

```json
{
  "tool": "normalize_events",
  "event_counts": {
    "history_events": 0,
    "learning_events": 0,
    "answer_events": 0,
    "resource_events": 0,
    "all_events": 0
  }
}
```

内部逻辑：

- 调用 `alignment.normalize_*`。
- 写入 `state.normalized_events`。

#### `tool_compute_features(state: dict) -> dict`

输入：

- `state.normalized_events`
- `state.loaded_personal_syllabuses`
- `state.learning_goal`
- `state.dialogue_texts`
- `state.profile_scope`

输出：

```json
{
  "tool": "compute_features",
  "confidence": 0.68,
  "overall_score": 0.43,
  "feature_count": 20
}
```

内部逻辑：

- 调用 `profile_builder.compute_learning_profile_bundle`。
- 允许缺失 normalized events 时自动补 normalize。
- 写入 `state.feature_bundle`。

#### `tool_assemble_profile(state: dict) -> dict`

输入：

- `state.feature_bundle`

输出：

```json
{
  "tool": "assemble_profile",
  "profile_ready": true,
  "profile_keys": 30
}
```

内部逻辑：

- 从 `feature_bundle.profile` 取最终画像。
- 生成 `suggested_personal_syllabus_updates`。
- 写入 `state.profile`。

#### `tool_save_or_update_profile(state: dict) -> dict`

输入：

- `state.profile`
- `state.existing_profile`
- `state.syllabus_id`

输出：

```json
{
  "tool": "save_or_update_profile",
  "saved": true,
  "profile_path": "profiles/29-20.json",
  "profile_revision": 2
}
```

内部逻辑：

- 无 `syllabus_id` 时不保存。
- 调用 `merge_profile_update`。
- 调用 `storage.save_personal_profile`。
- 写入 `state.profile/profile_path/profile_saved`。

### 4. 测试用例的构建描述

继续使用并调整 monkeypatch 位置：

```text
tests/test_learning_profile_toolchain.py
tests/test_learning_profile.py
tests/test_learning_profile_agent_choice.py
```

覆盖：

- fake agent 按工具顺序调用。
- 各 tool 修改 state 的字段不变。
- fallback next tool 逻辑不变。
- 保存 profile 时 revision/路径行为不变。
- 真实 Agent opt-in 测试仍能调度 expected tools。

运行命令：

```bash
python -m pytest -q tests/test_learning_profile.py tests/test_learning_profile_toolchain.py -m "not llm"
RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py -m llm
```

## Phase 3: 下沉 Agent runtime

### 0. 新增的常量定义

不新增常量。

### 1. 影响的文件范围

新增：

```text
tasks/learning_profile/agent_runtime.py
```

修改：

```text
tasks/learning_profile_task.py
tasks/learning_profile/agent_tools.py
tests/test_learning_profile_toolchain.py
tests/test_learning_profile_agent_choice.py
```

### 2. 函数级收口的完整数据流

```text
build_learning_profile(...)
  -> service initializes state
  -> agent_runtime.run_learning_profile_agent(state)
     -> agent_runtime.get_learning_profile_agent()
        -> pydantic-ai Agent with tools from agent_tools
     -> Agent tool-calling
     -> LearningProfileResult
```

### 3. 精确到输入输出的函数级收口

#### `get_learning_profile_agent() -> Agent`

输入：

- 无显式输入。
- 读取 `OPENAI_COMPAT_MODEL_CONFIGS["text"]`。

输出：

- pydantic-ai `Agent`

内部逻辑：

- 调用 `_build_learning_profile_model`。
- 注册 tools：
  - `load_existing_profile_context`
  - `load_history_context`
  - `load_personal_syllabus_context`
  - `read_personal_syllabus`
  - `init_personal_syllabus`
  - `normalize_events`
  - `compute_features`
  - `assemble_profile`
  - `save_or_update_profile`
- 保留 `@lru_cache(maxsize=1)`。

#### `run_learning_profile_agent(state: dict) -> LearningProfileResult`

输入：

- 已初始化的 Agent state。

输出：

```json
{
  "success": true,
  "profile": {},
  "error_message": "",
  "error_code": ""
}
```

内部逻辑：

- 构造 `LearningProfileDeps(state=state)`。
- 调用 `agent.run_sync(_build_learning_profile_user_prompt(state), deps=deps)`。
- 把 `result.output` 写入 `state.agent_output`。
- 返回 `result.output`。

#### `fallback_next_learning_profile_tool(state: dict) -> dict`

输入：

- 当前 state。

输出：

```json
{
  "action": "tool",
  "tool_name": "normalize_events",
  "reason": "fallback normalize events"
}
```

内部逻辑：

- 根据 state 中的 loaded/ready/saved 标记返回下一步。
- 作为测试和兜底调度逻辑保留。

### 4. 测试用例的构建描述

重点调整：

- `tests/test_learning_profile_toolchain.py` 中 `_build_learning_profile_model` monkeypatch 改到 `tasks.learning_profile.agent_runtime`。
- `get_learning_profile_agent.cache_clear()` 改到 runtime 模块或由门面转发。
- Agent choice 测试继续从门面调用 `build_learning_profile`，但内部 trace patch 改到 `agent_runtime/agent_tools`。

运行命令：

```bash
python -m pytest -q tests/test_learning_profile_toolchain.py -m "not llm"
RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py -m llm
```

## Phase 4: 下沉 service 并收敛外层门面

### 0. 新增的常量定义

不新增常量。

### 1. 影响的文件范围

新增：

```text
tasks/learning_profile/service.py
```

修改：

```text
tasks/learning_profile_task.py
tasks/learning_profile/__init__.py
tasks/personal_recommendation/service.py
tasks/learning_task.py
tests/test_learning_profile.py
tests/test_learning_profile_input_variants.py
tests/test_learning_profile_api.py
tests/test_learning_profile_toolchain.py
tests/test_profile_personal_syllabus_full_chain.py
```

### 2. 函数级收口的完整数据流

读取缓存画像：

```text
get_or_build_learning_profile(...)
  -> service.get_or_build_learning_profile
     -> get_persisted_learning_profile if syllabus_id and not refresh
     -> build_learning_profile if miss
```

构建画像：

```text
build_learning_profile(...)
  -> service.build_learning_profile
     -> get_user_by_id
     -> list_user_syllabuses
     -> build profile_scope
     -> initialize state
     -> if syllabus_id: agent_tools.tool_load_existing_profile_context
     -> agent_runtime.run_learning_profile_agent
     -> save profile fallback if needed
     -> return state.profile
```

外部门面：

```text
tasks.learning_profile_task
  -> imports and re-exports service / personal_syllabus / agent_runtime public entries
```

### 3. 精确到输入输出的函数级收口

#### `get_persisted_learning_profile(user_id: int, syllabus_id: int) -> dict | None`

输入：

- `user_id`
- `syllabus_id`

输出：

- 命中：profile dict，带：
  - `profile_path`
  - `profile_saved = True`
  - `profile_refreshed = False`
- 未命中：`None`

内部逻辑：

- 调用 `load_existing_profile`。
- 校验 `profile_has_required_identity`。

#### `collect_history_entries(user_id: int, syllabus_id: int | None = None) -> list[dict]`

输入：

- `user_id`
- 可选 `syllabus_id`

输出：

- history entry list

内部逻辑：

- 指定 syllabus 时读取 `history/{syllabus_id}_{user_id}.json`。
- 未指定时扫描 `history/*_{user_id}.json`。
- 只返回 dict item。

#### `load_personal_syllabus_rows(user_id: int, syllabus_id: int | None = None) -> list[tuple[int, dict, dict]]`

输入：

- `user_id`
- 可选 `syllabus_id`

输出：

```python
[(syllabus_id, personal_syllabus_json, original_syllabus_json)]
```

内部逻辑：

- 从 `list_user_syllabuses` 读取课程绑定。
- 读取 `personal_syllabus_path`。
- 读取原始 `syllabus_path`。
- 过滤非法 JSON。

#### `build_learning_profile(...) -> dict | None`

输入：

```python
build_learning_profile(
    user_id: int,
    syllabus_id: int | None = None,
    dialogue_text: Any = None,
    learning_goal: str | None = None,
    learning_records: Any = None,
    answer_records: Any = None,
    resource_usage: Any = None,
)
```

输出：

- profile dict
- 用户不存在返回 `None`

内部逻辑：

- 读取用户和课程绑定。
- 构造 `profile_scope`。
- 初始化 Agent state。
- 运行 Learning Profile Agent。
- 如果 Agent 没保存但有 `syllabus_id`，兜底保存。

#### `get_or_build_learning_profile(...) -> dict | None`

输入：

同 `build_learning_profile`，增加：

- `refresh_profile: bool = False`

输出：

- persisted profile 或新构建 profile

内部逻辑：

- `refresh_profile=False` 且有 `syllabus_id` 时优先读缓存。
- 未命中或强刷时调用 `build_learning_profile`。
- 新构建结果标记 `profile_refreshed=True`。

### 4. 测试用例的构建描述

继续使用：

```text
tests/test_learning_profile.py
tests/test_learning_profile_input_variants.py
tests/test_learning_profile_api.py
tests/test_learning_profile_toolchain.py
tests/test_profile_personal_syllabus_full_chain.py
tests/test_profile_personal_syllabus_tools.py
```

测试重点：

- 外部仍可 `from tasks import learning_profile_task as lpt`。
- `user_api` 仍只 patch `get_or_build_learning_profile`。
- `personal_recommendation.service` 仍从门面调用 `get_or_build_learning_profile`。
- `learning_task` 仍从门面调用个人大纲入口。
- 缓存读取路径不触发 Agent。
- refresh 强制重建。
- 无 `syllabus_id` 时不保存 profile。
- 有 `syllabus_id` 时 profile 保存路径和 DB path 写回不变。

运行命令：

```bash
python -m pytest -q \
  tests/test_learning_profile.py \
  tests/test_learning_profile_input_variants.py \
  tests/test_learning_profile_api.py \
  tests/test_learning_profile_toolchain.py \
  tests/test_profile_personal_syllabus_tools.py \
  tests/test_profile_personal_syllabus_full_chain.py \
  -m "not llm"
```

## Phase 5: 最终清理

### 0. 新增的常量定义

不新增常量。

### 1. 影响的文件范围

修改：

```text
tasks/learning_profile_task.py
tasks/learning_profile/__init__.py
tests/*
```

### 2. 函数级收口的完整数据流

最终门面：

```text
tasks.learning_profile_task
  -> service.get_or_build_learning_profile
  -> service.build_learning_profile
  -> service.get_persisted_learning_profile
  -> personal_syllabus.read_profile_personal_syllabus
  -> personal_syllabus.init_profile_personal_syllabus
  -> personal_syllabus.append_profile_personal_syllabus_suggestion
  -> agent_runtime.run_learning_profile_agent
  -> agent_runtime.get_learning_profile_agent
```

外部模块不得直接调用：

```text
tasks.learning_profile.agent_tools.*
tasks.learning_profile.service._*
tasks.learning_profile.personal_syllabus._*
```

测试可以按需要导入包内实现，但业务代码只走门面。

### 3. 精确到输入输出的函数级收口

`tasks/learning_profile_task.py` 最终只保留公共函数 re-export：

```python
get_persisted_learning_profile(...)
build_learning_profile(...)
get_or_build_learning_profile(...)
run_learning_profile_agent(...)
get_learning_profile_agent(...)
read_profile_personal_syllabus(...)
init_profile_personal_syllabus(...)
append_profile_personal_syllabus_suggestion(...)
normalize_profile_personal_syllabus_suggestion(...)
```

不再保留：

- `_tool_*`
- `_build_learning_profile_model`
- `_build_learning_profile_user_prompt`
- `_summarize_learning_profile_state`
- `_personal_syllabus_root_dir`
- `_hydrate_profile_personal_syllabus`

如测试仍需要这些内部函数，应改到对应包内模块导入。

### 4. 测试用例的构建描述

最终验收：

```bash
python -m pytest -q \
  tests/test_learning_profile.py \
  tests/test_learning_profile_toolchain.py \
  tests/test_learning_profile_input_variants.py \
  tests/test_learning_profile_api.py \
  tests/test_profile_personal_syllabus_tools.py \
  tests/test_profile_personal_syllabus_full_chain.py \
  tests/test_personal_recommendation_task.py \
  -m "not llm"
```

可选真实 Agent 验收：

```bash
RUN_LLM_TESTS=1 python -m pytest -q \
  tests/test_learning_profile_agent_choice.py \
  tests/test_profile_personal_syllabus_full_chain.py \
  -m llm
```
