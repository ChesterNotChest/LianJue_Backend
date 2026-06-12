# Recommendation Snapshot contract

本文档是“推荐大网展示缓存”收口计划。它替代 `recommendation_snapshot_small_plan.md` 中偏草案的部分，用真实代码边界约束后续实现。

## 0. 重新评估结论

复用效率较高，不需要重写推荐算法：

- 推荐大网已经由 `tasks/personal_recommendation/service.py::run_recommendation_route` 返回，包含 `graph / candidates / selected / best_path / rag_overlay / planning_hints`。
- 已选路径落地已经由 `tasks/personal_recommendation/learning_plan.py::accept_recommendation_path` 完成。
- 生产持久化模式已经集中在 `schemas/agent_runtime_state.py` 和各模块 storage 中，可以复用“生产 SQL、测试显式 file backend”的口径。
- 前端推荐入口已经有 `POST /api/personal_recommendation`，可在该 API 层保存展示缓存，不需要新增一套推荐入口。

必须修正的边界：

- `run_recommendation_route(...)` 必须保持纯计算，不产生数据库副作用。
- `run_recommendation_route_from_payload(...)` 默认也不应强制写库，否则会破坏大量内部调用和无 app context 单测。推荐大网缓存保存应由 API 层或显式 task 函数触发。
- Recommendation Snapshot 保存的是“推荐展示图 + 排序/剪枝后的候选路径”，它是前端展示缓存，不是推荐 Agent 的长期业务状态，也不是原始搜索过程中的全部中间候选。若后续需要算法审计，可另加 `debug_json`。
- Recommendation Snapshot 不属于学生学习事实，不写入 `study_graph`。
- `learning_plan` 仍只表示用户采纳后的执行计划，不复制完整推荐图。
- Total Agent 后续学习推进不读取 Recommendation Snapshot；它继续读取 active plan、profile、study graph 和资源元数据。
- 手选路径应优先通过 `recommendation_id + candidate_index` 完成；旧的 `accept_recommendation_path(..., recommendation_result, candidate_index)` 保持兼容。

## 阶段 1：新增 Recommendation Snapshot 持久化层

### 0. 新增常量定义

建议放在 `tasks/personal_recommendation/snapshot.py`：

```python
RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION = "recommendation_snapshot.v1"
RECOMMENDATION_SNAPSHOT_ID_PREFIX = "recommendation"

RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED = "proposed"
RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED = "accepted"
RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED = "expired"

RECOMMENDATION_SNAPSHOT_ROOT_DIR = "personal_recommendation/recommendation_snapshot"
RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV = "RECOMMENDATION_SNAPSHOT_FILE_BACKEND"
```

暂不实现 `superseded` 作为强语义。后续如果要在接受新 plan 时联动旧 snapshot，再扩展该状态。

### 1. 影响的文件范围

新增：

- `tasks/personal_recommendation/snapshot.py`

修改：

- `schemas/agent_runtime_state.py`
  - 新增 `RecommendationSnapshot` SQLAlchemy model。
- `tasks/personal_recommendation_task.py`
  - 导出 snapshot task 函数和常量。
- `tests/test_agent_runtime_db_persistence.py`
  - 覆盖 SQL backend 持久化。
- `tests/test_personal_recommendation_snapshot.py`
  - 覆盖 task 级保存、读取、列表和显式 file backend。

### 2. 函数级收口的完整数据流

```text
recommendation_result
  -> save_recommendation_snapshot
     -> normalize user_id / syllabus_id
     -> generate recommendation_id
     -> compact summary
     -> persist SQL RecommendationSnapshot
  -> get_recommendation_snapshot
     -> read SQL row
     -> reconstruct recommendation_result bundle
  -> list_recommendation_snapshots
     -> read recent rows
     -> return summary list only
```

测试或离线 artifact：

