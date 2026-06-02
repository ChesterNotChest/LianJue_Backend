# Total Agent contract

本文档收口正式 `total_agent` 实现契约。`Total Agent` 是工程命名；产品或论文中可以称为 Teacher Agent，但代码、测试和 artifact 统一使用 `total_agent`。

边界：

- `docs/total_agent_small_plan.md` 说明背景、阶段和优先级。
- `docs/total_agent_contract.md` 固定实现契约。
- `tests/total_agent/contract.md` 是测试侧前置闭环契约，不是生产 runtime。
- 正式 runtime 默认落在 `tasks/total_agent/`。
- `tasks/total_agent_task.py` 只作为可选薄门户，在 API/前端需要统一入口时新增。

## 阶段 1：建立 runtime、常量和结构化输出

### 0. 新增的常量定义

新增到 `tasks/total_agent/agent_contracts.py`：

```python
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"

INTENT_RECOMMEND_LEARNING_PATH = "recommend_learning_path"
INTENT_ACCEPT_RECOMMENDATION = "accept_recommendation"
INTENT_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
INTENT_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
INTENT_SKIP_CURRENT_STEP = "skip_current_step"
INTENT_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"

TOTAL_AGENT_INTENTS = {
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_SKIP_CURRENT_STEP,
    INTENT_ASK_GOAL_CLARIFICATION,
}

ACTION_WAIT_USER_ACCEPTANCE = "wait_user_acceptance"
ACTION_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
ACTION_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
ACTION_GET_NEXT_LEARNING_TASK = "get_next_learning_task"
ACTION_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
ACTION_RETRY_RECOMMENDATION = "retry_recommendation"
ACTION_CONTINUE_EXISTING_PLAN = "continue_existing_plan"

TOOL_LOAD_TOTAL_CONTEXT = "load_total_context"
TOOL_INFER_USER_INTENT = "infer_user_intent"
TOOL_RUN_LEARNING_RECOMMENDATION = "run_learning_recommendation"
TOOL_NORMALIZE_LEARNING_GOAL = "normalize_learning_goal_for_recommendation"
TOOL_ACCEPT_LEARNING_PLAN = "accept_learning_plan"
TOOL_GET_NEXT_LEARNING_TASK = "get_next_learning_task"
TOOL_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
TOOL_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
TOOL_SKIP_CURRENT_STEP = "skip_current_step"

TOTAL_AGENT_TOOL_ORDER = {
    INTENT_RECOMMEND_LEARNING_PATH: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_RUN_LEARNING_RECOMMENDATION,
    ],
    INTENT_ACCEPT_RECOMMENDATION: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_ACCEPT_LEARNING_PLAN,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
    INTENT_GENERATE_CURRENT_STEP_RESOURCE: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_GET_NEXT_LEARNING_TASK,
        TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    ],
    INTENT_RECORD_LEARNING_FEEDBACK: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_RECORD_LEARNING_FEEDBACK,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
    INTENT_SKIP_CURRENT_STEP: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_SKIP_CURRENT_STEP,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
}
```

### 1. 影响的文件范围

```text
tasks/total_agent/__init__.py
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tasks/total_agent_task.py                 # 可选薄门户
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
tests/TEST_REPORT.md
docs/total_agent_small_plan.md
docs/total_agent_contract.md
```

### 2. 函数级收口的完整数据流

```text
run_total_agent(payload)
  -> build TotalAgentState
  -> pydantic-ai TotalAgent
      -> load_total_context
      -> infer_user_intent
      -> route by intent
  -> execute intent-specific tool chain
  -> build TotalAgentResult
```

### 3. 精确到输入输出的函数级收口

`run_total_agent(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "我想继续学习 HBase RowKey",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "res_xxx"
  },
  "resource_types": ["documents"],
  "auto_accept": false
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
    "infer_user_intent",
    "get_next_learning_task",
    "generate_current_step_resource"
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

重要内部逻辑：

- LLM Agent 只负责意图识别、工具调度和解释，不直接编造推荐路径、学习计划、资源 manifest 或学习树变更。
- 工具实现只调用 task 门户，不直接依赖各包内 service。
- 所有失败返回结构化错误。
- `tool_trace` 必须真实来自工具调用，不由模型最终输出伪造。
- 默认不一次性生成全套资源。

### 4. 测试用例的构建描述

- `test_total_agent_routes_recommend_message`
- `test_total_agent_routes_continue_message_with_active_plan`
- `test_total_agent_routes_feedback_message`
- `test_total_agent_routes_skip_message`
- `test_total_agent_returns_structured_error_for_missing_user_id`
- `test_total_agent_agent_choice_real_llm_optional`

默认测试不访问真实 LLM/RAG/DB。

## 阶段 2：上下文读取与状态继承

### 0. 新增的常量定义

不新增全局常量，复用阶段 1 工具名。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tasks/study_graph_task.py
tests/test_total_agent_task.py
tests/total_agent/test_process_contract.py
```

