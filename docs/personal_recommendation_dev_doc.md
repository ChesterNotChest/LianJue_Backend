# 学习路径推荐关闭报告

本文档用于收口学习路径推荐 Agent/Task 的实现状态。当前实现已经从独立 `prototype_recommendation` 迁移到主工程 `tasks` 与 `tests` 结构中，作为可被总 Agent 或 API 调用的路径推荐能力。

目标不是直接替代 Teacher/Student Agent 的决策，也不是维护学习成长树。目标是在已有学习画像、个人教学大纲和学习树结构的基础上，生成一组可解释、可裁剪、可排序的学习路径候选：

```text
API/Agent payload
  -> personal_recommendation_task
      -> tasks.personal_recommendation.agent_runtime
      -> tasks.personal_recommendation.agent_tools
      -> load_request_context
      -> search_recommendation_context
      -> run_recommendation_route
  -> profile + syllabus learning tree
  -> state perception
  -> candidate generation
  -> hard prune
  -> score
  -> soft prune
  -> IB-GRPO selection
  -> return graph + candidates + selected + best_path
```

## 0. 新增的常量定义

本次迁移没有新增 `constant.py` 级别的全局常量。

路径推荐运行参数由 task 入口参数收口：

```python
L_max = 6
T_max = 100
K = 20
beam_width = 6
```

选择器当前使用：

```python
IB_constraints = {"E": 0.0}
iterations = 20
N = 1
```

评分权重定义在 `tasks/personal_recommendation/evaluator.py`：

```python
DEFAULT_WEIGHTS = {
    "E": 0.4,
    "D": 0.2,
    "R": 0.2,
    "P": 0.2,
}
```

## 1. 影响的文件范围

核心实现：

```text
tasks/personal_recommendation_task.py
tasks/personal_recommendation/
  agent_contracts.py
  agent_runtime.py
  agent_tools.py
  __init__.py
  candidate_generator.py
  evaluator.py
  graph_adapter.py
  perception.py
  pruning.py
  sample_data.py
  selector_ib_grpo.py
tasks/syllabus_to_learning_tree.py
```

API 接入：

```text
blueprint/learning_api.py
```

测试：

```text
tests/test_personal_recommendation_task.py
tests/test_personal_recommendation_api.py
tests/test_personal_recommendation_agent_choice.py
tests/TEST_REPORT.md
```

实验与 benchmark：

```text
experiments/learning_path_recommendation/
  README.md
  benchmarks/benchmark_perf.py
  benchmarks/results/
```

已清理：

```text
prototype_recommendation/
```

## 2. 函数级收口的完整数据流

### Agent 调用

```text
run_personal_recommendation_agent
  -> load_request_context
  -> search_recommendation_context
      -> search_tool
      -> RAG / 多路检索 reasoning_paths
  -> run_recommendation_route
      -> run_recommendation_route_from_payload
  -> return PersonalRecommendationResult
```

边界：

- RAG/多路检索属于 Agent 工具，不进入候选生成、剪枝、评分算法内部。
- 剪枝、评分、路径选择仍属于 `personal_recommendation_task.py` 的确定性算法链路。
- Agent 只负责调度工具和传递上下文，不自己编造推荐路径，也不写真实 RAG 图谱。

### API 调用

```text
POST /api/personal_recommendation
  -> run_recommendation_route_from_payload
  -> run_recommendation_route
  -> return recommendation result
```

输入 payload：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "goals": ["HBase RowKey 设计"],
  "L_max": 6,
  "T_max": 100,
  "K": 20,
  "beam_width": 6
}
```

### Task 内部流程

```text
run_recommendation_route
  -> build_recommendation_profile
      -> get_or_build_learning_profile
      -> fallback minimal profile
  -> load_recommendation_learning_tree
      -> get_syllabus_by_id
      -> load syllabus JSON
      -> syllabus_json_to_learning_tree
      -> fallback sample_learning_tree
  -> generate_state
  -> generate candidate paths
  -> hard_prune
  -> score
  -> soft_prune_by_dominance
  -> score again
  -> ib_grpo_select
  -> build graph/candidates/selected public response
