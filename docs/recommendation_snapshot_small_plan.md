# Recommendation Snapshot small plan

本文档用于收口“推荐大网快照”的增量设计。目标是让前端能够展示完整推荐网络，并支持用户在多个候选路径中手选一条路径，同时不把推荐快照变成后续 Agent 闭环的强依赖。

## 1. 背景判断

当前系统已经持久化两类推荐相关结果：

- `learning_plan`：用户采纳后的已选路径和 step 执行状态。
- `study_graph`：学生真实触达、学习、练习或反馈后的个人成长树。

但完整推荐结果目前主要停留在一次 `run_recommendation_route` 返回值中，包括：

- `graph.nodes`
- `graph.edges`
- `candidates`
- `selected`
- `best_path`
- `rag_overlay`
- `planning_hints`

这导致前端无法稳定展示“推荐大网”，也无法在推荐结果生成后让用户回到同一张推荐图里手动选择某条候选路径。`learning_plan` 只能表示已采纳路径，不能还原完整候选网络。

## 2. 目标

新增 Recommendation Snapshot，作为推荐结果的展示、回放、候选路径选择和调试快照。

目标能力：

- 推荐生成后保存完整推荐快照。
- 前端可按 `recommendation_id` 读取完整推荐图。
- 前端可列出某个用户/大纲最近的推荐快照。
- 用户可通过 `recommendation_id + candidate_index` 采纳候选路径。
- 采纳后仍然生成现有 `learning_plan`，不改变学习计划语义。
- 后续 Total Agent 学习推进默认不读取推荐快照，只读取 active plan、profile、study graph 和 resource metadata。

非目标：

- 不把推荐快照作为长期学习状态。
- 不把推荐图写入 study graph。
- 不让资源生成依赖完整推荐图。
- 不要求 Agent 二次读取推荐快照才能继续学习。

## 3. 数据模型建议

新增表：`recommendation_snapshot`

建议字段：

```text
recommendation_id        string primary key
user_id                  int, indexed
syllabus_id              int nullable, indexed
session_id               string nullable, indexed
status                   string, proposed | accepted | superseded | expired
schema_version           string
goal_json                text
query_text               text nullable
graph_json               long text
candidates_json          long text
selected_json            long text
best_path_json           long text
rag_overlay_json         long text nullable
planning_hints_json      text nullable
result_summary_json      text nullable
accepted_plan_id         string nullable
accepted_candidate_index int nullable
created_at               int
updated_at               int
expires_at               int nullable
```

推荐约束：

- `recommendation_id` 由后端生成，例如 `recommendation_YYYYMMDDHHMMSS_xxxxxx`。
- `user_id + syllabus_id + created_at` 建索引，支持前端读取最近推荐。
- `accepted_plan_id` 可关联 `learning_plan.plan_id`，但不要求旧数据全量回填。
- 大字段保留 JSON 文本，避免为展示图过早拆成多张表。

## 4. Task 层接口

建议放在 `tasks/personal_recommendation/snapshot.py`，并通过 `tasks/personal_recommendation_task.py` 对外导出。

新增函数：

```python
save_recommendation_snapshot(
    user_id: int,
    syllabus_id: int | None,
    recommendation_result: dict,
    *,
    request_payload: dict | None = None,
    session_id: str | None = None,
    status: str = "proposed",
) -> dict
```

返回：

```json
{
  "success": true,
  "recommendation_id": "recommendation_20260610191033_d27634",
  "status": "proposed"
}
```

新增读取：

```python
get_recommendation_snapshot(recommendation_id: str) -> dict
list_recommendation_snapshots(user_id: int, syllabus_id: int | None = None, limit: int = 20) -> dict
```

新增采纳：

```python
accept_recommendation_snapshot_path(
    user_id: int,
    syllabus_id: int | None,
    recommendation_id: str,
    candidate_index: int | None = None,
) -> dict
```

内部逻辑：

```text
get snapshot
  -> recover recommendation_result
  -> accept_recommendation_path(user_id, syllabus_id, recommendation_result, candidate_index)
  -> mark snapshot accepted
  -> save accepted_plan_id / accepted_candidate_index
```