### 2. 函数级收口的完整数据流

```text
load_total_context(payload)
  -> validate user_id / syllabus_id
  -> read active learning_plan
  -> derive next_task from learning_plan
  -> read current_resource_id / recent resources from payload.context
  -> read optional study_graph_state summary
  -> store total_context in state
```

### 3. 精确到输入输出的函数级收口

`load_total_context(state: dict) -> dict`

输入来自 `state["payload"]`：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "继续学习",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "documents-xxx"
  }
}
```

输出：

```json
{
  "tool": "load_total_context",
  "success": true,
  "user_id": 8,
  "syllabus_id": 20,
  "active_plan": {
    "plan_id": "plan_xxx",
    "status": "active"
  },
  "next_task": {
    "step_id": "step_xxx",
    "node_id": "rowkey_design",
    "title": "HBase RowKey 设计",
    "status": "active"
  },
  "current_resource_id": "documents-xxx",
  "study_graph_state": {
    "current_node_id": "",
    "completed_node_ids": [],
    "weak_node_ids": [],
    "blocked_node_ids": []
  },
  "error_code": "",
  "error_message": ""
}
```

重要内部逻辑：

- active plan 优先来自 `context.active_plan_id`，否则读取当前 active plan。
- `next_task` 只来自 learning plan，不从 syllabus 任意推断。
- 没有 active plan 时返回空上下文，不抛异常。
- `study_graph_state` 只作为只读摘要，不在该工具中提交变更。

### 4. 测试用例的构建描述

- 有 active plan 时能读出 active step。
- 完成反馈后下一次调用能继承新 active step。
- 没有 active plan 时返回空上下文并允许后续进入推荐或追问。
- `context.active_plan_id` 优先于默认 active plan。

## 阶段 3：意图识别和动态路由

### 0. 新增的常量定义

复用 `TOTAL_AGENT_INTENTS`，不新增。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py
tests/total_agent/test_process_contract.py
```

### 2. 函数级收口的完整数据流

```text
message + total_context
  -> infer_user_intent
  -> intent + confidence + required_context
  -> runtime selects next tools
```

### 3. 精确到输入输出的函数级收口

`infer_user_intent(state: dict) -> dict`

输入：

```json
{
  "message": "我完成了刚才的文档",
  "total_context": {
    "active_plan": {},
    "next_task": {},
    "current_resource_id": "documents-xxx"
  }
}
```

输出：

```json
{
  "tool": "infer_user_intent",
  "success": true,
  "intent": "record_learning_feedback",
  "confidence": 0.86,
  "reason": "message reports current resource completion",
  "required_context": ["active_plan", "current_resource_id"]
}
```

重要内部逻辑：

- “推荐 / 学什么 / 下一步路径”进入 `recommend_learning_path`。
- “继续 / 开始 / 给我资料”进入 `generate_current_step_resource`，但必须有 active plan 或能进入推荐链路。
- “完成 / 做完 / 看完 / 得分”进入 `record_learning_feedback`。
- “跳过 / 太简单 / 换一个”进入 `skip_current_step`。
- 缺少明确目标或置信度低时进入 `ask_goal_clarification`。
- 已有 active plan 且用户说“继续”，优先 history-driven，不重新推荐。

### 4. 测试用例的构建描述

- 推荐、继续、完成、跳过、模糊目标五类 deterministic intent 测试。
- 多轮调用继承同一 active plan。
- LLM opt-in 只验证工具选择和结构化结果，不评价资源内容质量。

## 阶段 4：推荐、目标归一化和采纳确认

### 0. 新增的常量定义

```python
RECOVERY_RETRY_RECOMMENDATION = "retry_recommendation"
RECOVERY_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
RECOVERY_CONTINUE_EXISTING_PLAN = "continue_existing_plan"

RECOMMENDATION_RECOVERY_ACTIONS = {
    RECOVERY_RETRY_RECOMMENDATION,
    RECOVERY_ASK_GOAL_CLARIFICATION,
    RECOVERY_CONTINUE_EXISTING_PLAN,
}
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tests/test_total_agent_task.py
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
```

