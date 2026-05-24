# 学习画像关闭报告

本文档描述当前学习画像模块的最终实现边界。目标是说明输入输出契约、内部核心逻辑、测试构造和持久化内容，便于后续接入总 Agent、前端接口或维护个人教学大纲。

## 0. 新增的常量定义

路径常量位于 `constant.py`：

- `BasePath.PERSONAL_PROFILE_ROOT = "/profiles"`
- `BasePath.PERSONAL_SYLLABUS_ROOT = "/schedule/student_alt"`

个人大纲推进常量：

- `PersonalSyllabus.FORGET_DAYS = 7`
- `PersonalSyllabus.PROGRESS_MAX = 5`
- `PersonalSyllabus.PROGRESS_MIN = -5`
- `PersonalSyllabus.LLM_REVIEW_THREDHOLD = 5`

画像建议来源：

- `ProfilePersonalSyllabusSuggestionSource.PROFILE_AGENT = "profile_agent"`
- `ProfilePersonalSyllabusSuggestionSource.TOTAL_AGENT = "total_agent"`
- `ProfilePersonalSyllabusSuggestionSource.LEGACY_LEARNING_QA = "legacy_learning_qa"`
- `ProfilePersonalSyllabusSuggestionSource.MANUAL = "manual"`

画像建议阈值：

- `ProfilePersonalSyllabusSuggestionThreshold.CONFIDENCE_MIN = 0.65`
- `ProfilePersonalSyllabusSuggestionThreshold.WEEK_REVIEW_THRESHOLD = 5`
- `ProfilePersonalSyllabusSuggestionThreshold.SUGGESTION_HISTORY_MAX = 50`

当前画像模块没有新增数据库表。它复用 `user_syllabus.personal_profile_path` 和 `user_syllabus.personal_syllabus_path` 作为文件路径绑定。

## 1. 影响的文件范围

核心实现：

- `tasks/learning_profile_task.py`
  - 学习画像 Agent 编排入口。
  - 画像构建、读取、持久化、个人大纲初始化和建议更新。
- `tasks/learning_profile/profile_builder.py`
  - 画像特征计算和最终 profile 组装。
- `tasks/learning_profile/alignment.py`
  - 输入清洗、事件归一化、文本和分数对齐工具。
- `tasks/learning_profile/storage.py`
  - 画像文件路径、读取、合并、保存、身份校验。
- `tasks/learning_profile/models.py`
  - `LearningProfileDeps`
  - `LearningProfileResult`
- `tasks/learning_profile/__init__.py`
  - 对外导出学习画像包内模型和存储工具。
- `repositories/user_syllabus_repo.py`
  - `personal_syllabus_path`
  - `personal_profile_path`
  - 路径写回。
- `schemas/user_syllabus.py`
  - `personal_syllabus_path`
  - `personal_profile_path`

接口和测试：

- `blueprint/user_api.py`
- `tests/test_learning_profile.py`
- `tests/test_learning_profile_toolchain.py`
- `tests/test_learning_profile_input_variants.py`
- `tests/test_learning_profile_api.py`
- `tests/test_profile_personal_syllabus_tools.py`
- `tests/test_profile_personal_syllabus_full_chain.py`
- `tests/test_learning_profile_agent_choice.py`
- `docs/learning_profile_dev_doc.md`

## 2. 函数级收口的完整数据流

### 2.1 外部调用输入契约

外部调用方可以通过 API 或 task 函数触发画像构建。该层输入是业务请求输入，不是 Agent tool 直接消费的完整 state。

API 入口：

```text
POST /api/user_learning_profile
```

Task 入口：

```python
get_or_build_learning_profile(...)
build_learning_profile(...)
```

外部输入契约：