```

### 输出

```json
{
  "success": true,
  "graph": {
    "nodes": [
      {
        "id": "node_1",
        "title": "HBase RowKey 设计",
        "difficulty": 2,
        "learning_time_est": 4,
        "outcomes": ["rowkey_design"],
        "prerequisites": []
      }
    ],
    "edges": [
      {
        "edge_id": "node_1->node_2",
        "source": "node_1",
        "target": "node_2",
        "type": "prerequisite"
      }
    ]
  },
  "candidates": [
    {
      "path": ["node_1", "node_2"],
      "path_edges": [
        {"edge_id": "node_1->node_2", "source": "node_1", "target": "node_2"}
      ],
      "total_time": 45,
      "skills": ["rowkey_design"],
      "selected": false,
      "rank": 1,
      "scores": {
        "E": 0.8,
        "D": 0.5,
        "R": 0.7,
        "P": 0.5,
        "total": 0.66
      }
    }
  ],
  "selected": [
    {
      "path": ["node_1", "node_2"],
      "path_edges": [
        {"edge_id": "node_1->node_2", "source": "node_1", "target": "node_2"}
      ],
      "skills": ["rowkey_design"],
      "selected": true,
      "scores": {}
    }
  ],
  "best_path": {
    "path": ["node_1", "node_2"],
    "selected": true
  },
  "error_message": "",
  "error_code": ""
}
```

前端推荐网展示契约：

- `graph.nodes` 是可展示节点全集。
- `graph.edges` 是推荐图中的先修关系边全集。
- `candidates[].path` 是候选路线节点序列。
- `candidates[].path_edges` 是该候选路线的连续路径边，前端可直接用于路线高亮。
- `selected[]` 是选择器返回的推荐路径集合。
- `best_path` 是前端默认高亮路径；当选择器没有返回结果时，回退为候选列表第一条。
- `skills` 已统一序列化为 list，避免 Python `set` 影响 JSON 输出。

错误输出：

```json
{
  "success": false,
  "candidates": [],
  "selected": [],
  "error_message": "missing user_id",
  "error_code": "missing_fields"
}
```

## 3. 精确到输入输出的函数级收口

### `run_recommendation_route_from_payload(payload: dict) -> dict`

职责：

- 接收 API/Agent payload。
- 校验 `user_id`。
- 提取 `syllabus_id`、`goals`、`L_max`、`T_max`、`K`、`beam_width`。
- 调用 `run_recommendation_route`。

缺少 `user_id` 时返回 structured error，不抛裸异常。

### `run_personal_recommendation_agent(payload: dict) -> PersonalRecommendationResult`

职责：

- 接收总 Agent 或测试传入的原始推荐 payload。
- 通过 LLM 工具调用完成推荐调度。
- 输出 `PersonalRecommendationResult`。

工具顺序预期：

```text
load_request_context
search_recommendation_context
run_recommendation_route
```

其中：

- `load_request_context` 只读取 payload，不执行推荐算法。
- `search_recommendation_context` 调用公共 `search_tool`，检索总知识库和 reasoning paths。
- `run_recommendation_route` 调用确定性推荐 task，并把 `rag_context` 放入 payload 供 overlay、审计和后续扩展使用。

测试中 `search_tool` 可以 mock；真实运行时由 `graph_name` 或 `SEARCH_TOOL_GRAPH_NAME` 指定检索图。

### `run_recommendation_route(...) -> dict`

职责：

- 构建学习画像。
- 构建推荐用 learning tree。
- 生成候选路径。
- 执行硬裁剪、软裁剪和最终选择。
- 返回前端可直接渲染的推荐图、候选路径、选中路径和默认高亮路径。

关键边界：

- `goals` 优先使用调用方传入值。
- 调用方未传 `goals` 时，回退到画像中的 `learning_goals`。
- 候选路径为空时仍返回 `success=true`，由上层决定是否追问或更换目标。
- `graph` 始终基于当前 learning tree 构建，即使候选路径为空也可用于前端展示可推荐网络。
- `best_path` 优先来自 `selected[0]`，没有选中路径时回退到 `candidates[0]`，再没有候选时为 `null`。

### `build_recommendation_profile(user_id: int, syllabus_id: int | None) -> dict`

职责：

- 调用学习画像能力获取用户画像。
- 读取失败时返回最小可运行 profile。

最小 profile：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "knowledge_levels": {},
  "learning_goals": []
}
```

