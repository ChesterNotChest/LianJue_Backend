# 总 Agent 前置闭环 small plan

> 本计划只覆盖总 Agent 实现前的测试契约。学习过程闭环先放在 `tests/total_agent/`，用于验证推荐、learning plan、学习事件和下一任务之间的衔接。
>
> 正式总 Agent 的运行时设计计划见 `docs/teacher_agent_small_plan.md`。本文档只描述测试侧契约，不新增生产 task、API 或业务模块。

## 目标

在正式实现总 Agent 前，先把它未来必须依赖的跨模块闭环验证清楚：

```text
recommendation result
  -> accept learning_plan
  -> record learning event
  -> update step status
  -> get next task
```

这不是业务模块，也不是前端 API。它是测试侧契约，用来降低后续总 Agent 调度多个 task 门户时的不确定性。

## 阶段 1：测试侧 deterministic learning process contract

### 0. 新增的常量定义

仅在测试文件中定义：

```python
PROCESS_CONTRACT_SCHEMA_VERSION = "total_agent_process_contract.v1"
LEARNING_EVENT_RECORDED = "learning_event_recorded"
```

### 1. 影响的文件范围

```text
tests/total_agent/contract.md
tests/total_agent/small_plan.md
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
tests/artifacts/total_agent/process_contract/
tests/artifacts/total_agent/e2e/
```

当前阶段的代码范围只在测试目录，不提升为运行时业务模块。

### 2. 函数级收口的完整数据流

```text
fixed recommendation_result fixture
  -> _accept_recommendation
      -> personal_recommendation_task.accept_recommendation_path
      -> get active learning_plan
      -> get next task
  -> _record_event
      -> append learning_event_recorded manifest entry
      -> update current step status
      -> activate next pending step
      -> get next task
  -> _get_next_task
      -> read active learning_plan
      -> return active/pending step
  -> write test artifact
```

### 3. 精确到输入输出的函数级收口

`_accept_recommendation(payload: dict) -> dict`

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
  "accept_result": {"success": true, "plan_id": "plan_xxx"},
  "plan": {"plan_id": "plan_xxx", "status": "active", "steps": []},
  "next_task": {"step_id": "step_1", "status": "active"},
  "metrics": {"total_steps": 2, "completed_steps": 0, "progress_ratio": 0.0},
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 只通过 `personal_recommendation_task.accept_recommendation_path` 创建 plan。
- 不直接调用 `study_graph_task`。
- 不生成资源。
- 返回当前 active plan、下一任务和轻量 metrics。