```json
{
  "user_id": 20,
  "syllabus_id": 29,
  "dialogue_text": [
    "我正在学 HBase，RowKey 热点和预分区很容易卡住。"
  ],
  "learning_goal": "掌握 HBase RowKey 设计",
  "learning_records": [
    {"event_type": "study_session", "duration_minutes": 42, "started_at": 1760000000, "meta": {"topic": "HBase"}}
  ],
  "answer_records": [
    {"question": "RowKey 如何避免热点？", "correct": false, "answered_at": 1760000100, "meta": {"knowledge_points": ["RowKey 热点"]}}
  ],
  "resource_usage": [
    {"resource_id": "video_hbase_rowkey", "action": "complete", "timestamp": 1760000200, "meta": {"knowledge_points": ["RowKey 热点"]}}
  ]
}
```

字段说明：

- `user_id`：必填。用于读取用户基础信息、课程绑定、历史和持久化画像。
- `syllabus_id`：可选，但建议提供。提供后画像会收口到指定课程，并启用个人大纲和画像持久化。
- `dialogue_text`：可选。字符串或字符串数组，用于目标明确度、情绪、难度、偏好等对话特征。
- `learning_goal`：可选。显式学习目标，优先级高于对话和大纲推断目标。
- `learning_records`：可选。学习时长、活跃度和学习频率输入。
- `answer_records`：可选。知识点级掌握度和答题表现输入。
- `resource_usage`：可选。资源偏好、完成情况和投入度输入。
- `refresh_profile`：只属于 `get_or_build_learning_profile` / API 缓存控制参数，不进入 Agent 算法计算。为 `false` 时优先读持久化画像；为 `true` 时强制重新构建。

### 2.2 Agent state 输入契约

`build_learning_profile(...)` 会把外部输入和数据库上下文整理成内部 state。真实 Learning Profile Agent 消费的是这个 state，而不是直接消费 API JSON。

state 核心字段：

```json
{
  "user_id": 20,
  "syllabus_id": 29,
  "user": "<User ORM object>",
  "user_syllabuses": ["<UserSyllabus ORM rows>"],
  "profile_scope": [
    {
      "syllabus_id": 29,
      "title": "大数据概论",
      "personal_syllabus_path": "schedule/student_alt/user_20/29_personal.json",
      "personal_profile_path": "profiles/29-20.json"
    }
  ],
  "dialogue_texts": ["我正在学 HBase，RowKey 热点和预分区很容易卡住。"],
  "learning_goal": "掌握 HBase RowKey 设计",
  "learning_records": [],
  "answer_records": [],
  "resource_usage": [],
  "now_ts": 1760000000,
  "history_entries": [],
  "existing_profile": null,
  "existing_profile_path": null,
  "loaded_personal_syllabuses": [],
  "normalized_events": {},
  "feature_bundle": {},
  "profile": null,
  "profile_path": null,
  "profile_saved": false,
  "tool_trace": []
}
```

算法计算需要的输入在 state 中都有对应来源：

| 算法输入 | state 字段 | 来源 |
|---|---|---|
| 用户身份 | `user`、`user_id` | `get_user_by_id` |
| 课程范围 | `profile_scope`、`user_syllabuses` | `list_user_syllabuses`、`get_syllabus_by_id` |
| 显式学习目标 | `learning_goal` | 外部调用输入 |
| 对话文本 | `dialogue_texts` | 外部 `dialogue_text` 经 `alignment.flatten_text_inputs` 清洗 |
| 历史问答 | `history_entries` | `history/{syllabus_id}_{user_id}.json` |
| 学习行为 | `learning_records` | 外部调用输入 |
| 答题记录 | `answer_records` | 外部调用输入 |
| 资源使用 | `resource_usage` | 外部调用输入 |
| 个人大纲 | `loaded_personal_syllabuses` | `user_syllabus.personal_syllabus_path` 和原始 syllabus JSON |
| 事件统一格式 | `normalized_events` | `_tool_normalize_events` |
| 时间基准 | `now_ts` | `build_learning_profile` 初始化 |
| 已保存画像 | `existing_profile` | `profiles/{syllabus_id}-{user_id}.json` 或 DB path |

因此当前实际 Agent tools 不缺算法计算用的输入。文档需要区分的是：外部请求输入、Agent state 输入、tool 运行中读取的上下文输入。