### `load_recommendation_learning_tree(syllabus_id: int | None) -> dict`

职责：

- 有 `syllabus_id` 时读取 syllabus JSON。
- 转换为推荐算法使用的 learning tree。
- 无 `syllabus_id` 或读取失败时回退到 sample tree。

该函数不负责写数据库，不负责维护学生成长树。

### `syllabus_json_to_learning_tree(syllabus_json: dict) -> dict`

职责：

- 将个人教学大纲 JSON 转换为推荐算法使用的节点、边和元数据结构。
- 保持输出结构和 `tasks.personal_recommendation` 算法模块兼容。

### `generate_state(profile: dict, learning_tree: dict) -> tuple[dict, list[str]]`

职责：

- 从用户画像和 learning tree 中提取算法状态。
- 输出可起步节点 `starts`。
- 该阶段只做感知和状态构造，不生成推荐结果。

### `generate(...) -> list[dict]`

职责：

- 基于起点、目标、树结构和搜索参数生成候选路径。
- 路径生成使用 `GraphAdapter` 读取图结构。
- 当前测试覆盖了内存图适配器路径读取。

### `hard_prune(...) -> list[dict]`

职责：

- 删除不满足硬约束的候选路径。
- 支持基于 `blocked_nodes` 的节点排除。

### `score(path_item: dict, state: dict, learning_tree: dict) -> dict`

职责：

- 为候选路径计算多维评分。
- 当前维度包括 `E`、`D`、`R`、`P` 与 `total`。
- `P` 当前为可替换的偏好占位分数，后续可接入更细粒度的偏好模型。

### `soft_prune_by_dominance(candidates: list[dict], scores: list[dict]) -> list[dict]`

职责：

- 基于支配关系做软裁剪。
- 保留综合表现更优或不可被完全支配的候选路径。

### `ib_grpo_select(...) -> list[dict]`

职责：

- 在候选路径中做最终选择。
- 当前 task 将其作为选择器调用，失败时降级为空选中结果，不影响候选路径返回。

### `_build_recommendation_graph(learning_tree: dict) -> dict`

职责：

- 将推荐算法内部的 learning tree 转换为前端图结构。
- 输出 `nodes` 与 `edges`。
- `edges` 由每个节点的 `prerequisites` 反推，方向为 `prerequisite -> current_node`。

输出：

```json
{
  "nodes": [{"id": "n1", "title": "Start"}],
  "edges": [{"edge_id": "n1->n2", "source": "n1", "target": "n2", "type": "prerequisite"}]
}
```

### `_serialize_path_item(candidate: dict, candidate_score: dict | None, ...) -> dict`

职责：

- 将内部候选路径转换为 API/前端安全结构。
- 将 `set`、`tuple` 等 Python 对象转换为 JSON 可序列化对象。
- 补充 `path_edges`、`selected`、`rank` 和 `scores`。

## 4. 测试用例的构建描述

测试命令：

```bash
python -m pytest -q tests/test_personal_recommendation_task.py tests/test_personal_recommendation_api.py
```

真实 LLM Agent 工具选择测试：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_personal_recommendation_agent_choice.py -m llm
```

可选真实 RAG 评估：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py -m llm
```

可选环境变量：

```text
PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME=RAG
PERSONAL_RECOMMENDATION_RAG_QUERY=<query>
PERSONAL_RECOMMENDATION_RAG_TOP_K=5
PERSONAL_RECOMMENDATION_ROUTE_K=10
PERSONAL_RECOMMENDATION_BEAM_WIDTH=8
```

测试层面的默认图名固定为 `RAG`；环境变量只用于临时覆盖。

