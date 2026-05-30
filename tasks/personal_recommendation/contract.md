# 学习路径推荐收口计划

本文档用于收口 `personal_recommendation` 后续改造。目标是把当前“基于教学大纲 learning_tree 的即时推荐”升级为“可被总 Agent 和前端稳定消费的学习路径推荐能力”。

核心边界：

- `tasks/personal_recommendation_task.py` 仍是唯一跨模块门户。
- `tasks/personal_recommendation/` 包内负责推荐图构建、候选路径生成、评分、选择和可选学习计划转换。
- `study_graph` 作为推荐生成的只读输入，不由推荐模块直接修改。
- 被采纳的推荐路径单独持久化为 `learning_plan`，不写入 `study_graph` 本体。
- `learning_plan_step` 只引用推荐图或 `study_graph` 的 `node_id`，不复制整棵学习进度树。
- step 状态变化后，再通过 `study_graph_task` 同步学习事实。
- 推荐结果默认是临时建议；只有被用户或总 Agent 确认后，才成为可执行计划。

目标数据关系：

```text
profile + syllabus learning_tree + RAG + study_graph_state
  -> recommendation graph
  -> candidates / selected / best_path
  -> accept path
  -> learning_plan / learning_plan_steps
  -> step status changed
  -> study_graph_task update progress
  -> learning_profile_task refresh profile
```

## 阶段 1：增强教学大纲节点展开

### 0. 新增的常量定义

建议新增在 `tasks/personal_recommendation/syllabus_adapter.py`：

```python
SYLLABUS_CHILD_KEYS = ("children", "sections", "topics", "subtopics", "items", "modules")
SYLLABUS_ID_KEYS = ("id", "node_id", "nid", "uid", "key")
SYLLABUS_TITLE_KEYS = ("title", "name", "label")
SYLLABUS_OUTCOME_KEYS = ("outcomes", "skills", "learning_outcomes", "objectives")
SYLLABUS_PREREQUISITE_KEYS = ("prerequisites", "prereq", "parents", "depends_on")
DEFAULT_DIRECTORY_DIFFICULTY = 1.0
DEFAULT_DIRECTORY_LEARNING_TIME = 1.0
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/syllabus_adapter.py
tasks/personal_recommendation/service.py
tests/test_personal_recommendation_syllabus_adapter.py
tests/test_personal_recommendation_task.py
```

### 2. 函数级收口的完整数据流

```text
load_recommendation_learning_tree(syllabus_id)
  -> get_syllabus_by_id
  -> load_json_file(syllabus_path)
  -> syllabus_json_to_learning_tree(syllabus_json)
      -> extract top-level nodes
      -> recursively expand nested nodes
      -> assign stable node id
      -> normalize title/outcomes/prerequisites/difficulty/time
      -> add parent prerequisite when explicit prerequisite is absent
  -> return expanded learning_tree
```

### 3. 函数级收口与内部逻辑

#### `syllabus_json_to_learning_tree(syllabus_json: Any) -> dict`

输入：

```json
{
  "chapters": [
    {
      "id": "ch_1",
      "title": "机器学习基础",
      "sections": [
        {
          "id": "sec_1",
          "title": "监督学习",
          "topics": [
            {
              "id": "topic_1",
              "title": "线性回归",
              "outcomes": ["linear_regression"]
            }
          ]
        }
      ]
    }
  ]
}
```

输出：

```json
{
  "ch_1": {
    "title": "机器学习基础",
    "prerequisites": [],
    "outcomes": ["机器学习基础"],
    "learning_time_est": 1.0,
    "difficulty": 1.0,
    "node_source": "syllabus"
  },
  "sec_1": {
    "title": "监督学习",
    "prerequisites": ["ch_1"],
    "outcomes": ["监督学习"],
    "learning_time_est": 1.0,
    "difficulty": 1.0,
    "node_source": "syllabus"
  },
  "topic_1": {
    "title": "线性回归",
    "prerequisites": ["sec_1"],
    "outcomes": ["linear_regression"],
    "learning_time_est": 1.0,
    "difficulty": 1.0,
    "node_source": "syllabus"
  }
}
```

内部逻辑：

