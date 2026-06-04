# Total Agent small plan

> 本计划用于推进正式总 Agent（Total Agent）实现。后续代码、测试和 artifact 统一使用 `total_agent` 命名；`Teacher Agent` 只作为产品/论文叙述中的角色名保留，不再作为工程命名空间。当前 `tests/total_agent/` 已经沉淀了总 Agent 前置闭环的行为契约；正式实现时应复用这些契约，不重新设计一套不同的流程。

## 计划关系

当前存在三类相关文档，边界如下：

```text
docs/total_agent_small_plan.md
  -> 正式 Total Agent runtime 实现计划和背景

docs/total_agent_contract.md
  -> 正式 Total Agent 执行级实现契约

tests/total_agent/small_plan.md
tests/total_agent/contract.md
  -> 测试侧前置闭环契约，只验证推荐、learning_plan、反馈事件和下一任务衔接

docs/*_dev_doc.md
  -> 子能力关闭报告，说明总 Agent 可调用的稳定入口和产物
```

`tests/total_agent/*` 不是正式总 Agent 的重复计划；它们是实现总 Agent 前已经跑通的行为样本和验收基线。

## 目标

总 Agent 不是简单串联 4 个子 Agent，而是多轮学习过程调度器。它负责根据用户自然语言和当前学习状态决定下一步动作：

```text
用户自然语言消息
  -> 读取 total context
  -> 识别意图
  -> 判断 active learning_plan / next_task / recent resources / study_graph state
  -> 调用对应 task 门户
  -> 必要时做目标归一化、重试或追问
  -> 返回 result + suggested_next_action
```

当前已经通过测试契约验证的基础能力：

- 推荐路径可以被采纳为 `learning_plan`。
- 学习事件可以推进 plan step 状态。
- 多轮消息需要继承 `active_plan_id`、`current_resource_id` 和当前 step。
- `suggested_next_action` 是总 Agent 输出的一等字段。
- 推荐无 `best_path` 时不能生成偏题资源，必须先做目标归一化或追问。
- 已有 active plan 时，可以继续执行当前计划，而不是重新挑任意 syllabus 节点。
- 推荐路径只是建议；采纳 learning plan 必须来自学生确认，测试或演示可以显式使用 `auto_accept=true`。
- 每周知识点已经可以通过 personal recommendation 的 Agent/RAG concept decomposer 破拆为推荐侧 concept graph；规则 fallback 只作为可诊断兜底。
- 资源生成、学习画像、学生成长树和学习路径推荐四个子能力均已有总 Agent 可调用的 task/agent 边界。

## 阶段 1：建立总 Agent runtime 和工具边界

### 0. 新增的常量定义

建议新增到 `tasks/total_agent/agent_contracts.py`：

```python
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"

TOTAL_AGENT_TOOL_ORDER = {
    "recommend_learning_path": [
        "load_total_context",
        "infer_user_intent",
        "run_learning_recommendation",
        "normalize_learning_goal_for_recommendation"
    ],
    "accept_recommendation": [
        "load_total_context",
        "infer_user_intent",
        "accept_learning_plan",
    ],
    "generate_current_step_resource": [
        "load_total_context",
        "infer_user_intent",
        "get_next_learning_task",
        "generate_current_step_resource",
    ],
    "record_learning_feedback": [
        "load_total_context",
        "infer_user_intent",
        "record_learning_feedback",
        "get_next_learning_task",
    ],
}

TOTAL_AGENT_INTENTS = {
    "recommend_learning_path",
    "accept_recommendation",
    "generate_current_step_resource",
    "record_learning_feedback",
    "skip_current_step",
    "ask_goal_clarification",
}
```

### 1. 影响的文件范围