```text
RECOMMENDATION_SNAPSHOT_FILE_BACKEND=1 or PERSONAL_RECOMMENDATION_ROOT set
  -> personal_recommendation/recommendation_snapshot/user_{user_id}/syllabus_{syllabus_id}/{recommendation_id}.json
```

生产环境：

```text
must have Flask app context + SQL database
no silent fallback to repo manifest
```

### 3. 精确到输入输出的函数级收口

#### `save_recommendation_snapshot(...) -> dict`

输入：

```python
save_recommendation_snapshot(
    user_id: int,
    syllabus_id: int | None,
    recommendation_result: dict,
    *,
    request_payload: dict | None = None,
    session_id: str | None = None,
    status: str = RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
) -> dict
```

输出：

```json
{
  "success": true,
  "recommendation_id": "recommendation_20260610191033_d27634",
  "status": "proposed",
  "schema_version": "recommendation_snapshot.v1",
  "created_at": 1781118633,
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 校验 `user_id` 必须为正整数。
- `syllabus_id` 可为空；不为空时必须为正整数。
- `recommendation_result.graph.nodes` 必须是 list，否则返回 `missing_graph`。
- 原样保存：
  - `graph`
  - `candidates`
  - `selected`
  - `best_path`
  - `rag_overlay`
  - `planning_hints`
- 从 `request_payload` 中抽取：
  - `goals`
  - `learning_goal`
  - `message`
  - `question`
  - `session_id`
- 生成 `result_summary_json`：
  - `candidate_count`
  - `selected_count`
  - `node_count`
  - `edge_count`
  - `best_path`
  - `best_path_titles`
- 不修改 `recommendation_result` 本体，除非调用方自己把返回的 `recommendation_id` 合并进去。

#### `get_recommendation_snapshot(recommendation_id: str) -> dict`

输出：

```json
{
  "success": true,
  "snapshot": {
    "recommendation_id": "recommendation_...",
    "user_id": 126,
    "syllabus_id": 29,
    "status": "proposed",
    "schema_version": "recommendation_snapshot.v1",
    "recommendation": {
      "graph": {},
      "candidates": [],
      "selected": [],
      "best_path": {},
      "rag_overlay": {},
      "planning_hints": {}
    },
    "summary": {},
    "created_at": 1781118633,
    "updated_at": 1781118633
  },
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 不调用推荐算法。
- 不调用 LLM / RAG。
- 只从 SQL 或显式 file backend 读取快照。
- 找不到返回 `not_found`。

#### `list_recommendation_snapshots(...) -> dict`

输入：

```python
list_recommendation_snapshots(
    user_id: int,
    syllabus_id: int | None = None,
    limit: int = 20,
) -> dict
```

输出：

```json
{
  "success": true,
  "snapshots": [
    {
      "recommendation_id": "recommendation_...",
      "user_id": 126,
      "syllabus_id": 29,
      "status": "proposed",
      "candidate_count": 3,
      "node_count": 12,
      "edge_count": 14,
      "best_path": ["hbase_intro", "rowkey_design"],
      "best_path_titles": ["HBase 基础", "HBase RowKey 设计"],
      "accepted_plan_id": null,
      "accepted_candidate_index": null,
      "created_at": 1781118633
    }
  ],
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 只返回摘要，不返回完整 `graph_json`，避免列表接口过重。
- `limit` clamp 到合理范围，例如 `1..100`。
- 默认按 `created_at desc` 排序。

### 4. 测试用例的构建描述

新增 `tests/test_personal_recommendation_snapshot.py`：

```text
test_save_recommendation_snapshot_file_backend
test_get_recommendation_snapshot_returns_full_recommendation
test_list_recommendation_snapshots_returns_summary_only
test_save_recommendation_snapshot_rejects_missing_graph
```

扩展 `tests/test_agent_runtime_db_persistence.py`：

```text
test_recommendation_snapshot_uses_database_backend_when_app_context
test_runtime_persistence_does_not_silently_fallback_to_manifest
```

核心断言：

- SQL 中有 `RecommendationSnapshot`。
- `get_recommendation_snapshot` 能恢复 `graph/candidates/best_path`。
- 列表结果不包含完整 `graph`。
- 无 DB app context 且未显式 file backend 时抛出 RuntimeError。

## 阶段 2：推荐 API 保存展示缓存并暴露读取接口

### 0. 新增常量定义

建议放在 `blueprint/learning_api.py` 或 snapshot 模块复用：

```python
DEFAULT_RECOMMENDATION_SNAPSHOT_LIMIT = 20
MAX_RECOMMENDATION_SNAPSHOT_LIMIT = 100
```

### 1. 影响的文件范围

修改：

- `blueprint/learning_api.py`
  - `POST /api/personal_recommendation` 成功后保存展示缓存 snapshot。
  - 新增 snapshot 列表、详情接口。
- `tasks/personal_recommendation_task.py`
  - 导出 `save_recommendation_snapshot`、`get_recommendation_snapshot`、`list_recommendation_snapshots`。
- `tests/test_personal_recommendation_api.py`
  - 覆盖 API 返回 `recommendation_id` 和读取快照。

不修改：

- `tasks/personal_recommendation/service.py::run_recommendation_route`
- `tasks/personal_recommendation/service.py::run_recommendation_route_from_payload`

### 2. 函数级收口的完整数据流

```text
POST /api/personal_recommendation
  -> run_recommendation_route_from_payload(data)
  -> if success and graph.nodes and data.persist_snapshot is not False
       save_recommendation_snapshot(...)
       merge recommendation_id into response
     else
       return recommendation result without snapshot

GET /api/recommendations
  -> list_recommendation_snapshots(user_id, syllabus_id, limit)

GET /api/recommendations/<recommendation_id>
  -> get_recommendation_snapshot(recommendation_id)
```

### 3. 精确到输入输出的函数级收口

#### `POST /api/personal_recommendation`

输入：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "goals": ["掌握 HBase RowKey 热点规避"],
  "session_id": "sess_demo_001",
  "persist_snapshot": true
}
```

输出：

```json
{
  "success": true,
  "schema_version": "personal_recommendation.v2",
  "recommendation_id": "recommendation_...",
  "snapshot_status": "proposed",
  "graph": {},
  "candidates": [],
  "selected": [],
  "best_path": {},
  "planning_hints": {},
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- API 层拥有数据库 app context，因此默认保存 snapshot。
- 如果 `persist_snapshot` 显式为 `false`，只返回推荐结果，不写 snapshot。
- 如果推荐失败，不保存 snapshot。
- 如果 snapshot 保存失败：
  - 推荐结果仍可返回。
  - 增加 `warnings=["recommendation_snapshot_save_failed"]`。
  - 不伪造 `recommendation_id`。
- 该保存动作只服务前端刷新恢复和候选路径手选，不表示推荐结果已经进入长期学习状态。

#### `GET /api/recommendations`

Query：

```text
user_id=126&syllabus_id=29&limit=20
```

输出：

```json
{
  "success": true,
  "snapshots": [],
  "error_code": "",
  "error_message": ""
}
```

#### `GET /api/recommendations/<recommendation_id>`

输出：

```json
{
  "success": true,
  "snapshot": {
    "recommendation_id": "recommendation_...",
    "recommendation": {
      "graph": {},
      "candidates": [],
      "selected": [],
      "best_path": {}
    }
  },
  "error_code": "",
  "error_message": ""
}
```

### 4. 测试用例的构建描述

扩展 `tests/test_personal_recommendation_api.py`：

```text
test_personal_recommendation_api_returns_recommendation_id
test_personal_recommendation_api_can_disable_snapshot
test_recommendation_snapshot_list_api_returns_summary
test_recommendation_snapshot_detail_api_returns_graph
```

测试构造：

- 使用 `create_app()` 和测试 client。
- 构造最小 syllabus JSON。
- 调用 `POST /api/personal_recommendation`。
- 断言响应中有 `recommendation_id`。
- 再调用 `GET /api/recommendations/<id>`，断言完整图可读。

## 阶段 3：通过 Recommendation Snapshot 手选路径并创建 Learning Plan

### 0. 新增常量定义

建议复用阶段 1 常量，并新增错误码常量：

```python
RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND = "recommendation_snapshot_not_found"
RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE = "invalid_candidate"
```

### 1. 影响的文件范围

修改：

- `tasks/personal_recommendation/snapshot.py`
  - 新增 `accept_recommendation_snapshot_path`。
- `tasks/personal_recommendation_task.py`
  - 导出新函数。
- `blueprint/learning_api.py`
  - 新增 `POST /api/recommendations/<recommendation_id>/accept`。
- `tests/test_personal_recommendation_snapshot.py`
  - 覆盖 task 级采纳。
- `tests/test_personal_recommendation_api.py`
  - 覆盖 API 级采纳。

可选修改：

- `schemas/agent_runtime_state.py`
  - `RecommendationSnapshot.accepted_plan_id` 可声明外键到 `learning_plan.plan_id`。

### 2. 函数级收口的完整数据流

```text
POST /api/recommendations/<recommendation_id>/accept
  -> accept_recommendation_snapshot_path(user_id, syllabus_id, recommendation_id, candidate_index)
     -> get_recommendation_snapshot(recommendation_id)
     -> validate ownership user_id / syllabus_id
     -> recover recommendation_result
     -> accept_recommendation_path(user_id, syllabus_id, recommendation_result, candidate_index)
     -> update snapshot status accepted
     -> save accepted_plan_id / accepted_candidate_index
  -> return learning plan result + snapshot status
```

### 3. 精确到输入输出的函数级收口

#### `accept_recommendation_snapshot_path(...) -> dict`

输入：

```python
accept_recommendation_snapshot_path(
    user_id: int,
    syllabus_id: int | None,
    recommendation_id: str,
    candidate_index: int | None = None,
) -> dict
```

输出：

```json
{
  "success": true,
  "recommendation_id": "recommendation_...",
  "snapshot_status": "accepted",
  "accepted_candidate_index": 1,
  "accepted_plan_id": "plan_...",
  "plan_id": "plan_...",
  "plan": {},
  "steps": [],
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 读取 snapshot。
- 校验 snapshot 的 `user_id` 与请求 `user_id` 一致。
- 如果请求传入 `syllabus_id`，也必须与 snapshot 一致。
- 从 snapshot 恢复：
  - `recommendation_result.graph`
  - `recommendation_result.candidates`
  - `recommendation_result.best_path`
- 调用现有 `accept_recommendation_path`，不复制 learning plan 创建逻辑。
- 成功后更新 snapshot：
  - `status = accepted`
  - `accepted_plan_id = result.plan_id`
  - `accepted_candidate_index = candidate_index`
  - `updated_at = now`

候选路径索引规则：

- `candidate_index` 采用后端现有零基索引。
- 前端展示可使用候选项中的 `rank`，但提交时应传零基 `candidate_index`。
- 如果未来要避免歧义，可扩展 `candidate_id`，但第一阶段不强制。

#### `POST /api/recommendations/<recommendation_id>/accept`

输入：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "candidate_index": 1
}
```

输出：

```json
{
  "success": true,
  "recommendation_id": "recommendation_...",
  "snapshot_status": "accepted",
  "accepted_plan_id": "plan_...",
  "plan": {},
  "steps": []
}
```

### 4. 测试用例的构建描述

Task 测试：

```text
test_accept_recommendation_snapshot_path_creates_learning_plan
test_accept_recommendation_snapshot_path_accepts_non_default_candidate
test_accept_recommendation_snapshot_path_marks_snapshot_accepted
test_accept_recommendation_snapshot_path_rejects_wrong_user
test_accept_recommendation_snapshot_path_rejects_invalid_candidate_index
test_accept_recommendation_path_keeps_direct_result_compatibility
```

API 测试：

```text
test_recommendation_snapshot_accept_api_creates_plan
test_recommendation_snapshot_accept_api_rejects_missing_user_id
test_recommendation_snapshot_accept_api_rejects_wrong_owner
```

核心断言：

- 手选第二条候选路径时，active plan steps 使用第二条候选路径。
- snapshot 状态变为 `accepted`。
- `learning_plan` 不包含完整 `graph`。
- `study_graph` 不因 accept snapshot 自动新增节点。

## 阶段 4：E2E 展示 artifact 和文档收口

### 0. 新增常量定义

不新增 Total Agent 常量。Recommendation Snapshot 是前端展示缓存，不作为 Total Agent 内部学习推进状态。

### 1. 影响的文件范围

按实际需要修改：

- `tests/total_agent/e2e_cases_large.py`
  - 可选：通过推荐 API 或显式 snapshot task 生成前端展示 artifact。
- `docs/personal_recommendation_dev_doc.md`
  - 融合本 contract 的最终事实。
- `docs/project_open_document/06_data_and_database_design.md`
  - 增加 recommendation snapshot 数据表说明。
- `tests/TEST_REPORT.md`
  - 更新回归命令和覆盖结果。

### 2. 函数级收口的完整数据流

API 演示主链路：

```text
frontend
  -> POST /api/personal_recommendation
  -> render graph/candidates from immediate response
  -> GET /api/recommendations/<recommendation_id> if page refresh or回放
  -> POST /api/recommendations/<recommendation_id>/accept
  -> active learning plan
  -> total agent continue current step
```

Total Agent 内部链路保持不依赖 snapshot：

```text
tool_run_learning_recommendation
  -> run_recommendation_route_from_payload
  -> result.recommendation
  -> wait user acceptance

tool_accept_learning_plan
  -> accept_recommendation_path(recommendation_result, candidate_index)
```

### 3. 精确到输入输出的函数级收口

#### Total Agent 推荐结果兼容

不要求 `tool_run_learning_recommendation` 返回 `recommendation_id`。如果某个演示链路确实需要在 Total Agent E2E artifact 中附带推荐大网，应由测试夹具或显式 snapshot task 在 artifact 层补充，不改变 Total Agent 工具语义。

#### E2E artifact

推荐 E2E artifact 结构：

```json
{
  "recommendation": {},
  "recommendation_snapshot": {
    "recommendation_id": "...",
    "summary": {},
    "snapshot": {}
  },
  "learning_plan": {},
  "study_graph": {}
}
```

### 4. 测试用例的构建描述

E2E 或集成测试：

```text
test_recommendation_snapshot_does_not_mutate_study_graph
test_frontend_recommendation_flow_accepts_selected_candidate
```

回归命令：

```bash
python -m pytest -q tests/test_personal_recommendation_snapshot.py tests/test_personal_recommendation_api.py tests/test_personal_recommendation_learning_plan.py tests/test_agent_runtime_db_persistence.py -rs
```

如果涉及 Total Agent：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

## 最终验收标准

- 前端可从 `POST /api/personal_recommendation` 直接拿到 `recommendation_id`。
- 前端可用 `GET /api/recommendations/<recommendation_id>` 在刷新后恢复完整推荐大网。
- 前端可用 `POST /api/recommendations/<recommendation_id>/accept` 手选候选路径并创建 active learning plan。
- `learning_plan` 仍只保存已选路径和 step。
- `study_graph` 不因推荐快照生成或采纳而直接写入推荐节点。
- 推荐算法核心函数保持纯计算，无数据库副作用。
- 生产环境默认 SQL，测试/离线 artifact 必须显式启用 file backend。
- 实现完成并同步 `personal_recommendation_dev_doc.md` 后，可删除本文和 small plan。