- 兼容当前已支持的 `nodes/items/modules/chapters/sections` 顶层结构。
- 对每个节点递归读取 child keys。
- 节点 id 优先使用显式 id；没有 id 时使用父 id + title 生成稳定 id。
- 节点缺少 outcomes 时，用 title 生成最小 outcome，避免目标匹配完全失效。
- 节点有显式 prerequisites 时保留显式值；没有显式 prerequisites 且存在 parent_id 时，补 `parent_id` 作为弱先修关系。
- 输出结构保持当前算法兼容：`prerequisites`、`outcomes`、`learning_time_est`、`difficulty`、`title`。

#### `_expand_syllabus_node(node: dict, parent_id: str | None, result: dict) -> str | None`

输入：

```python
node = {"id": "sec_1", "title": "监督学习", "topics": [...]}
parent_id = "ch_1"
result = {}
```

输出：

```python
"sec_1"
```

内部逻辑：

- 负责单节点规范化和递归展开。
- 返回当前节点 id，供子节点挂接父子边。
- 如果节点不可识别，返回 `None`，不抛异常。

### 4. 测试用例构建描述

- `test_syllabus_adapter_expands_nested_chapters_sections_topics`
  - 构造三层 syllabus。
  - 断言输出包含 chapter、section、topic。
  - 断言父子 prerequisite 边存在。

- `test_syllabus_adapter_preserves_explicit_prerequisites`
  - 子节点显式声明 prerequisites。
  - 断言不会被 parent_id 覆盖。

- `test_syllabus_adapter_uses_title_as_fallback_outcome`
  - 目录节点没有 outcomes。
  - 断言输出 outcomes 至少包含 title。

- `test_recommendation_route_uses_expanded_syllabus_tree`
  - 构造嵌套大纲。
  - 经过 `run_recommendation_route_from_payload` 后，断言 `graph.nodes`、`graph.edges` 展示展开后的节点和边。

## 阶段 2：新增推荐图构建器

### 0. 新增的常量定义

建议新增在 `tasks/personal_recommendation/graph_builder.py`：

```python
NODE_SOURCE_SYLLABUS = "syllabus"
NODE_SOURCE_RAG = "rag"
EDGE_SOURCE_SYLLABUS = "syllabus"
EDGE_SOURCE_RAG = "rag"
EDGE_SOURCE_PROFILE = "profile"
EDGE_CONFIDENCE_SYLLABUS = 1.0
EDGE_CONFIDENCE_RAG_DEFAULT = 0.6
PROFILE_STATE_KNOWN = "known"
PROFILE_STATE_WEAK = "weak"
PROFILE_STATE_UNKNOWN = "unknown"
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/graph_builder.py
tasks/personal_recommendation/service.py
tasks/personal_recommendation/rag_overlay.py
tests/test_personal_recommendation_graph_builder.py
tests/test_personal_recommendation_task.py
```

### 2. 函数级收口的完整数据流

```text
run_recommendation_route
  -> load_recommendation_learning_tree
  -> build_recommendation_profile
  -> build_rag_overlay(rag_context, learning_tree)
  -> build_recommendation_graph_tree(learning_tree, rag_overlay, profile, study_graph_state)
  -> generate_state(profile, recommendation_graph_tree, study_graph_state)
  -> generate(..., recommendation_graph_tree, ...)
  -> score(..., recommendation_graph_tree)
  -> _build_recommendation_graph(recommendation_graph_tree)
```

边界变化：

- 原始 `learning_tree` 只代表教学大纲转换结果。
- `recommendation_graph_tree` 是推荐算法实际使用的图。
- RAG temporary edges 可以进入推荐图参与搜索，但以 soft edge 标记。
- `study_graph_state` 只作为只读状态输入，不修改 `study_graph`。

### 3. 函数级收口与内部逻辑

#### `build_recommendation_graph_tree(learning_tree: dict, rag_overlay: dict | None = None, profile: dict | None = None, study_graph_state: dict | None = None) -> dict`

输入：