### 2.3 Agent 工具读取的上下文契约

Agent tools 会在运行时补齐以下上下文：

- `_tool_load_existing_profile_context`
  - 读取 `user_syllabus.personal_profile_path`
  - 读取默认路径 `profiles/{syllabus_id}-{user_id}.json`
- `_tool_load_history_context`
  - 读取 `history/{syllabus_id}_{user_id}.json`
  - 未指定 syllabus 时读取该用户匹配的历史文件
- `_tool_load_personal_syllabus_context`
  - 读取 `user_syllabus.personal_syllabus_path`
  - 读取原始 `syllabus.syllabus_path`
  - 若指定课程但没有个人大纲，则初始化 `schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json`
- `_tool_normalize_events`
  - 汇总 `history_entries / learning_records / answer_records / resource_usage / dialogue_texts`
- `_tool_compute_features`
  - 消费 `normalized_events / loaded_personal_syllabuses / dialogue_texts / learning_goal / now_ts / profile_scope / user`

这些上下文是画像算法的真实输入来源。外部调用方不需要手动传入 `existing_profile`、`history_entries`、`loaded_personal_syllabuses` 或 `normalized_events`。

### 2.4 构建路径：输入事件 -> 真实画像 Agent -> 画像 JSON

完整数据流：

```text
build_learning_profile(...)
  -> get_user_by_id
  -> list_user_syllabuses / get_syllabus_by_id
  -> 初始化 state
  -> 若 syllabus_id 存在，先 load_existing_profile_context
  -> run_learning_profile_agent(state)
    -> load_existing_profile_context
    -> load_history_context
    -> load_personal_syllabus_context
    -> normalize_events
    -> compute_features
       -> profile_builder.compute_learning_profile_bundle
    -> assemble_profile
    -> save_or_update_profile
  -> 返回 state["profile"]
```

模块输出契约：

```json
{
  "user_id": 20,
  "syllabus_id": 29,
  "syllabus_scope": [],
  "learning_goal": "掌握 HBase RowKey 设计",
  "knowledge_mastery": {
    "overall_level": "weak",
    "overall_score": 0.43,
    "syllabus_score": 0.35,
    "answer_score": 0.33,
    "engagement_score": 0.61,
    "by_knowledge_point": {},
    "knowledge_point_details": {},
    "weak_weeks": [],
    "mastered_weeks": []
  },
  "concept_gaps": [],
  "resource_preference": [],
  "learning_style": "visual-driven",
  "dropout_risk": "medium",
  "dropout_risk_score": 0.47,
  "recent_anomaly": [],
  "confidence": 0.68,
  "evidence": [],
  "source_events": [],
  "signals": {},
  "suggested_personal_syllabus_updates": [],
  "profile_path": "profiles/29-20.json",
  "profile_saved": true,
  "profile_refreshed": true
}
```

### 2.5 读取路径：优先读已保存画像

模块输入契约：

```python
get_or_build_learning_profile(
    user_id: int,
    syllabus_id: int | None = None,
    refresh_profile: bool = False,
    dialogue_text: Any = None,
    learning_goal: str | None = None,
    learning_records: Any = None,
    answer_records: Any = None,
    resource_usage: Any = None,
)
```

完整数据流：

```text
get_or_build_learning_profile
  -> 如果 syllabus_id 存在且 refresh_profile=False
     -> get_persisted_learning_profile
        -> load_existing_profile
        -> profile_has_required_identity
     -> 命中则直接返回 profile_refreshed=False
  -> 未命中或 refresh_profile=True
     -> build_learning_profile
     -> 返回 profile_refreshed=True
```

该路径用于前端普通读取，避免每次读取都重新调用真实 Agent。

### 2.6 个人教学大纲路径

个人教学大纲由画像模块初始化和更新建议维护：