### 2. 函数级收口的完整数据流

```text
recommend_learning_path
  -> run_learning_recommendation
      -> personal_recommendation_task.run_recommendation_route_from_payload
  -> if best_path exists:
      -> return candidates
      -> suggested_next_action=wait_user_acceptance
  -> if no best_path:
      -> normalize_learning_goal_for_recommendation
      -> retry only when semantic evidence exists
      -> otherwise ask_goal_clarification

accept_recommendation
  -> require explicit confirmation or auto_accept=true
  -> accept_learning_plan
  -> get_next_learning_task
```

### 3. 精确到输入输出的函数级收口

`run_learning_recommendation(state: dict) -> dict`

输出：

```json
{
  "tool": "run_learning_recommendation",
  "success": true,
  "recommendation": {
    "success": true,
    "best_path": {},
    "candidates": []
  },
  "has_best_path": true,
  "suggested_next_action": "wait_user_acceptance",
  "error_code": "",
  "error_message": ""
}
```

`normalize_learning_goal_for_recommendation(state: dict) -> dict`

输入：

```json
{
  "message": "我想学 RowKey 热点规避",
  "goals": ["RowKey 热点规避"],
  "recommendation_result": {
    "success": true,
    "best_path": null,
    "graph": {"nodes": []},
    "rag_overlay": {}
  }
}
```

输出：

```json
{
  "tool": "normalize_learning_goal_for_recommendation",
  "success": true,
  "normalized_goals": ["rowkey_hotspot_avoidance"],
  "selected_nodes": ["rowkey_design"],
  "confidence": 0.82,
  "suggested_next_action": "retry_recommendation",
  "reason": "goal tokens overlap with graph node outcomes and RAG evidence"
}
```

`accept_learning_plan(state: dict) -> dict`

输入要求：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "就按这条路径开始",
  "auto_accept": false,
  "recommendation_result": {
    "success": true,
    "best_path": {"path": ["n1", "n2"]}
  },
  "candidate_index": 0
}
```

输出：

```json
{
  "tool": "accept_learning_plan",
  "success": true,
  "plan": {"plan_id": "plan_xxx", "status": "active"},
  "next_task": {"step_id": "step_1", "status": "active"},
  "suggested_next_action": "generate_current_step_resource"
}
```

重要内部逻辑：

- 推荐成功后不能默认采纳。
- `accept_learning_plan` 必须来自用户明确确认，或 payload 显式 `auto_accept=true`。
- `auto_accept=true` 只允许测试、演示或管理员流程使用，并写入 artifact。
- `accept_learning_plan` 不能自己重选路径；输入必须包含 `recommendation_result` 和 `candidate_index` 或 `best_path`。
- 推荐失败但已有 active plan 且用户意图是继续时，可以走 `continue_existing_plan`，不改写推荐结果。
- 无语义证据时返回 `ask_goal_clarification`，不能 fallback 到任意 syllabus 节点。

### 4. 测试用例的构建描述

- 推荐成功但未确认时返回 `wait_user_acceptance`，不创建 plan。
- 用户确认或 `auto_accept=true` 时才创建 active learning plan。
- 推荐失败但 graph/RAG 有语义证据时重试。
- 推荐失败且无语义证据时 `ask_goal_clarification`。
- 已有 active plan 的“继续学习”不重新选择任意节点。

## 阶段 5：当前 step 资源生成

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/generative_task.py
tests/test_total_agent_task.py
tests/total_agent/test_total_agent_e2e.py
```

### 2. 函数级收口的完整数据流

```text
generate_current_step_resource
  -> get_next_learning_task
  -> build generative request from current step
  -> generative_task.run_generative_task / existing generative task portal
  -> return resources summary
```

### 3. 精确到输入输出的函数级收口

`get_next_learning_task(state: dict) -> dict`

输出：

```json
{
  "tool": "get_next_learning_task",
  "success": true,
  "next_task": {
    "step_id": "step_xxx",
    "node_id": "rowkey_design",
    "title": "HBase RowKey 设计",
    "outcomes": ["rowkey_design"]
  },
  "error_code": "",
  "error_message": ""
}
```

`generate_current_step_resource(state: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "next_task": {
    "node_id": "rowkey_design",
    "title": "HBase RowKey 设计",
    "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"]
  },
  "resource_types": ["documents"]
}
```

输出：