```json
{
  "learning_tree": {
    "n1": {
      "title": "统计基础",
      "prerequisites": [],
      "outcomes": ["stats_basic"]
    },
    "n2": {
      "title": "机器学习",
      "prerequisites": [],
      "outcomes": ["ml_basic"]
    }
  },
  "rag_overlay": {
    "temporary_edges": [
      {"source": "n1", "target": "n2", "reason": "统计基础支持机器学习"}
    ]
  },
  "profile": {
    "knowledge_levels": {"stats_basic": 0.8}
  },
  "study_graph_state": {
    "completed_node_ids": ["n1"],
    "blocked_node_ids": [],
    "weak_node_ids": []
  }
}
```

输出：

```json
{
  "n1": {
    "title": "统计基础",
    "prerequisites": [],
    "outcomes": ["stats_basic"],
    "node_source": "syllabus",
    "edge_sources": {},
    "edge_confidence": {},
    "profile_state": "known",
    "study_graph_state": "completed"
  },
  "n2": {
    "title": "机器学习",
    "prerequisites": ["n1"],
    "outcomes": ["ml_basic"],
    "node_source": "syllabus",
    "edge_sources": {"n1": "rag"},
    "edge_confidence": {"n1": 0.6},
    "profile_state": "unknown",
    "study_graph_state": "unknown"
  }
}
```

内部逻辑：

- 深拷贝 `learning_tree`，不原地修改输入。
- 原始节点补 `node_source="syllabus"`。
- 原始 prerequisites 标记 `edge_sources[prereq]="syllabus"`、`edge_confidence[prereq]=1.0`。
- 读取 `rag_overlay.temporary_edges`，source/target 都存在时，将 source 追加到 target prerequisites。
- RAG edge 标记 `edge_sources[source]="rag"`、`edge_confidence[source]=0.6`。
- profile 只标记 `profile_state`，例如 `known/weak/unknown`。
- study_graph_state 只标记 `study_graph_state`，例如 `completed/blocked/weak/current/unknown`。

#### `_annotate_profile_state(node: dict, profile: dict) -> str`

输入：

```json
{
  "node": {"outcomes": ["stats_basic"]},
  "profile": {"knowledge_levels": {"stats_basic": 0.8}}
}
```

输出：

```text
known
```

内部逻辑：

- 所有 outcomes 掌握度高于阈值，返回 `known`。
- 部分掌握或低分，返回 `weak`。
- 没有掌握信息，返回 `unknown`。

#### `_annotate_study_graph_state(node_id: str, study_graph_state: dict | None) -> str`

输入：

```json
{
  "node_id": "n1",
  "study_graph_state": {
    "current_node_id": "n2",
    "completed_node_ids": ["n1"],
    "blocked_node_ids": ["n3"],
    "weak_node_ids": ["n4"]
  }
}
```

输出：

```text
completed
```

内部逻辑：

- 命中 `current_node_id` 返回 `current`。
- 命中 `completed_node_ids` 返回 `completed`。
- 命中 `blocked_node_ids` 返回 `blocked`。
- 命中 `weak_node_ids` 返回 `weak`。
- 都未命中返回 `unknown`。

### 4. 测试用例构建描述

- `test_graph_builder_does_not_mutate_learning_tree`
  - 传入原始 tree 和 RAG edge。
  - 调用后断言原始 tree 未变化。

- `test_graph_builder_adds_rag_temporary_edges_as_soft_edges`
  - 断言 target prerequisites 包含 source。
  - 断言 `edge_sources[source] == "rag"`。
  - 断言 `edge_confidence[source] < 1.0`。

- `test_graph_builder_marks_syllabus_edges_as_high_confidence`
  - 原始 prerequisites 边标为 syllabus。
  - confidence 为 1.0。

- `test_graph_builder_applies_study_graph_state_as_readonly_annotations`
  - 输入 `completed_node_ids`、`blocked_node_ids`。
  - 断言输出节点有状态标记。
  - 断言没有调用任何 study_graph 写操作。

## 阶段 3：候选路径生成支持深度策略和 study_graph_state

### 0. 新增的常量定义

建议新增在 `tasks/personal_recommendation/candidate_generator.py`：