```text
init_profile_personal_syllabus
  -> 读取 syllabus 原始 JSON
  -> 生成 schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json
  -> 写回 user_syllabus.personal_syllabus_path

append_profile_personal_syllabus_suggestion
  -> normalize suggestion
  -> 追加 suggested_competance_list / suggestion_history
  -> 达到 WEEK_REVIEW_THRESHOLD 后推进 competance / competance_progress
  -> 写回个人大纲 JSON
```

## 3. 精确到输入输出的函数级收口

### 3.1 `build_learning_profile(...) -> dict | None`

输入：

- `user_id`
- `syllabus_id`
- `dialogue_text`
- `learning_goal`
- `learning_records`
- `answer_records`
- `resource_usage`

输出：

- 完整 profile dict。
- 用户不存在时返回 `None`。

内部逻辑：

- 读取用户基础信息。
- 读取用户关联课程和课程标题。
- 构造 `profile_scope`。
- 初始化 state。
- 调用真实 `run_learning_profile_agent(state)`。
- 如果 Agent 没有保存画像，但 `syllabus_id` 存在，则 fallback 调用 `_tool_save_or_update_profile`。

### 3.2 `get_or_build_learning_profile(...) -> dict | None`

输入：

- 同 `build_learning_profile`，额外包含 `refresh_profile`。

输出：

- 已保存画像或新构建画像。

内部逻辑：

- `refresh_profile=False` 且 `syllabus_id` 存在时优先读 `profiles/{syllabus_id}-{user_id}.json`。
- 已保存画像通过身份校验后直接返回。
- 未命中才重新构建并标记 `profile_refreshed=True`。

### 3.3 `run_learning_profile_agent(state: dict) -> LearningProfileResult`

输入：

- 已初始化的 Agent state。该 state 已包含外部调用输入、用户基础信息、课程绑定范围、可选历史上下文占位、可选个人大纲上下文占位和工具运行状态字段。

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

- 创建 `LearningProfileDeps(state=state)`。
- 调用 pydantic-ai Agent。
- Agent 必须通过工具链完成上下文读取、事件归一化、特征计算、画像汇总和保存。
- Agent 不直接执行画像算法；它负责按工具契约调度 `_tool_*`，算法计算收口在 `_tool_compute_features` 和 `profile_builder.compute_learning_profile_bundle`。

### 3.4 `_tool_load_existing_profile_context(state) -> dict`

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
- 优先读 DB 中 `personal_profile_path`，再读默认路径。
- 结果写入 state。

### 3.5 `_tool_load_history_context(state) -> dict`

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

- 读取 `history/{syllabus_id}_{user_id}.json`。
- 未指定 syllabus 时读取匹配该用户的历史文件。

### 3.6 `_tool_load_personal_syllabus_context(state) -> dict`

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

- 读取 `user_syllabus.personal_syllabus_path` 指向的个人大纲。
- 若指定课程但个人大纲不存在，调用 `init_profile_personal_syllabus` 初始化。
- 结果写入 `state.loaded_personal_syllabuses`。

### 3.7 `_tool_normalize_events(state) -> dict`

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

- 历史问答、学习记录、答题记录、资源使用统一转为事件。
- 提取时间、文本、知识点、行为类型、资源使用信号。
- 写入 `state.normalized_events`。

### 3.8 `_tool_compute_features(state) -> dict`

输入：

- `state.normalized_events`
- `state.loaded_personal_syllabuses`
- `state.learning_goal`
- `state.dialogue_texts`
- `state.now_ts`
- `state.profile_scope`
- `state.user`

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
- 计算对话特征、行为特征、资源偏好、答题掌握度、个人大纲周次掌握度、风险特征、证据链和置信度。
- 如果 `state.normalized_events` 为空，会先调用 `_tool_normalize_events(state)` 兜底补齐事件输入。

### 3.9 `_tool_assemble_profile(state) -> dict`

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

- 取 `feature_bundle.profile` 作为最终画像。
- 构造 `suggested_personal_syllabus_updates`，用于后续个人大纲建议更新。

### 3.10 `_tool_save_or_update_profile(state) -> dict`

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
- 合并旧画像 revision。
- 写入 `profiles/{syllabus_id}-{user_id}.json`。
- 写回 `user_syllabus.personal_profile_path`。
- DB 路径写回失败时删除临时文件。