```json
{
  "tool": "generate_current_step_resource",
  "success": true,
  "next_task": {},
  "resources": [
    {
      "resource_id": "documents-xxx",
      "resource_type": "documents",
      "status": "ready"
    }
  ],
  "suggested_next_action": "record_learning_feedback",
  "error_code": "",
  "error_message": ""
}
```

重要内部逻辑：

- 默认只生成当前 step 所需资源。
- 未指定资源类型时优先 `documents`，不默认全量生成。
- 资源 request 使用当前 step 的 `title/outcomes/node_id`。
- 资源生成失败不推进 learning plan。

### 4. 测试用例的构建描述

- active step 存在时生成当前 step 资源。
- payload 包含当前 step title/outcomes。
- 默认不生成全套资源。
- 真实资源生成只在 large opt-in E2E 打开。

## 阶段 6：学习反馈、step 推进和 study graph 同步

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tasks/study_graph_task.py
tests/test_total_agent_task.py
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
```

### 2. 函数级收口的完整数据流

```text
record_learning_feedback
  -> append learning_event_recorded to learning_plan manifest
  -> update current step status
  -> activate next pending step
  -> optionally sync resource event to study_graph
  -> get_next_learning_task
```

### 3. 精确到输入输出的函数级收口

`record_learning_feedback(state: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "plan_id": "plan_xxx",
  "step_id": "step_xxx",
  "resource_id": "documents-xxx",
  "event_type": "resource_completed",
  "status": "completed",
  "score": 0.86
}
```

输出：

```json
{
  "tool": "record_learning_feedback",
  "success": true,
  "updated_step": {"status": "completed"},
  "activated_step": {"status": "active"},
  "study_graph_sync": {
    "attempted": true,
    "success": true,
    "warning": ""
  },
  "next_task": {},
  "suggested_next_action": "generate_current_step_resource",
  "error_code": "",
  "error_message": ""
}
```

`skip_current_step(state: dict) -> dict`

输出：

```json
{
  "tool": "skip_current_step",
  "success": true,
  "updated_step": {"status": "skipped"},
  "activated_step": {"status": "active"},
  "suggested_next_action": "generate_current_step_resource"
}
```

重要内部逻辑：

- learning plan manifest 是计划执行事实。
- study graph 是学习事实和成长树，不保存完整 plan。
- step 完成或跳过后才推进下一步。
- study graph 同步失败不回滚 learning plan 事件，但必须返回 warning。

### 4. 测试用例的构建描述

- completed 事件推进到下一 step。
- skipped 事件推进到下一 step。
- resource_completed 触发 study graph 更新。
- study graph 更新失败返回 warning，learning plan 不回滚。

## 阶段 7：验收分层和 artifact 契约

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
tests/TEST_REPORT.md
tests/artifacts/total_agent/
```

### 2. 函数级收口的完整数据流

```text
small deterministic
  -> intent routing
  -> plan/event/next_task state machine

medium task integration
  -> personal_recommendation_task
  -> learning_plan
  -> current step resource stub or mock

large opt-in
  -> MySQL + profile + personal recommendation + real RAG
  -> generative current step resource
  -> study_graph sync
```

### 3. 精确到输入输出的函数级收口

验收 artifact：

```json
{
  "schema_version": "total_agent.v1",
  "intent": "generate_current_step_resource",
  "tool_trace": [],
  "result": {},
  "suggested_next_action": "record_learning_feedback",
  "artifacts": {
    "learning_plan_manifest": "path",
    "resource_manifest": "path",
    "study_graph_manifest": "path"
  },
  "terminal_state": ""
}
```

重要内部逻辑：

- 所有 artifacts 放在 `tests/artifacts/total_agent/`。
- 不把 artifacts 放在 `tests/total_agent/`。
- large clarification 场景可以合法结束于 `terminal_state="ask_goal_clarification"`。
- large deep success 场景必须走到 resource generation 和 study graph sync。

### 4. 测试用例的构建描述

默认 CI：

```bash
python -m pytest -q tests/test_total_agent_task.py tests/total_agent/test_process_contract.py
```

LLM 工具选择：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_total_agent_agent_choice.py -m llm
```

大型 opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" -rs
```

通过标准：

- small/medium 默认稳定通过。
- 覆盖 `insufficient`、`history-driven`、`force` 三类主路径。
- large clarification 场景允许以 `ask_goal_clarification` 合法结束。
- large deep success 场景必须走到资源生成和学习图谱同步。