`_record_event(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "plan_id": "plan_xxx",
  "step_id": "step_1",
  "event_type": "resource_completed",
  "resource_id": "res_1",
  "status": "completed",
  "score": 0.9
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

内部逻辑：

- 先写学习事件 manifest entry，保留用户行为事实。
- 再更新 step 状态。
- 当前 step 完成或跳过后，激活下一个 pending step。
- 测试阶段不把事件同步到 `study_graph`。

`_get_next_task(user_id: int, syllabus_id: int | None = None) -> dict`

输出：

```json
{
  "success": true,
  "schema_version": "total_agent_process_contract.v1",
  "plan": {"status": "active"},
  "next_task": {"status": "active"},
  "metrics": {"remaining_steps": 1},
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 读取 active learning plan。
- 优先返回 active step。
- 没有 active step 时返回第一个 pending step。
- 没有 active plan 时返回 `no_active_plan`。

### 4. 测试用例的构建描述

- 固定 recommendation fixture 可以创建 active learning plan。
- 创建 plan 后第一步为 active，后续 step 为 pending。
- 记录 completed 事件后，当前 step 变 completed，下一步变 active。
- `_get_next_task` 能返回当前下一任务。
- 没有 active plan 时返回结构化 `no_active_plan`。
- 测试输出 artifact，便于人工检查 manifest 和闭环结果。

## 阶段 2：接入真实 recommendation task 的中型契约

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tests/total_agent/test_process_contract.py
tests/artifacts/total_agent/process_contract/recommendation_contract_closure/
```

### 2. 函数级收口的完整数据流

```text
run_recommendation_route_from_payload
  -> recommendation result
  -> _accept_recommendation
  -> _record_event
  -> _get_next_task
  -> write recommendation contract artifact
```

### 3. 精确到输入输出的函数级收口

`_recommend_and_accept(payload: dict) -> dict`

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
  "accept_result": {"success": true},
  "plan": {"status": "active"},
  "next_task": {"status": "active"},
  "metrics": {"total_steps": 2}
}
```

内部逻辑：

- 调用真实 `personal_recommendation_task.run_recommendation_route_from_payload`。
- 使用 deterministic/sample 路径，不打开真实 LLM/RAG。
- 推荐输出不被测试 helper 重写，只通过采纳入口转为 learning plan。
- 本 helper 等价于测试/演示场景的 `auto_accept=true`，不代表正式总 Agent 可以在推荐成功后替学生默认采纳。

### 4. 测试用例的构建描述

- 真实 recommendation task 的 `best_path` 可以被 learning plan 接收。
- 采纳结果包含 active plan 和 steps。
- step 完成后下一任务正确推进。
- artifact 保存 recommendation、accept result、event result 和 next task。
- artifact 应保留 auto accept 语义，方便后续区分“推荐结果”与“学生确认后的计划执行”。

## 阶段 2.5：测试侧多轮总 Agent 行为契约

### 0. 新增的常量定义

测试文件中复用：

```python
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"
```

### 1. 影响的文件范围

```text
tests/total_agent/test_process_contract.py
tests/artifacts/total_agent/process_contract/multi_turn_intent_context/
```

### 2. 函数级收口的完整数据流

```text
message: 帮我推荐一条学习路径
  -> infer intent: recommend_learning_path
  -> accept recommendation fixture
  -> suggested_next_action: generate_current_step_resource

message: 继续学习
  -> inherit active_plan_id
  -> get next task
  -> generate stub resource
  -> suggested_next_action: record_learning_feedback

message: 我完成了当前资源
  -> inherit active_plan_id/current_resource_id
  -> record completed event
  -> activate next step
  -> suggested_next_action: generate_current_step_resource

message: 跳过当前步骤
  -> inherit active_plan_id
  -> record skipped event
  -> activate next step
```

### 3. 精确到输入输出的函数级收口

`_run_total_agent_contract_turn(payload: dict) -> dict`

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
  "tool_trace": ["load_total_context", "get_next_learning_task", "generate_learning_resources"],
  "result": {"next_task": {}, "resources": []},
  "suggested_next_action": "record_learning_feedback",
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 只做测试侧 deterministic intent router。
- 不调用真实 LLM，不调用真实资源生成。
- 通过同一个 learning plan manifest 验证多轮状态继承。
- 断言 `suggested_next_action` 随 intent 和 step 状态变化。

### 4. 测试用例的构建描述

- 推荐消息会进入推荐/采纳链路。
- 继续学习消息会复用 active plan 并生成当前 step 的 stub resource。
- 完成消息会记录 completed event 并推进到下一 step。
- 跳过消息会记录 skipped event 并推进到下一 step。
- artifact 保存每一轮 turn output 和最终 manifest。
- 推荐链路无 `best_path` 但已有 active plan 时，可以继续当前 step 并生成 stub resource；该分支只验证“继续执行已有计划”，不允许选择任意 syllabus 节点。

## 阶段 3：后续总 Agent 与大型 opt-in E2E

### 0. 新增的常量定义

后续总 Agent 实现时再新增：

```python
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"
```

### 1. 影响的文件范围

当前作为 opt-in 测试范围：

```text
tests/total_agent/test_total_agent_e2e.py
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

目标：

```text
MySQL user/syllabus
  -> learning_profile
  -> personal_recommendation + real RAG with natural language goals
  -> if no best_path, score syllabus graph nodes by user goal tokens + RAG evidence
  -> if aligned node exists, retry personal_recommendation with aligned outcomes
  -> if no aligned node, return ask_goal_clarification and write goal_alignment_failed artifact
  -> accept learning_plan
  -> get next task
  -> generative current step resource
  -> record learning feedback
  -> study_graph resource-event sync
  -> artifact
```

### 3. 精确到输入输出的函数级收口

`test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db(...)` 产物摘要：

```json
{
  "schema_version": "total_agent_process_contract.v1",
  "summary": {
    "best_path": ["n1", "n2"],
    "accepted_step_count": 2,
    "generated_resource_type": "documents",
    "study_graph_created_nodes": []
  }
}
```

内部逻辑：

- 使用真实 MySQL 测试用户和课程。
- 调用 `learning_profile_task.get_or_build_learning_profile`。
- 调用 `personal_recommendation_task.run_personal_recommendation_agent`，检索图由环境变量指定，默认 `RAG`。
- 首次使用自然语言目标，若推荐图没有 `best_path`，从当前推荐图节点、用户目标 token 和 RAG evidence 中计算语义相关目标。
- 只有存在明确语义重合的节点时才用该节点 outcomes 重试；否则写出 `goal_alignment_failed` artifact，并以 `ask_goal_clarification` 作为合法终态，不继续生成资源。
- 采纳推荐路径并获取当前 step。
- 只围绕当前 step 调用 `generative_task.generate_resources_from_request` 生成 `documents`。
- 记录学习事件并调用 `study_graph_task` 根据资源事件更新学习图谱。
- 写出完整 artifact，便于人工检查。

### 4. 测试用例的构建描述

large opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" -rs
```

目标链路：

```text
MySQL user/syllabus
  -> learning_profile
  -> personal_recommendation + optional real RAG
  -> learning_plan
  -> next_task
  -> optional generative_task
```

该阶段不进入默认 CI。未设置环境变量时应跳过，不应访问真实 LLM/RAG/DB。

large opt-in 包含两类场景：

```text
goal clarification scenario
  -> 使用真实 syllabus
  -> 若自然语言目标无法和推荐图语义对齐
  -> 返回 ask_goal_clarification

deep success scenario
  -> 使用 HBase aligned recommendation graph fixture
  -> 保证推荐 path 可达
  -> 继续验证 resource generation + study_graph sync
```

当前真实大数据 syllabus fixture 是 `period` 结构；如果推荐图退回 sample tree，说明 syllabus adapter 还没有覆盖该结构。后续 adapter 应把 `period` 映射为语义主题节点，并把 `week_index` 保留为元数据；不应该把 `week_x` 当作主学习节点，也不应该用任意 fallback 节点绕过。

总 Agent 设计思路：

```text
recommendation.best_path is None
  -> classify as recoverable planning gap
  -> attempt deterministic goal normalization from graph/RAG evidence
  -> retry only when there is semantic evidence
  -> otherwise ask user to clarify goal
```

这个策略的目的不是让测试强行通过，而是提前约束总 Agent：不能因为推荐链路失败就退到任意 syllabus 节点并生成偏题资源。