```text
tasks/total_agent/__init__.py             # 新增包
tasks/total_agent/agent_contracts.py      # 新增结构化输出与常量
tasks/total_agent/agent_tools.py          # 新增工具实现
tasks/total_agent/agent_runtime.py        # 新增 pydantic-ai runtime
tasks/total_agent_task.py                 # 可选薄门户；需要 API/前端统一入口时再新增
tests/test_total_agent_task.py            # 新增默认 deterministic 测试
tests/test_total_agent_agent_choice.py    # 新增 opt-in LLM 工具选择测试
tests/total_agent/test_process_contract.py
tests/total_agent/contract.md
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
run_total_agent(payload)
  -> TotalAgent runtime
      -> load_total_context
      -> infer_user_intent
      -> route by intent:
          recommend_learning_path
            -> run_learning_recommendation
            -> normalize_learning_goal_for_recommendation if needed
            -> return candidates and suggested_next_action=wait_user_acceptance
          accept_recommendation
            -> require explicit user confirmation or auto_accept=true
            -> accept_learning_plan
          generate_current_step_resource
            -> get_next_learning_task
            -> generate_current_step_resource
          record_learning_feedback
            -> record_learning_feedback
            -> get_next_learning_task
  -> TotalAgentResult
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

- 只调用 task 门户，不直接 import 各子包 service。
- 默认不一次性生成全套资源，只围绕当前 step 生成用户需要的资源。
- 所有失败返回结构化错误。
- LLM Agent 只负责调度工具和解释意图，不直接编造推荐路径、学习计划或资源 manifest。
- `accept_learning_plan` 不在推荐成功后默认执行；只有用户明确确认、payload 显式 `auto_accept=true`，或测试 fixture 指定自动采纳时才允许调用。

### 4. 测试用例的构建描述

- 默认 deterministic 测试验证 `run_total_agent` 对“推荐/继续/完成/跳过”四类消息的路由结果。
- 断言 `tool_trace` 与 intent 匹配。
- 断言 `suggested_next_action` 合理。
- LLM opt-in 测试验证真实模型会选择预期工具，不依赖真实 RAG。

## 阶段 2：上下文读取与状态继承

### 0. 新增的常量定义

不新增全局常量。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tests/test_total_agent_task.py
tests/total_agent/test_process_contract.py
```

### 2. 函数级收口的完整数据流

```text
load_total_context(payload)
  -> read active learning_plan
  -> read next_task
  -> read recent resource ids from payload/context
  -> read optional study_graph_state
  -> build TotalContext
```

### 3. 精确到输入输出的函数级收口

`load_total_context(payload: dict) -> dict`

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
  "tool": "load_total_context",
  "success": true,
  "user_id": 8,
  "syllabus_id": 20,
  "active_plan": {},
  "next_task": {},
  "current_resource_id": "res_xxx",
  "study_graph_state": {
    "completed_node_ids": [],
    "weak_node_ids": [],
    "current_node_id": ""
  },
  "error_code": "",
  "error_message": ""
}
```

重要内部逻辑：

- active plan 优先来自显式 `context.active_plan_id`，否则读取当前 active plan。
- `next_task` 只来自 learning plan 状态，不从 syllabus 任意推断。
- `study_graph_state` 是推荐输入状态，不在此工具中修改 study graph。
- 没有 active plan 时返回空上下文，不抛异常，由后续 intent 决定推荐或追问。

### 4. 测试用例的构建描述

- 已有 active plan 时可以读出当前 active step。
- 完成一轮反馈后下一次调用能继承新的 active step。
- 没有 active plan 时返回结构化上下文，并允许进入推荐链路。

## 阶段 3：意图识别和动态路由

### 0. 新增的常量定义

不新增，复用 `TOTAL_AGENT_INTENTS`。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py
```

### 2. 函数级收口的完整数据流

```text
message + TotalContext
  -> infer_user_intent
  -> intent + confidence + required_context
  -> runtime chooses next tool chain
```

### 3. 精确到输入输出的函数级收口

`infer_user_intent(state: dict) -> dict`

输入：