```python
DEPTH_STRATEGY_SHORTEST = "shortest"
DEPTH_STRATEGY_BALANCED = "balanced"
DEPTH_STRATEGY_DEEP_PREREQUISITE = "deep_prerequisite"
DEFAULT_DEPTH_STRATEGY = DEPTH_STRATEGY_BALANCED
SUPPORTED_DEPTH_STRATEGIES = {
    DEPTH_STRATEGY_SHORTEST,
    DEPTH_STRATEGY_BALANCED,
    DEPTH_STRATEGY_DEEP_PREREQUISITE,
}
```

建议新增在 `tasks/personal_recommendation/perception.py`：

```python
STUDY_GRAPH_STATE_COMPLETED = "completed"
STUDY_GRAPH_STATE_BLOCKED = "blocked"
STUDY_GRAPH_STATE_WEAK = "weak"
STUDY_GRAPH_STATE_CURRENT = "current"
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/candidate_generator.py
tasks/personal_recommendation/graph_adapter.py
tasks/personal_recommendation/perception.py
tasks/personal_recommendation/service.py
tasks/personal_recommendation_task.py
tests/test_personal_recommendation_task.py
```

### 2. 函数级收口的完整数据流

```text
run_recommendation_route_from_payload
  -> parse depth_strategy
  -> parse optional study_graph_state
  -> run_recommendation_route(..., depth_strategy, study_graph_state)
  -> generate_state(profile, recommendation_graph_tree, study_graph_state)
      -> completed nodes become less preferred start nodes
      -> blocked nodes become hard constraints
      -> weak/current nodes can become preferred start hints
  -> generate(..., depth_strategy)
  -> serialize candidates
```

### 3. 函数级收口与内部逻辑

#### `run_recommendation_route_from_payload(payload: dict) -> dict`

新增输入字段：

```json
{
  "depth_strategy": "balanced",
  "study_graph_state": {
    "current_node_id": "n2",
    "completed_node_ids": ["n1"],
    "blocked_node_ids": ["n3"],
    "skipped_node_ids": [],
    "weak_node_ids": ["n4"]
  }
}
```

输出不破坏现有结构，但候选项可以新增：

```json
{
  "path": ["n2", "n4"],
  "path_depth": 2,
  "path_edge_sources": ["syllabus"],
  "study_graph_matched_nodes": ["n2", "n4"]
}
```

内部逻辑：

- 从 payload 读取 `depth_strategy`，非法值回退 `"balanced"`。
- 从 payload 读取 `study_graph_state`，必须是 dict，否则忽略。
- 不主动调用 `study_graph_task`，除非后续由总 Agent 或 API 层在进入推荐前统一注入。

#### `run_recommendation_route(..., study_graph_state: dict | None = None, depth_strategy: str = "balanced") -> dict`

新增参数：

```python
study_graph_state: dict | None = None
depth_strategy: str = "balanced"
```

内部逻辑：

- `study_graph_state.completed_node_ids` 进入状态感知，避免完成节点被优先推荐为下一步。
- `study_graph_state.blocked_node_ids` 进入 constraints，避免生成不可执行路径。
- `study_graph_state.current_node_id`、`weak_node_ids` 可作为起点或补救路径提示。
- 不修改 `study_graph_state`，不写数据库。

#### `generate(..., depth_strategy: str = DEFAULT_DEPTH_STRATEGY) -> list[dict]`

输入：

```python
generate(
    start_nodes,
    goals,
    learning_tree,
    S,
    L_max=6,
    T_max=100,
    K=20,
    beam_width=6,
    depth_strategy="balanced",
)
```

输出：

```json
[
  {
    "path": ["n1", "n2"],
    "cost": 12.0,
    "skills": ["stats_basic", "ml_basic"],
    "path_depth": 2,
    "path_edge_sources": ["syllabus"]
  }
]
```

内部逻辑：

- `shortest`：保持偏短路径行为，目标达成即可尽快返回。
- `balanced`：默认行为，适度保留包含前置节点的路径。
- `deep_prerequisite`：对基础薄弱或前置风险高的情况，提高包含前置链路路径的保留概率。
- 不把扩大 `L_max` 当成唯一手段；策略应影响 heuristic 和 beam pruning。

#### `GraphAdapter.get_edge_metadata(source: str, target: str) -> dict`