### 3.11 `append_profile_personal_syllabus_suggestion(...) -> dict | None`

输入：

```json
{
  "week_index": 1,
  "suggested_competance": "weak",
  "confidence": 0.72,
  "reason": "画像计算发现第 1 周学习状态偏弱",
  "evidence": ["personal_syllabus", "learning_profile"],
  "source": "profile_agent"
}
```

输出：

```json
{
  "personal_syllabus": {},
  "personal_syllabus_path": "schedule/student_alt/user_20/29_personal.json",
  "suggestion": {},
  "applied": false,
  "week_index": 1,
  "suggestion_review_count": 1,
  "competance": "weak",
  "competance_progress": 0
}
```

内部逻辑：

- suggestion 低于 `CONFIDENCE_MIN` 时拒绝。
- 追加 suggestion 历史。
- 历史最多保留 `SUGGESTION_HISTORY_MAX` 条。
- 达到 `WEEK_REVIEW_THRESHOLD` 后推进个人大纲 competance。

## 4. 测试用例的构建描述

### 4.1 默认单元测试包

运行命令：

```bash
python -m pytest -q tests/test_learning_profile.py tests/test_learning_profile_toolchain.py tests/test_learning_profile_input_variants.py tests/test_learning_profile_api.py tests/test_profile_personal_syllabus_tools.py tests/test_profile_personal_syllabus_full_chain.py
```

覆盖范围：

- 本地工具链计算画像。
- fake agent 调用工具顺序。
- 多输入形态清洗。
- 个人大纲初始化。
- 个人大纲 suggestion 累积和推进。
- 画像保存路径。
- API 缓存读取和刷新语义。

这些测试不调用真实 LLM。

### 4.2 真实 Agent 集成测试

运行命令：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py tests/test_profile_personal_syllabus_full_chain.py -m llm
```

覆盖范围：

- 真实 Learning Profile Agent 是否能承担工具调度。
- 是否能读取上下文、归一化事件、计算特征、组装画像、保存画像。
- 是否能初始化个人大纲并写回 `personal_syllabus_path`。
- 是否能保存画像并写回 `personal_profile_path`。

典型工具 trace：

```json
[
  "load_existing_profile_context",
  "load_history_context",
  "load_personal_syllabus_context",
  "normalize_events",
  "compute_features",
  "assemble_profile",
  "save_or_update_profile"
]
```

真实 Agent 工具选择存在轻微波动。测试重点是链路职责，而不是模型文案质量。

## 5. 新增的持久化内容

### 5.1 个人画像 JSON

路径：

```text
profiles/{syllabus_id}-{user_id}.json
```

写入时补充：

- `profile_schema_version`
- `profile_path`
- `profile_saved`
- `saved_at`
- `profile_revision`
- `previous_profile_updated_at`
- `previous_confidence`

数据库绑定：

- `user_syllabus.personal_profile_path`

版本库策略：

```gitignore
profiles/*
!profiles/.gitkeep
```

### 5.2 个人教学大纲 JSON

路径：

```text
schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json
```

核心字段：

```json
{
  "syllabus_id": 29,
  "user_id": 20,
  "period": [
    {
      "week_index": 1,
      "content": "...",
      "enhanced_content": "...",
      "importance": "...",
      "competance": "none|weak|normal|master",
      "competance_progress": 0,
      "suggested_competance_list": [],
      "suggestion_review_count": 0,
      "suggestion_history": [],
      "updated_at": 0
    }
  ]
}
```

数据库绑定：

- `user_syllabus.personal_syllabus_path`

版本库策略：

```gitignore
schedule/student_alt/*
!schedule/student_alt/.gitkeep
```

### 5.3 历史读取内容

画像模块会读取但不主动创建历史问答文件：

```text
history/{syllabus_id}_{user_id}.json
```

版本库策略：

```gitignore
history/*
!history/.gitkeep
```