```json
{
  "message": "我完成了刚才的文档",
  "active_plan": {},
  "next_task": {},
  "current_resource_id": "documents-xxx"
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

- “推荐/学什么/下一步路径”进入 `recommend_learning_path`。
- “继续/开始/给我资料”进入 `generate_current_step_resource`，但必须有 active plan 或可推荐路径。
- “完成/做完/看完/得分”进入 `record_learning_feedback`。
- “跳过/太简单/换一个”进入 `skip_current_step`。
- 置信度低或缺少目标时进入 `ask_goal_clarification`。

### 4. 测试用例的构建描述

- 覆盖推荐、继续、完成、跳过、模糊目标五类消息。
- 测试同一 plan 多轮调用的动态切换。
- LLM opt-in 测试只验证工具选择和结构化输出，不要求资源质量。

## 阶段 4：推荐链路、目标归一化和采纳

### 0. 新增的常量定义

可选新增：

```python
RECOMMENDATION_RECOVERY_ACTIONS = {
    "retry_recommendation",
    "ask_goal_clarification",
    "continue_existing_plan",
}
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tests/test_total_agent_task.py
tests/total_agent/test_total_agent_e2e.py
tests/total_agent/contract.md
```

### 2. 函数级收口的完整数据流

```text
recommend_learning_path intent
  -> run_learning_recommendation
      -> personal_recommendation_task.run_recommendation_route_from_payload
  -> if best_path exists:
      -> return recommendation candidates
      -> suggested_next_action = wait_user_acceptance
  -> if best_path missing:
      -> normalize_learning_goal_for_recommendation
      -> retry only when semantic evidence exists
      -> otherwise ask_goal_clarification
  -> never call accept_learning_plan implicitly

accept_recommendation intent
  -> require explicit confirmation or auto_accept=true
  -> require recommendation_result + candidate_index/best_path
  -> accept_learning_plan
  -> get_next_learning_task

  -> if active plan exists and user asks to continue:
      -> continue_existing_plan
```

### 3. 精确到输入输出的函数级收口

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

重要内部逻辑：

- 只使用 graph nodes、outcomes、titles、RAG evidence 和 profile goals 做归一化。
- 有明确语义证据才重试推荐。
- 没有证据时返回 `ask_goal_clarification`，不使用任意 syllabus fallback。
- 已有 active plan 且用户意图是继续时，不因为新推荐失败中断旧计划。

`accept_learning_plan(state: dict) -> dict`

输入：

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

- `accept_learning_plan` 表示执行采纳动作，不表示总 Agent 替学生决定采纳。
- 正式产品中必须来自用户明确确认，例如“采纳这条”“就按这个开始”“确认计划”。
- 测试、演示或管理员流程可以显式传入 `auto_accept=true`，但必须在 artifact 中记录。
- 输入必须包含已有 `recommendation_result` 和 `candidate_index` 或 `best_path`；该工具不能自己重新挑路径。
- 如果没有确认，也没有 `auto_accept=true`，返回 `wait_user_acceptance`，不创建 plan。

### 4. 测试用例的构建描述

- 推荐成功时可以采纳为 learning plan。
- 推荐成功但用户未确认时只返回候选，`suggested_next_action=wait_user_acceptance`。
- 用户明确确认或 `auto_accept=true` 时才会创建 active learning plan。
- 推荐失败但 RAG/graph 有语义证据时会重试。
- 推荐失败且无语义证据时返回 `ask_goal_clarification`。
- 已有 active plan 的“继续学习”不会重新选择任意节点。

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
generate_current_step_resource intent
  -> get_next_learning_task
  -> build generative request from current step
  -> generative_task.generate_resources_from_request
  -> return resource summary
```

### 3. 精确到输入输出的函数级收口

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
    {"resource_id": "documents-xxx", "resource_type": "documents", "status": "ready"}
  ],
  "suggested_next_action": "record_learning_feedback"
}
```

重要内部逻辑：

- 默认只生成当前 step 所需资源。
- 默认资源类型可以从用户消息推断；未指定时优先 `documents`，避免一次性全量生成。
- 资源 request 使用 step `title/outcomes`，不直接使用上一次推荐 question 作为主题。
- 资源生成失败时保留当前 step，不推进计划。

### 4. 测试用例的构建描述

- active step 存在时能生成当前 step 资源。
- 资源 payload 包含当前 step title/outcomes。
- 默认不生成全套资源。
- 真实 LLM/RAG 资源生成放入 opt-in E2E。

## 阶段 6：学习反馈、step 推进和 study graph 同步

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/personal_recommendation_task.py
tasks/study_graph_task.py
tests/test_total_agent_task.py
tests/total_agent/test_total_agent_e2e.py
```

### 2. 函数级收口的完整数据流

```text
record_learning_feedback intent
  -> append learning_event_recorded to learning_plan manifest
  -> update current step status
  -> activate next pending step
  -> sync resource event to study_graph
  -> get next task
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
  "study_graph_sync": {"attempted": true, "success": true},
  "next_task": {},
  "suggested_next_action": "generate_current_step_resource"
}
```

重要内部逻辑：

