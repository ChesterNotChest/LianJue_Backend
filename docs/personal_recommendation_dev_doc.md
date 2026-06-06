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

路径被用户或总 Agent 采纳后，进入独立的学习计划确认链路：

```text
recommendation result
  -> accept_recommendation_path
  -> learning_plan manifest.jsonl
  -> active plan + ordered steps
  -> optional step status update
  -> optional study_graph progress sync
```

## 当前同步状态

本模块当前仍是学习路径推荐的唯一 task 门户。Total Agent 通过 `run_recommendation_route_from_payload` 触发推荐，通过 `accept_recommendation_path` 创建 active learning plan；推荐本身不直接写入 study graph，只有后续 plan step 状态更新时才由调用方显式同步学习成长树。

系统职责按“画像描述状态、路径决定顺序、资源服务当前节点”分层：

- 学习画像回答“学生当前是什么状态”，不直接决定下一步学什么。
- 学习路径推荐回答“接下来按什么阶段、节点和优先级学习”，是个性化学习闭环的顺序决策层。
- 资源生成回答“围绕当前路径节点给什么学习材料”，不自行决定学习顺序。
- 资源展示/推送是路径当前节点的呈现动作，不是独立的推荐系统。
- 学习反馈和 study graph 事件会影响后续画像、路径和资源策略，但推荐模块本身只生成候选路径，不直接写学习树。

RAG 在本模块中是推荐图的软增强，不是确定性前置条件。`rag_overlay` 会尝试把检索结果转成临时节点、临时边和图结构提示，但不会修改原始 syllabus JSON。当前已补充质量门禁：字符级、停用词级、低质量 reason edge 不进入推荐图，避免出现 `Hadoop-HBase: d, e, f...` 这类噪声边把候选路径打散。

每周知识点拆解优先使用 Agent/RAG concept decomposer；规则 fallback 只作为可诊断兜底，不作为通用学科拆解首选。fallback 输出必须带 `decomposition_method`、`fallback_tag` 和较低 confidence，方便上层识别低置信来源。

Total Agent E2E 的推荐回归入口已统一到：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

推荐模块自身的噪声 RAG 回归可用：

```bash
python -m pytest -q tests/test_personal_recommendation_task.py::test_rag_overlay_ignores_character_level_reasoning_edges tests/test_personal_recommendation_task.py::test_personal_recommendation_mock_rag_route_graph_closes -rs
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
  graph_builder.py
  learning_plan.py
  perception.py
  pruning.py
  rag_overlay.py
  sample_data.py
  selector_ib_grpo.py
  service.py
  syllabus_adapter.py
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

入口边界：

- `tasks/personal_recommendation_task.py` 是路径推荐的唯一跨模块 task 门户。
- `tasks/personal_recommendation/` 只放包内实现，外部 API 或其他 Agent 不应直接依赖包内函数。
- 原 `tasks/syllabus_to_learning_tree.py` 已迁入 `tasks/personal_recommendation/syllabus_adapter.py`，不再保留外层转发文件。
- 公共检索工具位于 `tasks/common/search_tool.py`；推荐 Agent 通过 `tasks.personal_recommendation.agent_tools` 调用它。
- 推荐 Agent 模型构造统一走 `tasks.common.agent_model.build_openai_compatible_model`，兼容 DashScope 工具调用时的 thinking/tool_choice 限制。

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
  -> build_recommendation_graph_tree
      -> apply rag_overlay
      -> apply profile state
      -> apply readonly study_graph_state
  -> generate_state
  -> generate candidate paths
  -> hard_prune
  -> score
  -> soft_prune_by_dominance
  -> score again
  -> ib_grpo_select
  -> build graph/candidates/selected public response
```

生成链路边界：

- `study_graph_state` 只作为只读输入，不写回学习成长树。
- `rag_overlay` 和画像/study_graph 状态只进入推荐用图和评分解释，不污染原始 syllabus JSON。
- 推荐图从“syllabus 直接映射树”扩展为 `syllabus_adapter -> graph_builder -> candidate_generator -> evaluator -> selector`。

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
- 构建推荐用图，融合 syllabus 主干、RAG overlay、画像状态和只读 `study_graph_state`。
- 生成候选路径。
- 执行硬裁剪、软裁剪和最终选择。
- 返回前端可直接渲染的推荐图、候选路径、选中路径和默认高亮路径。

关键边界：

- `goals` 优先使用调用方传入值。
- 调用方未传 `goals` 时，回退到画像中的 `learning_goals`。
- 候选路径为空时仍返回 `success=true`，由上层决定是否追问或更换目标。
- `graph` 始终基于当前 learning tree 构建，即使候选路径为空也可用于前端展示可推荐网络。
- `best_path` 优先来自 `selected[0]`，没有选中路径时回退到 `candidates[0]`，再没有候选时为 `null`。
- `study_graph_state` 只用于避开已完成、阻塞或薄弱节点等推荐约束，不负责写入学习成长树。

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
- 对 `period` 教学周/课次结构，生成语义化每周知识点 anchor，而不是把 `week_x` 当主学习节点。
- 当前已接入每周知识点 Agent/RAG 破拆链路，能够把通用语义增强过的每周知识点派生为推荐侧 concept graph；该产物只作为推荐侧派生图，不覆盖原始 syllabus。
- 规则型 concept fallback 保留为可诊断兜底，只在 Agent 不可用、超时或输出无法通过本地校验时触发。