输入：

```python
source = "n1"
target = "n2"
```

输出：

```json
{
  "source": "syllabus",
  "confidence": 1.0
}
```

内部逻辑：

- 对没有 metadata 的旧 tree，默认返回 syllabus/high confidence。
- 对 graph_builder 生成的 tree，读取 `edge_sources` 和 `edge_confidence`。

### 4. 测试用例构建描述

- `test_recommendation_depth_strategy_defaults_to_balanced`
  - 不传 `depth_strategy`，行为稳定。

- `test_recommendation_depth_strategy_rejects_unknown_value`
  - 传非法值，回退 balanced，不报错。

- `test_deep_prerequisite_strategy_prefers_prerequisite_chain`
  - 构造一个直接目标节点和一条前置链。
  - 基础薄弱 profile 下，deep strategy 倾向前置链。

- `test_study_graph_completed_nodes_are_not_prioritized`
  - `study_graph_state.completed_node_ids` 中的节点不应被优先推荐为下一步。

- `test_study_graph_blocked_nodes_enter_constraints`
  - `blocked_node_ids` 可进入约束，避免生成不可执行路径。

- `test_recommendation_without_study_graph_state_keeps_existing_behavior`
  - 不传 `study_graph_state` 时保持当前行为。

## 阶段 4：评分加入路径深度与图结构置信度

### 0. 新增的常量定义

建议更新 `tasks/personal_recommendation/evaluator.py`：

```python
DEFAULT_WEIGHTS = {
    "E": 0.35,
    "D": 0.15,
    "R": 0.15,
    "P": 0.15,
    "G": 0.10,
    "C": 0.10,
}
SCORE_KEY_GRANULARITY = "G"
SCORE_KEY_CONFIDENCE = "C"
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/evaluator.py
tasks/personal_recommendation/candidate_generator.py
tasks/personal_recommendation/service.py
tests/test_personal_recommendation_task.py
```

### 2. 函数级收口的完整数据流

```text
candidates
  -> score(candidate, state, recommendation_graph_tree)
      -> E efficiency
      -> D difficulty mismatch
      -> R prerequisite risk
      -> P preference match
      -> G path granularity/depth quality
      -> C edge confidence
  -> normalize_scores
  -> scalar_scores
  -> soft_prune_by_dominance
  -> ib_grpo_select
```

### 3. 函数级收口与内部逻辑

#### `score(path_item: dict, S: dict, learning_tree: dict) -> dict`

输入：

```json
{
  "path_item": {
    "path": ["n1", "n2", "n3"],
    "cost": 12.0,
    "skills": ["a", "b", "c"],
    "path_edge_sources": ["syllabus", "rag"]
  },
  "S": {
    "knowledge": {"a": 0.0},
    "preferences": {},
    "constraints": {}
  }
}
```

输出：

```json
{
  "E": 0.25,
  "D": 2.0,
  "R": 0.33,
  "P": 0.5,
  "G": 0.75,
  "C": 0.8
}
```

内部逻辑：

- `E` 保持当前“新技能 / 成本”逻辑。
- `D` 保持当前难度不匹配逻辑。
- `R` 保持当前先修风险逻辑，但读取推荐图中的 prerequisites。
- `P` 暂时保持默认 0.5，后续再接画像偏好。
- `G` 根据路径长度、目标达成情况、用户基础状态计算。
- `C` 根据路径边的 confidence 平均值计算；没有边的单节点路径使用中性值。

#### `normalize_scores(score_dicts: list[dict], keys: list[str] | None = None) -> list[dict]`

内部逻辑：

- 默认 keys 扩展为 `["E", "D", "R", "P", "G", "C"]`。
- `D`、`R` 越低越好，需要反向归一化。
- `G`、`C` 越高越好。

### 4. 测试用例构建描述

- `test_score_includes_granularity_and_confidence`
  - 断言 score 输出包含 `G`、`C`。

- `test_score_confidence_prefers_syllabus_edges_over_rag_edges`
  - syllabus edge 路径 C 高于 rag-only 路径。

- `test_score_granularity_penalizes_risky_single_node_path`
  - 用户基础薄弱，目标节点有未掌握 prerequisites。
  - 单节点直达路径 G 较低。