- learning_plan manifest 是计划执行事实。
- study_graph 是学习事实和成长树，不保存完整计划。
- step 完成或跳过后才推进下一步。
- study_graph 同步失败不应回滚 learning_plan 事件，但要返回 warning。

### 4. 测试用例的构建描述

- completed 事件推进到下一 step。
- skipped 事件推进到下一 step。
- resource_completed 能触发 study_graph 更新。
- study_graph 更新失败时返回结构化 warning。

## 阶段 7：验收分层

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py
tests/total_agent/test_process_contract.py
tests/total_agent/test_total_agent_e2e.py
tests/TEST_REPORT.md
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

验收产物应包含：

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
  }
}
```

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
- large clarification 场景允许以 `ask_goal_clarification` 合法结束。
- large deep success 场景必须走到 resource generation 和 study_graph sync。
- 所有 artifacts 放在 `tests/artifacts/total_agent/`，不放在 `tests/total_agent/` 内。

## 当前后续优先级

建议顺序：

```text
1. 实现 `tasks/total_agent/` 的最小 runtime、contracts 和工具。
2. 把 `tests/total_agent` 里的 deterministic router 契约迁移成正式工具行为。
3. 补默认 deterministic tests，覆盖 insufficient / history-driven / force 三类主路径。
4. 再补 LLM agent choice，验证真实模型会按意图选择工具链。
5. 最后补大型 opt-in E2E，把真实 RAG、DB、资源生成和 study_graph sync 串起来。
```

关键原则：

- 不用任意 fallback 节点强行推进。
- 有 active plan 时优先继续已有计划。
- 没有语义对齐时追问用户。
- 资源生成围绕当前 step，不默认全量生成。

## Next Deepening

Profile / Study Graph / Resource Strategy 的下一轮深化先作为测试侧预备契约收口，放在 `tests/total_agent/small_plan.md` 和 `tests/total_agent/contract.md` 中维护。稳定后再把通过测试验证的最小必要接口迁移回正式 `tasks/total_agent/` runtime。

正式实现侧继续遵守当前原则：

- 有 active plan 时优先 history-driven，不重新随机推荐。
- 推荐成功后等待学生确认，不隐式 accept。
- 没有语义证据时追问，不强行 fallback。
- 资源生成围绕当前 step，不默认全量生成。
- fallback 节点只作为诊断和降级信号，不能和 Agent/RAG 置信节点完全等价。

## 阶段 8：Profile / Study Graph / Resource Strategy 正式迁移

本阶段把 `tests/total_agent` 中已经通过的预备契约迁移进正式 `tasks/total_agent/` runtime。迁移范围只包含已验证的最小接口，不扩大到真实 profile 重建、真实 study graph 写入或复杂个性化推荐重排。

### 0. 新增的常量定义

建议新增到 `tasks/total_agent/agent_contracts.py`：

```python
TOTAL_AGENT_CONTEXT_SCHEMA_VERSION = "total_agent.context.v1"
RESOURCE_STRATEGY_DEFAULT_TYPE = "documents"

RESOURCE_STRATEGY_DIFFICULTY_STANDARD = "standard"
RESOURCE_STRATEGY_DIFFICULTY_TARGETED = "targeted"
RESOURCE_STRATEGY_DIFFICULTY_REVIEW = "review"
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tests/test_total_agent_task.py
tests/total_agent/test_context_strategy_contract.py
docs/total_agent_dev_doc.md
tests/TEST_REPORT.md
```

测试侧 `tests/total_agent/test_context_strategy_contract.py` 保留为预备契约样本；正式 runtime 测试新增到 `tests/test_total_agent_task.py`。

### 2. 函数级收口的完整数据流

```text
run_total_agent(payload)
  -> load_total_context
      -> get active learning_plan
      -> get next_task
      -> read profile summary, best-effort
      -> read study graph features, best-effort
      -> normalize profile_summary
      -> normalize study_graph_state
  -> infer_user_intent
  -> generate_current_step_resource
      -> get_next_learning_task
      -> build_current_step_resource_strategy
      -> build generative request from strategy
      -> generative_task.generate_resources_from_request
