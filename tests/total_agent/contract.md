# 总 Agent 前置闭环 contract

本文档定义总 Agent 实现前的跨模块测试契约。当前范围限定在 `tests/total_agent/`，用于验证后续总 Agent 需要依赖的学习过程闭环。

学习过程闭环在当前阶段只作为 `tests/total_agent/` 下的测试 helper 存在，用来验证总 Agent 未来需要调度的几个关键动作是否已经能通过现有 task 门户稳定衔接。

## 模块边界

```text
learning_profile_task
  -> 维护画像和个人大纲

study_graph_task
  -> 维护学习事实和进度树

personal_recommendation_task
  -> 生成推荐路径
  -> 持久化被采纳 learning_plan manifest

generative_task
  -> 根据当前节点/目标生成学习资源

tests/total_agent/test_process_contract.py
  -> 验证推荐结果、learning_plan、学习事件和下一任务之间的契约

tests/total_agent/test_total_agent_e2e.py
  -> opt-in 验证真实 LLM/RAG/DB/资源生成/学习图谱的全链路
```

当前测试契约只允许调用 task 门户或测试 helper，不把这些 helper 提升为生产业务模块。

## 0. 常量定义

测试契约常量：

```python
PROCESS_CONTRACT_SCHEMA_VERSION = "total_agent_process_contract.v1"
LEARNING_EVENT_RECORDED = "learning_event_recorded"
```

后续总 Agent 常量只作为未来预期，不在本阶段落代码：

```python
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"
```

## 1. 测试层流程契约

### `_accept_recommendation(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "candidate_index": 0,
  "recommendation_result": {
    "success": true,
    "best_path": {
      "path": ["n1", "n2"],
      "skills": ["a", "b"]
    },
    "graph": {
      "nodes": [
        {"id": "n1", "title": "基础", "outcomes": ["a"]},
        {"id": "n2", "title": "进阶", "outcomes": ["b"]}
      ],
      "edges": []
    }
  }
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent_process_contract.v1",
  "plan": {
    "plan_id": "plan_xxx",
    "status": "active",
    "steps": [
      {"step_id": "step_1", "node_id": "n1", "status": "active"},
      {"step_id": "step_2", "node_id": "n2", "status": "pending"}
    ]
  },
  "accept_result": {"success": true, "plan_id": "plan_xxx"},
  "next_task": {"step_id": "step_1", "node_id": "n1", "status": "active"},
  "metrics": {"total_steps": 2, "completed_steps": 0, "progress_ratio": 0.0},
  "error_code": "",
  "error_message": ""
}
```

规则：

- 只调用 `personal_recommendation_task.accept_recommendation_path`。
- 不直接写 `study_graph`。
- 不调用资源生成。
- 不作为生产 task 暴露。

### `_record_event(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "plan_id": "plan_xxx",
  "step_id": "step_1",
  "event_type": "resource_completed",
  "resource_type": "quiz",
  "resource_id": "res_1",
  "score": 0.9,
  "status": "completed"
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent_process_contract.v1",
  "updated_step": {"step_id": "step_1", "status": "completed"},
  "activated_step": {"step_id": "step_2", "status": "active"},
  "next_task": {"step_id": "step_2", "status": "active"},
  "metrics": {"completed_steps": 1, "progress_ratio": 0.5},
  "event_entry": {"event_type": "learning_event_recorded"},
  "error_code": "",
  "error_message": ""
}
```

规则：

- 先追加 `learning_event_recorded` manifest entry。
- 再更新 step 状态。
- 当前 step 完成或跳过后，激活下一个 pending step。
- 测试中不触发 `study_graph` 同步。

### `_get_next_task(user_id: int, syllabus_id: int | None = None) -> dict`

输出：

```json
{
  "success": true,
  "schema_version": "total_agent_process_contract.v1",
  "plan": {"plan_id": "plan_xxx", "status": "active"},
  "next_task": {"step_id": "step_2", "node_id": "n2", "status": "active"},
  "metrics": {"remaining_steps": 1},
  "error_code": "",
  "error_message": ""
}
```

规则：

- 优先返回 active step。
- 没有 active step 时返回第一个 pending step。
- 没有 active plan 时返回 `no_active_plan`。

### `_recommend_and_accept(payload: dict) -> dict`

输入：

```json
{
  "user_id": 12345,
  "syllabus_id": 20,
  "goals": ["ml_basic"],
  "K": 10,
  "beam_width": 8
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent_process_contract.v1",
  "recommendation": {"success": true, "best_path": {}},
  "accept_result": {"success": true, "plan_id": "plan_xxx"},
  "plan": {"status": "active"},
  "next_task": {"status": "active"},
  "metrics": {"total_steps": 2}
}
```

规则：

- 调用真实 `personal_recommendation_task.run_recommendation_route_from_payload`。
- RAG/LLM 不在默认测试中打开。
- 推荐结果只通过 `accept_recommendation_path` 转成 learning plan。
- 该测试 helper 表示测试/演示用自动采纳，不代表正式总 Agent 默认替学生采纳推荐路径。
- 正式总 Agent 中，推荐成功后应先返回候选和解释，并以 `wait_user_acceptance` 作为下一动作；只有用户确认或显式 `auto_accept=true` 时才进入采纳。

### `_run_total_agent_contract_turn(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "继续学习",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "res_xxx"
  }
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent.v1",
  "intent": "generate_current_step_resource",
  "tool_trace": [
    "load_total_context",
    "get_next_learning_task",
    "generate_learning_resources"
  ],
  "result": {
    "next_task": {},
    "resources": []
  },
  "suggested_next_action": "record_learning_feedback",
  "error_code": "",
  "error_message": ""
}
```

规则：

- 这是测试侧 deterministic turn router，不是总 Agent runtime。
- 根据自然语言 `message` 识别 `recommend_learning_path`、`generate_current_step_resource`、`record_learning_feedback`、`skip_current_step`。
- 连续多轮复用同一个 learning plan manifest，验证上下文继承。
- 每轮都必须返回 `intent`、`tool_trace`、`suggested_next_action`。
- 资源生成使用测试 stub，默认测试不调用真实 `generative_task`。

## 2. 后续总 Agent 预期行为

以下只作为未来总 Agent 的目标行为，不在本阶段实现：

### `run_total_agent(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "我想继续学习 HBase RowKey",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "res_xxx"
  }
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent.v1",
  "intent": "generate_current_step_resource",
  "tool_trace": [
    "load_total_context",
    "get_next_learning_task",
    "generate_learning_resources"
  ],
  "result": {
    "next_task": {},
    "resources": []
  },
  "suggested_next_action": "record_learning_feedback",
  "error_code": "",
  "error_message": ""
}
```

未来规则：

- 只调用 task 门户，不直接依赖各包内 service。
- 默认不一次性生成全套资源。
- 资源生成以当前 step 和用户意图为准。
- 推荐路径采纳必须需要用户确认；测试或演示可显式使用 deterministic `auto_accept=true`。
- `accept_learning_plan` 的输入必须包含已有 `recommendation_result` 和 `candidate_index` 或 `best_path`，不能由该工具自行重选路径。
- 所有失败返回结构化错误。

## 3. 集成边界

当前阶段只验证测试侧流程契约，不提供运行时路由。后续是否暴露路由由总 Agent 实现阶段统一决定。

## 4. 测试契约

默认 CI：

```bash
python -m pytest -q tests/total_agent/test_process_contract.py
```

默认测试目标：

```text
fixed recommendation_result fixture
  -> accept learning_plan
  -> record first step completed
  -> get next task