`period` 结构输出边界：

```text
period item
  -> syllabus_period anchor
  -> Agent/RAG concept decomposition
  -> validate_concept_graph
  -> syllabus_period_concept nodes
  -> recommendation learning_tree
```

Agent 破拆节点会显式标记结构来源、置信度和证据来源：

```json
{
  "title": "RowKey设计",
  "node_source": "syllabus_period_concept",
  "decomposition_method": "agent",
  "fallback_tag": "",
  "source_period": {"week_index": "6", "title": "分布式数据库中典型技术HBase"},
  "confidence": 0.9,
  "reliability": 0.9,
  "matched_by": ["text"],
  "reason": "Explicitly mentioned in enhanced_content as key design aspect",
  "prerequisites": ["HBase数据模型"]
}
```

真实 LLM/RAG 验证中，HBase period 可以被破拆为：

```text
HBase概述
HBase数据模型
RowKey设计
Region划分
预分区
热点规避
HBase架构
HBase与HDFS关系
```

并生成先修边：

```text
HBase数据模型 -> RowKey设计
RowKey设计 -> Region划分
Region划分 -> 预分区
RowKey设计 -> 热点规避
Region划分 -> 热点规避
预分区 -> 热点规避
```

规则 fallback 节点同样会显式标记来源，方便推荐 Agent 或总 Agent 识别低可信路径：

```json
{
  "title": "RowKey",
  "node_source": "syllabus_period_concept",
  "decomposition_method": "rule_fallback",
  "fallback_tag": "period_concept_rule_fallback",
  "source_period": {"week_index": "6", "title": "分布式数据库中典型技术HBase"},
  "confidence": 0.75,
  "matched_by": ["RowKey"],
  "implied": false
}
```

HBase 这类明确主题可以低置信度派生 RowKey、Region、预分区、热点规避等 implied concept：

```json
{
  "title": "热点规避",
  "decomposition_method": "rule_fallback",
  "fallback_tag": "period_concept_rule_implied_fallback",
  "confidence": 0.55,
  "matched_by": ["implied_by:HBase"],
  "implied": true
}
```

当前边界：

- Agent/RAG concept decomposer 是默认破拆方向，输出 `decomposition_method="agent"`。
- 规则 fallback 是可诊断兜底，不作为通用学科破拆首选。
- Agent 成功输出时不会混入规则 fallback；Agent 失败时输出 `fallback_used=true` 和 `fallback_summary`。
- 本地 validator 负责接住真实模型常见 schema 漂移，例如 `matched_by` 字符串、`from/to` 边字段，并归一为内部 schema。
- Agent 破拆通过 mock structured output 做 CI 测试；真实 LLM/RAG 放 opt-in 测试。
- 原始 syllabus JSON 不被写回；派生节点通过 `source_period` 引用原始每周知识点。

### `run_period_concept_decomposer_agent(payload: dict) -> dict`

职责：

- 读取每周知识点上下文。
- 检索或复用 RAG evidence。
- 调用 LLM Agent 生成 concept graph proposal。
- 通过本地 `validate_concept_graph` 归一化、校验和兜底。

工具顺序：

```text
read_period_context
retrieve_period_evidence
decompose_period_concepts
validate_concept_graph
```

输出：

```json
{
  "success": true,
  "method": "agent",
  "fallback_used": false,
  "concepts": [],
  "edges": [],
  "tool_trace": [
    "read_period_context",
    "retrieve_period_evidence",
    "decompose_period_concepts",
    "validate_concept_graph"
  ],
  "error_code": "",
  "error_message": ""
}
```

调试开关：

```text
PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG=1
```

开启后 artifact 会包含 `debug.concept_proposal` 和压缩后的 `debug.rag_context_summary`，用于判断模型 schema 漂移、RAG evidence 质量和 fallback 触发原因。

### `build_recommendation_graph_tree(learning_tree: dict, rag_overlay: dict | None, profile: dict | None, study_graph_state: dict | None) -> dict`

职责：

- 将原始 syllabus learning tree 转换为推荐用图。
- 合并 RAG 命中的节点、临时边和图结构置信度。
- 标注画像状态和只读学习进度状态。

关键边界：

- 不原地修改原始 `learning_tree`。
- RAG 边和 RAG 命中只作为推荐用图属性进入候选生成和评分。
- `study_graph_state` 只标注 `completed`、`blocked`、`weak` 等状态，不触发持久化。

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

### `accept_recommendation_path(user_id: int, syllabus_id: int | None, recommendation_result: dict, candidate_index: int | None = None, source: str = "recommendation") -> dict`

职责：