```

### 3. 精确到输入输出的函数级收口

`normalize_profile_summary(profile: dict | None) -> dict`

输入可以来自 `learning_profile_task` 的读取入口、profile artifact 或测试 mock。

输出：

```json
{
  "learning_goal": "掌握 HBase RowKey 热点规避",
  "weak_points": ["RowKey 热点", "预分区"],
  "preferred_formats": ["documents", "quiz"],
  "risk_level": "medium",
  "time_budget": {"minutes_per_day": 30},
  "updated_at": 1760000000
}
```

内部逻辑：

- 缺失字段归一为空字符串、空列表或空 dict。
- profile 读取失败不让 `load_total_context` 失败，只写 warning。
- profile 不覆盖用户显式 message、intent 或 resource_types。

`normalize_study_graph_state(features: dict | None) -> dict`

输出：

```json
{
  "current_node_id": "rowkey_design",
  "completed_node_ids": ["hbase_intro"],
  "weak_node_ids": ["rowkey_design"],
  "mastered_node_ids": [],
  "recent_node_ids": ["hbase_intro"],
  "stale_node_ids": [],
  "warnings": []
}
```

内部逻辑：

- 兼容缺失字段。
- study graph 读取失败不阻断 active plan / next task，只写 warning。
- study graph 状态只作为调度信号，不在 `load_total_context` 中写回。

`build_current_step_resource_strategy(state: dict) -> dict`

输入来自当前 Total Agent state：

```json
{
  "payload": {"message": "继续学习，最好给我一点练习"},
  "next_task": {
    "node_id": "rowkey_design",
    "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"]
  },
  "total_context": {
    "profile_summary": {
      "weak_points": ["RowKey 热点"],
      "preferred_formats": ["documents", "quiz"]
    },
    "study_graph_state": {
      "weak_node_ids": ["rowkey_design"]
    }
  }
}
```

输出：

```json
{
  "success": true,
  "schema_version": "total_agent.context.v1",
  "resource_types": ["documents", "quiz"],
  "difficulty": "targeted",
  "knowledge_items": ["rowkey_design", "rowkey_hotspot_avoidance", "RowKey 热点"],
  "reason": "current step is weak and profile/study graph indicates targeted practice",
  "strategy_signals": {
    "explicit_resource_types": false,
    "matched_profile_weak_point": true,
    "matched_study_graph_weak_node": true,
    "message_requests_practice": true,
    "message_requests_review": false
  },
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 用户显式 `resource_types` 优先，不被 profile 覆盖。
- 无显式类型且 profile/study graph 指向薄弱时，默认扩展为 `documents + quiz`。
- message 包含“代码/coding”时优先 `coding_practice`。
- message 包含“复习/总结/梳理/review”时选择复习型资源。
- 没有任何信号时保持 `documents`。
- strategy 只决定资源请求，不推进 learning plan。

`tool_generate_current_step_resource(state: dict) -> dict`

变更点：

- 调用 `build_current_step_resource_strategy`。
- generative request 使用 strategy 的：
  - `resource_types`
  - `knowledge_items`
  - `difficulty`
  - `strategy_reason`
  - `strategy_signals`
- 返回结果中保留 `resource_strategy`，便于 artifact 审查。

### 4. 测试用例的构建描述

正式默认测试补到 `tests/test_total_agent_task.py`：

- `test_total_agent_load_context_includes_profile_summary`
  - monkeypatch profile 读取入口。
  - 断言 `load_total_context` 输出包含 `profile_summary`。

- `test_total_agent_load_context_includes_normalized_study_graph_state`
  - monkeypatch `study_graph_task.get_learning_tree_features`。
  - 断言 `study_graph_state` 包含 weak/completed/recent/stale 字段。

- `test_total_agent_context_read_failures_are_warnings`
  - profile 或 study graph 读取抛错。
  - 断言 Total Agent 不失败，warnings 可见。

- `test_total_agent_resource_strategy_uses_profile_and_study_graph`
  - active step 命中 weak profile 和 weak graph。
  - 断言生成 request 的 `resource_types` 包含 `documents + quiz`。

- `test_total_agent_resource_strategy_respects_explicit_resource_types`
  - payload 显式 `resource_types=["documents"]`。
  - 断言不被 profile preferred formats 覆盖。

迁移完成后继续保留预备测试：

```bash
python -m pytest -q tests/total_agent/test_context_strategy_contract.py
```

正式 runtime 验收：

```bash
python -m pytest -q tests/test_total_agent_task.py
```
## 阶段 9：真实 Profile 读取接入 Total Agent

本阶段把正式 Total Agent 里的 `load_profile_summary(payload)` 从空 hook 接到真实画像读取入口。目标是让 `load_total_context` 能在真实链路中读到已有学生画像，并把它归一成资源策略可消费的 `profile_summary`。本阶段不在 Total Agent 内重建画像算法，不在读取失败时伪造 mock profile，也不把 profile 写回逻辑塞进 Total Agent。

边界：

- 正式链路禁止在 profile 读取失败时 fallback 到 mock profile。
- profile 缺失或读取失败时，只返回空 `profile_summary` 并写 warning。
- mock 只允许存在于测试 monkeypatch / fixture 中，不进入 `tasks/total_agent/agent_tools.py` 的真实失败分支。
- Total Agent 只读取和归一化画像，不负责计算画像、不刷新画像、不保存画像。
- 如果后续确实需要刷新画像，必须通过 `learning_profile_task` 的显式工具或单独 intent 触发。

### 0. 新增的常量定义

建议新增到 `tasks/total_agent/agent_contracts.py`：

```python
PROFILE_SOURCE_NONE = "none"
PROFILE_SOURCE_PERSISTED = "persisted_profile"
PROFILE_SOURCE_BUILT = "built_profile"

PROFILE_READ_ACTION_USE_PERSISTED_ONLY = "use_persisted_only"
PROFILE_READ_ACTION_BUILD_IF_MISSING = "build_if_missing"

PROFILE_WARNING_NOT_FOUND = "profile_not_found"
PROFILE_WARNING_READ_FAILED = "profile_read_failed"
PROFILE_WARNING_BUILD_SKIPPED = "profile_build_skipped"
```

默认策略：

```text
profile_read_action = use_persisted_only
```

只有 payload 显式 `profile_read_action="build_if_missing"` 或 opt-in E2E 明确打开时，才允许调用 `get_or_build_learning_profile` 构建缺失画像。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/learning_profile_task.py              # 只通过 task 门户调用，不改包内 service
tests/test_total_agent_task.py
tests/test_total_agent_agent_choice.py       # 只检查 artifact 字段，不要求真实 profile
tests/total_agent/test_total_agent_e2e.py    # opt-in 验证真实 profile 读取
docs/total_agent_dev_doc.md
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
run_total_agent(payload)
  -> load_total_context
      -> get active learning_plan
      -> get next_task
      -> load_profile_summary(payload)
          -> validate user_id / syllabus_id
          -> try learning_profile_task.get_persisted_learning_profile
          -> if missing and profile_read_action=build_if_missing
               -> learning_profile_task.get_or_build_learning_profile
          -> never create mock profile on failure
      -> normalize_profile_summary(profile)
      -> read and normalize study_graph_state
  -> infer_user_intent
  -> generate_current_step_resource
      -> build_current_step_resource_strategy
      -> strategy consumes real profile_summary when available
```

失败路径：

```text
profile missing / read failed
  -> load_profile_summary returns success=false or empty profile with warning
  -> normalize_profile_summary({})
  -> load_total_context remains success=true
  -> resource strategy uses study graph / message / default documents
```

### 3. 精确到输入输出的函数级收口

#### `load_profile_summary(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "message": "继续学习 RowKey",
  "profile_read_action": "use_persisted_only"
}
```

输出：命中已持久化画像

```json
{
  "success": true,
  "source": "persisted_profile",
  "profile": {
    "user_id": 8,
    "syllabus_id": 20,
    "learning_goal": "掌握 HBase RowKey 热点规避",
    "knowledge_levels": {},
    "preferences": {
      "preferred_formats": ["documents", "quiz"]
    },
    "weak_points": ["RowKey 热点"],
    "risk_level": "medium",
    "updated_at": 1760000000
  },
  "warnings": [],
  "error_code": "",
  "error_message": ""
}
```

输出：未命中且不构建

```json
{
  "success": false,
  "source": "none",
  "profile": {},
  "warnings": ["profile_not_found", "profile_build_skipped"],
  "error_code": "profile_not_found",
  "error_message": "no persisted learning profile"
}
```

重要内部逻辑：

- `user_id` 缺失时直接返回结构化错误，不抛异常。
- `syllabus_id` 缺失时优先返回空 profile，不任意猜测课程画像。
- 默认只调用 `learning_profile_task.get_persisted_learning_profile(user_id, syllabus_id)`。
- `profile_read_action="build_if_missing"` 时，才允许调用 `learning_profile_task.get_or_build_learning_profile(..., refresh_profile=False)`。
- `get_or_build_learning_profile` 异常时返回 warning，不让 `load_total_context` 失败。
- 不允许硬编码 HBase / RowKey / quiz 等 mock profile。
- 不允许在 `except` 分支返回测试用假画像。

#### `normalize_profile_summary(profile: dict | None) -> dict`

输入可以是 `load_profile_summary` 的完整返回，也可以是已展开 profile。

输出：

```json
{
  "learning_goal": "掌握 HBase RowKey 热点规避",
  "weak_points": ["RowKey 热点"],
  "preferred_formats": ["documents", "quiz"],
  "risk_level": "medium",
  "time_budget": {"minutes_per_day": 30},
  "updated_at": 1760000000,
  "profile_source": "persisted_profile"
}
```

重要内部逻辑：

- 兼容 `profile.preferences.preferred_formats`、顶层 `preferred_formats`、`resource_preferences`。
- 兼容顶层 `weak_points`、`knowledge_weaknesses`、profile feature bundle 中可稳定识别的弱点字段。
- 输出 `profile_source`，便于 artifact 判断是真实读取还是空 profile。
- 缺失字段归一为空字符串、空列表或空 dict。
- 不根据 message 临时构造 weak_points，避免把用户意图误写成画像事实。

#### `tool_load_total_context(state: dict) -> dict`

变更点：

```json
{
  "profile_summary": {
    "learning_goal": "掌握 HBase RowKey 热点规避",
    "weak_points": ["RowKey 热点"],
    "preferred_formats": ["documents", "quiz"],
    "risk_level": "medium",
    "time_budget": {"minutes_per_day": 30},
    "updated_at": 1760000000,
    "profile_source": "persisted_profile"
  },
  "warnings": []
}
```

重要内部逻辑：

- `profile_summary.profile_source="none"` 时，资源策略不能假装命中 profile weak point。
- profile warning 合并到 `total_context.warnings`。
- profile 读取失败不影响 active plan 和 next task。

### 4. 测试用例的构建描述

默认 deterministic 测试补到 `tests/test_total_agent_task.py`：

- `test_total_agent_load_profile_summary_reads_persisted_profile`
  - monkeypatch `learning_profile_task.get_persisted_learning_profile` 返回真实形状 profile。
  - 断言 `load_profile_summary` 返回 `source="persisted_profile"`。
  - 断言没有 mock 字段污染。

- `test_total_agent_load_profile_summary_missing_profile_is_empty_warning`
  - monkeypatch persisted profile 返回 `None`。
  - 断言 `profile_summary.profile_source="none"`。
  - 断言 warnings 包含 `profile_not_found` / `profile_build_skipped`。
  - 断言不出现 HBase / RowKey 等测试假数据。

- `test_total_agent_load_profile_summary_build_if_missing_opt_in`
  - persisted 返回 `None`。
  - payload 显式 `profile_read_action="build_if_missing"`。
  - monkeypatch `get_or_build_learning_profile` 返回 profile。
  - 断言 `source="built_profile"`。

- `test_total_agent_load_profile_summary_read_failure_does_not_mock`
  - persisted 读取抛错。
  - 断言返回空 profile + warning。
  - 断言正式链路没有 fallback 到任意 mock。

- `test_total_agent_resource_strategy_with_real_profile_summary`
  - monkeypatch persisted profile 返回 preferred formats / weak points。
  - active step 命中 weak profile。
  - 断言 resource request 包含 `documents + quiz` 和 `profile_source="persisted_profile"`。

opt-in E2E：

- `test_total_agent_large_e2e_reads_real_learning_profile`
  - 先用 `learning_profile_task.get_or_build_learning_profile(..., refresh_profile=True)` 生成真实画像。
  - 再调用 Total Agent continue/resource generation。
  - 断言 artifact 中 `profile_summary.profile_source!="none"`。
  - 断言失败时保存 profile read warnings，但不伪造 mock profile。

验收命令：

```bash
python -m pytest -q tests/test_total_agent_task.py
```

真实 profile opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" -rs
```