## 5. 推荐生成接入点

推荐主入口：

```text
run_recommendation_route_from_payload(payload)
  -> run_recommendation_route(...)
  -> save_recommendation_snapshot(...)
  -> return recommendation_result with recommendation_id
```

建议默认保存条件：

- `success == True`
- `graph.nodes` 非空
- `payload.persist_snapshot` 没有显式设为 `False`

返回中追加：

```json
{
  "recommendation_id": "recommendation_...",
  "snapshot_status": "proposed"
}
```

测试或离线 artifact 可通过显式文件后端保留 JSON 快照；生产环境默认依赖 SQL。

## 6. Learning Plan 接入点

现有入口保留：

```python
accept_recommendation_path(user_id, syllabus_id, recommendation_result, candidate_index)
```

新增入口：

```python
accept_recommendation_snapshot_path(user_id, syllabus_id, recommendation_id, candidate_index)
```

前端推荐使用新入口。Total Agent 内部如果已经持有 `recommendation_result`，可以继续走旧入口，避免强制二次读取。

采纳后：

- 创建 active learning plan。
- supersede 旧 active plan。
- 标记 snapshot `accepted`。
- 记录 `accepted_plan_id` 和 `accepted_candidate_index`。

## 7. API 设计建议

新增或扩展 `learning_api`：

```text
POST /api/personal_recommendation
  生成推荐结果，并返回 recommendation_id。

GET /api/recommendations
  query: user_id, syllabus_id, limit
  返回推荐快照列表摘要。

GET /api/recommendations/<recommendation_id>
  返回完整推荐快照。

POST /api/recommendations/<recommendation_id>/accept
  body: {user_id, syllabus_id, candidate_index}
  按候选路径创建 learning plan。
```

列表接口只返回摘要：

```json
{
  "recommendation_id": "...",
  "status": "proposed",
  "candidate_count": 3,
  "best_path_titles": ["HBase 基础", "HBase RowKey 设计"],
  "created_at": 1781118633
}
```

详情接口返回完整：

```json
{
  "recommendation_id": "...",
  "status": "proposed",
  "recommendation": {
    "graph": {},
    "candidates": [],
    "selected": [],
    "best_path": {},
    "planning_hints": {}
  }
}
```

## 8. 前端使用方式

推荐页流程：

```text
用户输入学习目标
  -> POST /api/personal_recommendation
  -> 获取 recommendation_id + graph + candidates
  -> 渲染推荐大网
  -> 高亮 best_path
  -> 用户可切换 candidate
  -> POST /api/recommendations/<id>/accept
  -> 跳转学习计划 / 当前 step / 资源生成入口
```

展示原则：

- 推荐大网展示的是“建议网络”，不是学生成长树。
- 已选路径展示的是候选路径之一，采纳后才变成 learning plan。
- 学生成长树只展示真实学习状态，不提前铺满推荐图节点。

## 9. 测试计划

单元测试：

```text
test_recommendation_snapshot_saved_after_route
test_get_recommendation_snapshot_returns_full_graph
test_list_recommendation_snapshots_returns_summary_only
test_accept_recommendation_snapshot_path_creates_learning_plan
test_accept_recommendation_snapshot_path_records_accepted_status
test_accept_recommendation_path_keeps_direct_result_compatibility
```

API 测试：

```text
test_personal_recommendation_api_returns_recommendation_id
test_recommendation_snapshot_detail_api
test_recommendation_snapshot_accept_api
```

E2E 重点：

- 推荐图生成后有 `recommendation_id`。
- 推荐图可被前端读取和渲染。
- 用户手选非默认候选路径后，learning plan 使用该候选路径。
- study graph 不因推荐快照创建而新增节点。

## 10. 验收标准

- `run_recommendation_route_from_payload` 返回结果包含 `recommendation_id`。
- SQL 中能读取完整 `graph/candidates/best_path`。
- 前端可以用 `recommendation_id + candidate_index` 创建学习计划。
- 学习计划仍只保存已选路径和 step，不保存完整推荐大网。
- Total Agent 后续学习推进不依赖推荐快照。
- dev doc 更新后，本文可被删除。