当前覆盖：

- task 正常生成候选路径。
- 缺少 `user_id` 返回 `missing_fields`。
- 内存图适配器可读取节点并生成路径。
- API 可读取临时 syllabus JSON 并返回推荐结果。
- task 返回 `graph.nodes`、`graph.edges`、`path_edges`、`best_path`。
- 候选路径中的 `skills` 为 JSON 友好的 list。
- API 缺少 `user_id` 返回 400。
- 非 LLM 单测验证 RAG 工具位于 Agent 层，推荐算法通过 `run_recommendation_route` 工具调用。
- mock RAG 闭环验证 `rag_context -> run_recommendation_route -> graph/candidates/selected/best_path` 可以形成前端可渲染推荐图。
- 闭环测试断言 `best_path` 来自候选路径，且路径节点、路径边都存在于返回的 `graph.nodes` / `graph.edges` 中。
- LLM opt-in 测试验证真实模型会选择 `load_request_context -> search_recommendation_context -> run_recommendation_route`。

测试产物：

```text
tests/artifacts/personal_recommendation/mock_rag_route_graph_closure/route_result.json
tests/artifacts/personal_recommendation/agent_choice/agent_choice_result.json
tests/artifacts/personal_recommendation/agent_choice_real_rag/agent_choice_real_rag_result.json
```

其中 `mock_rag_route_graph_closure` 保存 mock RAG 到推荐图的完整闭环结果，`agent_choice` 保存真实 LLM 工具选择链路和最终 `PersonalRecommendationResult`，`agent_choice_real_rag` 保存可选真实 RAG 返回和推荐闭环结果。

测试边界：

- 默认单元/API 测试不依赖真实 LLM。
- 不依赖真实知识库。
- 默认 LLM 集成测试使用 mock RAG；如需评估真实检索质量，使用 `RUN_REAL_RAG_TESTS=1` 打开可选真实 RAG 链路。
- API 测试使用临时 syllabus JSON 和测试数据库上下文。
- `test_personal_recommendation_agent_choice.py` 使用真实 LLM，RAG 使用 mock，profile/tree 使用固定 fixture，推荐算法走真实 `run_recommendation_route_from_payload` 链路，重点验证 Agent 工具选择和推荐闭环能力。

最近一次本地验证结果：

```text
7 passed, 1 deselected, 2 warnings
```

benchmark smoke：

```bash
python experiments/learning_path_recommendation/benchmarks/benchmark_perf.py --nodes 20 --runs 1 --out /tmp/lianjue_reco_bench_smoke_2
```

结果：

```text
2 个 benchmark 配置均完成，无运行错误。
```

## 5. 新增的持久化内容

本功能没有新增运行时持久化表。

推荐结果当前作为 API/Task 返回值即时生成，不写入数据库。已有 syllabus JSON 由现有 syllabus 存储链路提供，推荐 task 只读取，不修改。

实验输出保存在：

```text
experiments/learning_path_recommendation/benchmarks/results/
```

这些结果用于实验对比，不作为生产运行数据。

## 6. 当前限制与后续边界

- 当前学习路径推荐包含一层薄 LLM Agent wrapper 和一层确定性 task 算法。总 Agent 可以调用 Agent，也可以在内部场景直接调用 task。
- CI 级测试不触发真实 LLM 和真实知识库访问；真实 Agent 工具选择测试通过 `RUN_LLM_TESTS=1` 手动开启。
- `KnowLionGraphAdapter` 属于后续真实图谱接入边界，当前主测试覆盖的是内存图适配器和 syllabus 转换链路。
- RAG/多路检索属于 Agent 工具层，不写入推荐算法内部。这样后续可以替换为五路检索、reasoning path 检索或 mock 检索，而不影响剪枝、评分和选择算法。
- `P` 偏好评分目前为占位实现，后续可接入学习画像中的偏好、节奏、资源类型倾向。
- 推荐结果未持久化；如果后续需要审计、回放或 A/B 对比，应新增独立 recommendation log，而不是写入学习成长树。