- 回归测试：现有推荐 task 测试仍通过。

## 阶段 5：返回结构补充总 Agent 可用信息

### 0. 新增的常量定义

建议新增在 `tasks/personal_recommendation/service.py`：

```python
RECOMMENDATION_SCHEMA_VERSION = "personal_recommendation.v2"
NEXT_ACTION_CONFIRM_PATH = "confirm_path"
NEXT_ACTION_GENERATE_RESOURCES = "generate_resources"
NEXT_ACTION_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/service.py
tasks/personal_recommendation/agent_contracts.py
tasks/personal_recommendation_task.py
tests/test_personal_recommendation_task.py
tests/test_personal_recommendation_agent_choice.py
docs/personal_recommendation_dev_doc.md
```

### 2. 函数级收口的完整数据流

```text
run_recommendation_route
  -> build graph/candidates/selected/best_path
  -> attach schema_version
  -> attach planning_hints
  -> return API-ready result

total agent
  -> if active learning_plan exists: use active plan
  -> else read best_path and planning_hints
  -> decide ask / confirm / auto accept / generate resources
```

### 3. 函数级收口与内部逻辑

#### `run_recommendation_route(...) -> dict`

输出新增字段：

```json
{
  "schema_version": "personal_recommendation.v2",
  "planning_hints": {
    "path_depth": 3,
    "has_rag_edges": true,
    "has_low_confidence_edges": true,
    "suggested_next_action": "confirm_path"
  }
}
```

内部逻辑：

- `schema_version` 用于前端和总 Agent 做兼容判断。
- `planning_hints.path_depth` 来自 `best_path.path` 长度。
- `planning_hints.has_rag_edges` 根据 best path edge sources 判断。
- `planning_hints.has_low_confidence_edges` 根据 edge confidence 判断。
- `suggested_next_action` 建议值：
  - `confirm_path`：路径可用，但存在 soft edge 或低置信边。
  - `generate_resources`：路径明确，可直接进入资源生成。
  - `ask_goal_clarification`：没有 candidates 或 goals 无法解析。

#### `_build_planning_hints(result: dict) -> dict`

输入：

```json
{
  "best_path": {
    "path": ["n1", "n2"],
    "path_edge_sources": ["rag"]
  },
  "candidates": []
}
```

输出：

```json
{
  "path_depth": 2,
  "has_rag_edges": true,
  "has_low_confidence_edges": true,
  "suggested_next_action": "confirm_path"
}
```

内部逻辑：

- 只读推荐结果，不重新执行算法。
- 对空候选返回 `ask_goal_clarification`。
- 对无 RAG/低置信边且路径非空返回 `generate_resources`。

### 4. 测试用例构建描述

- 推荐结果包含 `schema_version`。
- 有 best_path 时，`planning_hints.path_depth` 等于路径长度。
- 有 RAG edge 时，`has_rag_edges=True`。
- 空 candidates 时，`suggested_next_action="ask_goal_clarification"`。
- Agent choice 测试中保留 `planning_hints`，工具调用顺序不变。

## 阶段 6：learning_plan manifest.jsonl 持久化

### 0. 新增的常量定义

建议新增在 `tasks/personal_recommendation/learning_plan.py`：

```python
LEARNING_PLAN_MANIFEST_VERSION = "learning_plan.v1"
LEARNING_PLAN_ROOT_DIR = "personal_recommendation/learning_plan"
LEARNING_PLAN_MANIFEST_FILENAME = "manifest.jsonl"
LEARNING_PLAN_STATUS_ACTIVE = "active"
LEARNING_PLAN_STATUS_COMPLETED = "completed"
LEARNING_PLAN_STATUS_SUPERSEDED = "superseded"
LEARNING_PLAN_STATUS_ABANDONED = "abandoned"
LEARNING_PLAN_STEP_STATUS_PENDING = "pending"
LEARNING_PLAN_STEP_STATUS_ACTIVE = "active"
LEARNING_PLAN_STEP_STATUS_COMPLETED = "completed"
LEARNING_PLAN_STEP_STATUS_SKIPPED = "skipped"
LEARNING_PLAN_SOURCE_RECOMMENDATION = "recommendation"
LEARNING_PLAN_SOURCE_AUTO_AGENT = "auto_agent"
```