- 将用户或总 Agent 采纳的推荐路径写成 active learning plan。
- 旧 active plan 通过 manifest 事件标记为 `superseded`。
- 为路径节点生成有序 plan steps。

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
      "node_id": "n2",
      "title": "Statistics 101",
      "status": "active",
      "order_index": 0,
      "resource_ids": []
    }
  ]
}
```

### `update_learning_plan_step_status(plan_id: str, step_id: str, status: str, *, sync_study_graph: bool = False) -> dict`

职责：

- 更新 learning plan step 状态。
- 默认只追加 manifest 事件，不写 `study_graph`。
- 当调用方显式开启 `sync_study_graph` 时，才把 step 进度同步给 `study_graph_task`。

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

每周知识点 Agent 破拆真实 LLM/RAG 验证：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1 PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py::test_period_concept_decomposer_real_llm_rag_optional -m llm
```

如需查看 Agent 原始 proposal 和 RAG evidence 摘要，可打开调试开关：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1 PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG=1 PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py::test_period_concept_decomposer_real_llm_rag_optional -m llm
```

可选环境变量：

```text
PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME=RAG
PERSONAL_RECOMMENDATION_RAG_QUERY=<query>
PERSONAL_RECOMMENDATION_RAG_TOP_K=5
PERSONAL_RECOMMENDATION_ROUTE_K=10
PERSONAL_RECOMMENDATION_BEAM_WIDTH=8
PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1
PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG=1
PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG
PERSONAL_RECOMMENDATION_DECOMPOSER_TOP_K=5
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
- 每周知识点 concept decomposer 单测覆盖 mock Agent 输出、本地 schema 漂移归一、Agent invalid 后 rule fallback、RAG context 归一和原始 period 不被修改。
- syllabus adapter 测试覆盖注入 Agent concept 后输出 `decomposition_method="agent"`，以及无 Agent 时保留 `rule_fallback` 兜底。
- task 测试覆盖 Agent 破拆概念进入推荐路径，以及 fallback 节点在候选路径中形成 `fallback_dependency` 诊断字段。
- 真实 LLM/RAG opt-in 测试验证每周知识点 Agent 会按工具链完成 `read_period_context -> retrieve_period_evidence -> decompose_period_concepts -> validate_concept_graph`，并产出 `method="agent"` 的 concept graph。

测试产物：

```text
tests/artifacts/personal_recommendation/mock_rag_route_graph_closure/route_result.json
tests/artifacts/personal_recommendation/agent_choice/agent_choice_result.json
tests/artifacts/personal_recommendation/agent_choice_real_rag/agent_choice_real_rag_result.json
tests/artifacts/personal_recommendation/concept_decomposer_real_rag/concept_decomposer_real_rag_result.json
```

其中 `mock_rag_route_graph_closure` 保存 mock RAG 到推荐图的完整闭环结果，`agent_choice` 保存真实 LLM 工具选择链路和最终 `PersonalRecommendationResult`，`agent_choice_real_rag` 保存可选真实 RAG 返回和推荐闭环结果，`concept_decomposer_real_rag` 保存每周知识点 Agent/RAG 破拆的概念、边、fallback 状态和可选 debug evidence。

测试边界：

- 默认单元/API 测试不依赖真实 LLM。
- 不依赖真实知识库。
- 默认 LLM 集成测试使用 mock RAG；如需评估真实检索质量，使用 `RUN_REAL_RAG_TESTS=1` 打开可选真实 RAG 链路。
- API 测试使用临时 syllabus JSON 和测试数据库上下文。
- `test_personal_recommendation_agent_choice.py` 使用真实 LLM，RAG 使用 mock，profile/tree 使用固定 fixture，推荐算法走真实 `run_recommendation_route_from_payload` 链路，重点验证 Agent 工具选择和推荐闭环能力。
- 每周知识点 Agent 破拆默认不访问真实 LLM/RAG；真实链路必须同时打开 `RUN_LLM_TESTS=1`、`RUN_REAL_RAG_TESTS=1` 和 `PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1`。

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

本功能没有新增运行时数据库表。

推荐生成结果当前作为 API/Task 返回值即时生成，不写入数据库。已有 syllabus JSON 由现有 syllabus 存储链路提供，推荐 task 只读取，不修改。

被用户或总 Agent 确认采纳的路径可以写入独立 learning plan manifest：

```text
learning_plan/user_{user_id}/syllabus_{syllabus_id}/manifest.jsonl
```

持久化边界：

- `accept_recommendation_path(...)` 从 `best_path` 或指定 `candidate_index` 中创建 active plan。
- 每个 plan step 保存 `node_id`、`title`、`outcomes`、`order_index`、`status` 和 `resource_ids`。
- 新 plan 创建时，旧 active plan 通过 `plan_superseded` 事件逻辑失效，不物理覆盖历史。
- `update_learning_plan_step_status(...)` 只更新 plan step 状态；如调用方显式开启同步，才把 step 进度传给 `study_graph_task`。
- manifest 是当前过渡形态，后续统一 `manifest -> MySQL` 时再迁移为正式表。

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
- learning plan 当前只做 manifest 级路径确认和执行状态记录；正式落库、审计、A/B 对比和跨设备恢复应在后续 `manifest -> MySQL` 迁移中统一完成。