run_recommendation_route_from_payload
  -> accept learning_plan
  -> record first step completed
  -> get next task

multi-turn deterministic router
  -> "帮我推荐一条学习路径"
      -> recommend_learning_path
      -> suggested_next_action=generate_current_step_resource
  -> "继续学习"
      -> generate_current_step_resource
      -> suggested_next_action=record_learning_feedback
  -> "我完成了当前资源"
      -> record_learning_feedback
      -> activate next step
  -> "跳过当前步骤"
      -> skip_current_step
      -> activate next step

forced continue fallback
  -> recommendation produced no best_path
  -> active learning_plan exists
  -> get next task from existing plan
  -> generate current step resource
  -> suggested_next_action=record_learning_feedback
```

大型 opt-in 目标只作为未来测试方向：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql"
```

大型 opt-in 推荐段采用两步数据流：

```text
natural language goals
  -> personal_recommendation_agent + real RAG
  -> if best_path exists: continue
  -> if no candidate path:
      score syllabus graph nodes by semantic overlap with user goal tokens and RAG evidence
      if aligned node exists:
        retry personal_recommendation_agent with aligned node outcomes
      else:
        stop with terminal_state=ask_goal_clarification
        write goal_alignment_failed artifact
  -> accept learning_plan
```

这一步不是吞掉推荐失败，而是把自然语言目标匹配失败写入 artifact，同时模拟后续总 Agent 会承担的目标归一化职责。

总 Agent 设计原则：

- 子 Agent 推荐结果没有 `best_path` 时，不能直接进入资源生成。
- 目标归一化必须有语义证据：用户目标 token、syllabus 节点标题/outcomes、RAG evidence 至少有明确重合。
- 如果只有任意 fallback 节点，应该追问用户，而不是生成偏题资源。
- 允许一个很窄的强行推进特例：推荐失败但已有 active plan / next_task 时，可以继续执行当前 plan；这不是重写推荐结果，也不是选择任意 syllabus 节点。
- E2E 中的 deterministic fallback 是未来总 Agent 调度策略原型，不是子 Agent mock。
- Large E2E 有两个合法终态：生成当前 step 资源，或在目标无法语义对齐时返回 `ask_goal_clarification`。

大型 opt-in 另有一条必然走深的 aligned graph 验收链路：

```text
aligned HBase recommendation graph fixture
  -> personal_recommendation_agent + real RAG
  -> accept learning_plan
  -> generate current step document
  -> record learning feedback
  -> study_graph resource-event sync
```

这条链路用于验证“目标已经对齐时”能走到资源生成和学习图谱更新。它不替代真实 syllabus 验证；如果真实 syllabus 链路停在 `ask_goal_clarification`，需要检查 syllabus adapter 是否覆盖当前课程 JSON 结构。

默认测试不依赖真实 LLM、真实 RAG 或真实 MySQL。