可选 recommendation run 日志常量，仍然先写文件，不建表：

```python
RECOMMENDATION_RUN_STATUS_CREATED = "created"
RECOMMENDATION_RUN_STATUS_ACCEPTED = "accepted"
RECOMMENDATION_RUN_STATUS_DISCARDED = "discarded"
```

### 1. 影响的文件范围

```text
tasks/personal_recommendation/learning_plan.py
tasks/personal_recommendation/service.py
tasks/personal_recommendation_task.py
tasks/study_graph_task.py
tests/test_personal_recommendation_learning_plan.py
```

暂不新增：

```text
repositories/learning_plan_repo.py
models/learning_plan.py
```

这些落库相关内容后续统一迁移时再补。

### 2. 函数级收口的完整数据流

推荐即时结果：

```text
run_recommendation_route
  -> return transient candidates / selected / best_path
```

被采纳路径：

```text
frontend / total agent
  -> accept_recommendation_path
  -> read user manifest.jsonl
  -> append supersede event for old active plan if exists
  -> append create active learning_plan event
  -> append create learning_plan_steps event
  -> return active plan snapshot
```

step 执行同步：

```text
update_learning_plan_step_status(plan_id, step_id, completed)
  -> append step_status_changed event to manifest.jsonl
  -> rebuild active plan snapshot from manifest entries
  -> call study_graph_task to update node progress
  -> call learning_profile_task to refresh or patch profile
```

读取 active plan：

```text
get_active_learning_plan(user_id, syllabus_id)
  -> read manifest.jsonl
  -> replay entries by plan_id
  -> ignore superseded/abandoned plans
  -> return latest active plan snapshot
```

### 3. 函数级收口与内部逻辑

#### `accept_recommendation_path(user_id: int, syllabus_id: int | None, recommendation_result: dict, candidate_index: int | None = None) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "candidate_index": 0,
  "recommendation_result": {
    "candidates": [
      {
        "path": ["n1", "n2"],
        "skills": ["a", "b"],
        "path_edges": []
      }
    ],
    "best_path": {
      "path": ["n1", "n2"]
    }
  }
}
```

输出：

```json
{
  "success": true,
  "plan_id": "plan_xxx",
  "status": "active",
  "superseded_plan_id": "plan_old",
  "steps": [
    {
      "step_id": "step_1",
      "node_id": "n1",
      "status": "active",
      "order_index": 0
    },
    {
      "step_id": "step_2",
      "node_id": "n2",
      "status": "pending",
      "order_index": 1
    }
  ]
}
```

内部逻辑：

- 如果传 `candidate_index`，优先采纳 `candidates[candidate_index]`。
- 未传 `candidate_index` 时，采纳 `best_path`。
- 如果已有 active plan，新确认路径时向 `manifest.jsonl` 追加一条 `plan_superseded` 事件，不物理删除旧记录。
- 向 `manifest.jsonl` 追加新的 `plan_created` 事件。
- 向 `manifest.jsonl` 追加新的 `steps_created` 事件。
- 每个 step 只保存 `node_id`、title/outcomes 摘要、order_index、status、resource_ids 等执行字段。
- 不复制整个 `study_graph`，不直接修改 `study_graph`。
- 返回值由 manifest entries replay 得到，避免内存状态和文件状态不一致。

manifest entry 示例：

```json
{
  "entry_id": "lp_entry_20260530120000_ab12cd",
  "event_type": "plan_created",
  "schema_version": "learning_plan.v1",
  "user_id": 8,
  "syllabus_id": 20,
  "plan_id": "plan_20260530120000_ab12cd",
  "status": "active",
  "source": "recommendation",
  "created_at": 1780123200,
  "payload": {
    "path": ["n1", "n2"],
    "candidate_index": 0
  }
}
```

#### `get_active_learning_plan(user_id: int, syllabus_id: int | None = None) -> dict | None`

输出：

```json
{
  "plan_id": "plan_xxx",
  "status": "active",
  "current_step_index": 0,
  "steps": [
    {"step_id": "step_1", "node_id": "n1", "status": "active"}
  ]
}
```

内部逻辑：

- 从 `manifest.jsonl` 读取该用户的 learning plan entries。
- 按写入顺序 replay plan events 和 step events。
- 返回当前 active plan。
- 如果没有 active plan，返回 `None`。
- 总 Agent 优先读取该函数结果；存在 active plan 时，不重新把临时 best_path 当 committed plan。

#### `update_learning_plan_step_status(plan_id: str, step_id: str, status: str) -> dict`

输入：

```json
{
  "plan_id": "plan_xxx",
  "step_id": "step_1",
  "status": "completed"
}
```

输出：

```json
{
  "success": true,
  "plan_id": "plan_xxx",
  "step_id": "step_1",
  "status": "completed",
  "study_graph_sync": {
    "attempted": true,
    "success": true
  }
}
```

内部逻辑：

- 向 `manifest.jsonl` 追加一条 `step_status_changed` 事件。
- 通过 replay manifest entries 得到最新 plan snapshot。
- 当 status 变为 `completed` 时，再调用 `study_graph_task` 更新对应 `node_id` 的学习进度。
- 同步后可触发 `learning_profile_task` 局部刷新或重建。
- study_graph 同步失败时，保留 plan 状态变更结果，并返回 sync 错误信息供重试。

#### `load_learning_plan_manifest(user_id: int, syllabus_id: int | None = None) -> list[dict]`

输出：

```json
[
  {
    "entry_id": "lp_entry_...",
    "event_type": "plan_created",
    "plan_id": "plan_...",
    "payload": {}
  }
]
```

内部逻辑：

- 如果 `manifest.jsonl` 不存在，返回空列表。
- 每行必须是 JSON object；坏行可以跳过并记录 warning，避免单条损坏导致全部读取失败。
- 后续落库迁移时，该函数可以作为迁移读取入口。

#### `append_learning_plan_manifest_entry(user_id: int, entry: dict) -> dict`

内部逻辑：

- 给 entry 补 `entry_id`、`schema_version`、`user_id`、`created_at`。
- 追加写入 `manifest.jsonl`，每行一个 JSON object。
- 不覆盖旧事件。

### 4. 测试用例构建描述

- `test_accept_recommendation_path_creates_active_plan`
  - 确认某条 candidate 后写入 `manifest.jsonl`。
  - replay 后返回 active learning_plan。

- `test_accept_recommendation_path_supersedes_old_active_plan`
  - 新确认一条路径时，旧 active plan 通过 manifest 事件标记为 superseded，不物理删除。

- `test_learning_plan_step_stores_node_reference_only`
  - step 保存 `node_id`，但不复制整个 study_graph 节点。

- `test_step_completed_triggers_study_graph_sync`
  - step completed 后才触发 study_graph 更新。

- `test_get_active_learning_plan_returns_committed_source`
  - 有 active plan 时，返回固定来源，供总 Agent 读取。

- `test_learning_plan_manifest_is_append_only_jsonl`
  - 连续 accept/update 后，`manifest.jsonl` 行数递增。
  - 不覆盖旧 entry。

- `test_learning_plan_manifest_replay_ignores_superseded_plan`
  - replay 后只返回最新 active plan。

## 推荐实施顺序

建议按以下顺序推进：

```text
1. 阶段 1：增强 syllabus adapter 嵌套展开
2. 阶段 2：新增 recommendation graph builder
3. 阶段 5：补充 schema_version 和 planning_hints
4. 阶段 3：候选路径生成支持深度策略和 study_graph_state
5. 阶段 4：评分加入 G/C
6. 阶段 6：按总 Agent 和前端确认路径需求，实现 learning_plan 持久化
```

原因：

- 阶段 1 和 2 直接解决推荐树浅的问题。
- 阶段 5 能让总 Agent 更早消费推荐结果。
- 阶段 3 和 4 属于算法质量调优，最好等有更多真实 syllabus/RAG/study_graph 样本后再收紧权重。
- 阶段 6 不应过早实现，但边界必须提前固定：推荐路径是临时建议，`learning_plan` 才是固定执行来源。
