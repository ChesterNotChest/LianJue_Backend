# Total Agent dev doc

本文档记录当前 `total_agent` 后端运行时的关闭状态。产品或论文中可以称为 Teacher Agent；代码、测试和 artifact 统一使用 `total_agent` 命名。

## 当前状态

Total Agent 后端核心链路已经完成，不包含 API/前端接入。当前已验证的主链路是：

```text
student message
  -> load_total_context
      -> read active learning_plan
      -> read persisted profile
      -> read study graph state
  -> infer_user_intent
  -> route by intent
  -> call task portals
  -> return TotalAgentResult + tool_trace + suggested_next_action
```

支持的 intent：

- `recommend_learning_path`
- `accept_recommendation`
- `generate_current_step_resource`
- `answer_learning_question`
- `record_learning_feedback`
- `skip_current_step`
- `ask_goal_clarification`

即时答疑相关枚举定义在 `tasks/total_agent/agent_contracts.py`：

```text
question_type:
  concept_explanation
  learning_strategy
  exercise_help
  unknown

answer next_actions:
  offer_resource
  offer_practice
  continue_current_step
  clarify_goal

warnings:
  low_relevance_evidence
  profile_weak_points_filtered

tone_style:
  pragmatic
  friendly_pragmatic
  encouraging

answer_style:
  concise
  normal
  detailed

session window:
  QA_CONTEXT_SESSION_WINDOW_TURNS = 6
```

系统层职责边界：

- Total Agent 是全局调度中枢，负责 intent、上下文读取、工具路由、异常回退和统一输出。
- Total Agent 不直接生成教学内容、不直接改写画像、不直接编辑学习树，只通过 task 门户调用子模块。
- 个性化学习闭环遵循“画像描述状态 -> 推荐决定路径 -> 资源服务当前节点 -> 反馈回流计划与学习树”的顺序。
- “资源推送”在当前实现中不是独立业务模块，而是当前 active plan step 的资源生成和前端展示动作。
- 未实现的内容审核 Agent、学习效果评估 Agent、视频/动画脚本生成不作为当前 Total Agent 能力承诺；当前只保留后续扩展边界。

正式入口：

```python
run_total_agent(payload, use_llm=False)
run_total_agent_agent(payload)
get_total_agent()
```

默认入口是 deterministic runtime；`use_llm=True` 或 `run_total_agent_agent` 才走 pydantic-ai tool-choice。

## 工具边界

Agent 工具定义在 `tasks/total_agent/agent_tools.py`：

```text
load_total_context
infer_user_intent
run_learning_recommendation
normalize_learning_goal_for_recommendation
accept_learning_plan
get_next_learning_task
generate_current_step_resource
retrieve_learning_evidence
answer_learning_question
record_learning_feedback
skip_current_step
```

Total Agent 不直接编造业务产物，只通过 task 门户调用子能力：

```text
learning_profile_task
  -> get_persisted_learning_profile
  -> get_or_build_learning_profile only when explicitly opted in

personal_recommendation_task
  -> run_recommendation_route_from_payload
  -> accept_recommendation_path
  -> get_active_learning_plan
  -> append / update learning_plan manifest

generative_task
  -> generate_resources_from_request through process_resource_generation_request

study_graph_task
  -> get_learning_tree_features
  -> get_course_learning_tree_summary
  -> submit_learning_tree_changes for feedback sync
```

## 关键行为

- 推荐成功后默认不自动采纳，返回 `wait_user_acceptance`。
- 只有用户明确确认或 payload 显式 `auto_accept=true` 时，才创建 active learning plan。
- 有 active plan 时，“继续学习”优先沿用当前 active step，不重新随机推荐。
- 没有语义证据时返回追问，不用任意 syllabus 节点强行推进。
- `load_total_context` 会读取 persisted profile 和 study graph state；读取失败只产生 warning，不阻断 active plan。
- Total Agent 不在 runtime 里伪造 mock profile、mock study graph 或 mock resource result。
- `profile_summary.profile_source` 用于审查画像来源：`persisted_profile`、`built_profile` 或 `none`。
- 真实画像字段保持 Profile Agent 原生风格，例如 `concept_gaps`、`bottleneck_topics`、`knowledge_mastery`、`resource_preference`。
- `normalize_profile_summary` 将真实画像归一为调度摘要：`weak_points`、`preferred_formats`、`risk_level`、`time_budget`。
- `build_current_step_resource_strategy` 根据 message、当前 step、profile 和 study graph 生成资源策略。
- 用户显式 `resource_types` 优先，不被 profile 偏好覆盖。
- 当前 step 命中画像或学习树弱点时，资源策略会倾向 `targeted`，并可扩展到 `documents + quiz + mindmap`。
- `tool_generate_current_step_resource` 不直接逐个等待 Resource Agent。它只调用一次 `process_resource_generation_request`；处理器先冻结完整 `resource_type_tasks`，再并行调用多个单类型 Resource Agent。
- 每个单类型 Resource Agent 只能生成 `assigned_resource_type` 对应资源；自然语言 message/question 不能新增或覆盖结构化资源类型。
- 资源生成结果除扁平 `resources` 外，还返回 `resource_tasks`、`resource_results`、`failed_resource_types` 和 `overall_status`，供前端展示每类资源状态。
- `record_learning_feedback` 先写 learning plan manifest，再推进 step，并尝试同步 study graph。
- study graph sync 失败不回滚 learning plan 事件，但必须记录 warning。
- 所有失败返回结构化 `error_code/error_message`。
- `answer_learning_question` 是即时答疑闭环，不生成资源、不推进 plan、不写 feedback。
- 即时答疑会先分类问题类型：`concept_explanation`、`learning_strategy`、`exercise_help` 或 `unknown`。
- 概念型问题走 RAG evidence + 上下文解释；策略型问题走 active plan / next task / weak points / study graph weak nodes。
- 即时答疑返回结构化 `answer` payload，稳定包含 `question_type`、`text`、`key_points`、`evidence_used`、`plan_reference`、`next_actions`、`confidence`、`warnings`。
- `conversation_history` / `dialogue_history` / `messages` 会被压缩为 `session_context`，只用于本轮指代消解和 query hints，不写入 profile 或 plan。
- `tone_style` 和 `answer_style` 只影响用户可见 `answer.text` 的语气和详略，不影响 intent、question_type、plan_reference 或 next_actions。
- RAG query 会拼接 message、session topic hints、learning goal、next task 和相关 weak nodes，并限制长度；低相关 evidence 返回 `low_relevance_evidence` warning。
- profile weak points 只在和问题、当前 step、outcomes、study graph 或 session hints 相关时进入回答文本。
- `tool_status_events` 是当前同步运行结果的稳定字段；它可供前端观察工具阶段，但还不是正式 streaming/SSE 协议。

即时答疑 answer payload 稳定结构：

```json
{
  "question_type": "learning_strategy",
  "text": "你现在可以这样走：当前步骤是 HBase 基础...",
  "key_points": [
    "当前步骤：HBase 基础",
    "先完成当前 step，再围绕 RowKey 热点做针对练习"
  ],
  "evidence_used": [
    {"title": "HBase RowKey 热点", "source": "RAG", "relevance": "medium"}
  ],
  "plan_reference": {
    "plan_id": "plan_xxx",
    "current_step_id": "step_xxx",
    "current_step_title": "HBase 基础",
    "current_step_status": "active"
  },
  "relevant_weak_points": ["RowKey 热点", "预分区"],
  "filtered_weak_points": ["大数据感知与获取涉及数据的来源与类型"],
  "next_actions": [
    {
      "action": "continue_current_step",
      "label_key": "agent.answer.next_action.continue_current_step",
      "resource_type": "documents"
    }
  ],
  "session_context_used": true,
  "confidence": 0.84,
  "tone": {
    "tone_style": "friendly_pragmatic",
    "answer_style": "normal"
  },
  "warnings": []
}
```

字段约束：

- `text` 面向用户展示，不能为空。
- `key_points` 保持 1-6 条短句；为空时从 `text` 生成 fallback。
- `evidence_used` 只放轻量摘要，不放 RAG 原文。
- `plan_reference` 策略型问题应尽量填充；无 active plan 时为空对象。
- `next_actions` 给前端按钮/推荐动作使用，不依赖自然语言解析。
- `confidence` clamp 到 0-1。
- `warnings` 使用结构化 warning code。
- `normalize_answer_payload` / `validate_answer_payload` 是最终统一入口；工具函数用确定性逻辑组装 dict，不依赖模型自由 JSON。

## Agent 状态事件

当前后端已经把 Agent 工作状态收口到同步结果字段，不需要依赖测试侧 `print` 或 artifact 文本。一次 Total Agent 请求会共享同一个 `run_id`，并在返回结果里带上：

```json
{
  "tool_trace": ["load_total_context", "infer_user_intent"],
  "tool_status_events": [
    {
      "event_id": "evt_xxx",
      "run_id": "total_agent_run_xxx",
      "agent": "total_agent",
      "stage": "load_total_context",
      "status": "running",
      "event_key": "total_agent.load_total_context.running",
      "label_key": "agent.total_agent.load_total_context.running",
      "message": "",
      "timestamp": 1780640000,
      "payload": {}
    }
  ]
}
```

事件字段约束：

- `agent`、`stage`、`status` 是稳定机器字段，前端可用它们做 stepper、icon 和状态判断。
- `event_key` 采用 `${agent}.${stage}.${status}`，用于日志、测试和前端匹配。
- `label_key` 只提供 i18n 映射 key；前端文案不依赖后端中文。
- `message` 是 debug/fallback 短文本，允许为空，不作为 UI 状态判断依据。
- `payload` 只放轻量摘要，不放完整 profile、RAG 原文或资源正文。

当前已接入的状态来源：

```text
total_agent
  load_total_context
  infer_user_intent
  run_learning_recommendation
  normalize_learning_goal_for_recommendation
  accept_learning_plan
  get_next_learning_task
  generate_current_step_resource
  retrieve_learning_evidence
  answer_learning_question
  record_learning_feedback
  skip_current_step

profile_agent
  load_context / assemble_profile
  通过 load_profile_summary 的 status_state 汇入 Total Agent tool_status_events

recommendation_agent
  rank_path
  通过 run_learning_recommendation 的 status wrapper 汇入 Total Agent tool_status_events

resource_agent
  read_generation_request
  read_generation_plan
  retrieve_generation_materials
  write_generation_draft
  generate_resource_payload
  persist_generated_resource
  通过 generate_current_step_resource 汇入 Total Agent tool_status_events

study_graph
  read_features
  submit_changes / feedback sync
  通过 Total Agent context load 或 feedback sync 汇入 warning/status 摘要
```

边界：

- 当前是“同步事件收集”，不是正式 streaming API。
- 已能支持请求完成后展示阶段轨迹，也能在服务端 callback 存在时即时发出 running/succeeded/failed。
- 暂不承诺模型 token 流式输出，也不暴露 pydantic-ai 内部 tool calling 细节。
- 如果后续要做前端实时进度条，应在现有 `tool_status_events` schema 上增加 SSE/WebSocket/polling 出口，而不是新增一套状态协议。

## 资源生成

资源生成已经全量逐出 LiteLLM 内容生成路径。当前资源内容生成由资源 Agent 自己完成：

```text
Total Agent resource_strategy
  -> process_resource_generation_request
  -> freeze resource_type_tasks
  -> parallel single-type generative_task.generate_resources_from_request calls
  -> resource agent planning / retrieval / draft per type
  -> OpenAI-compatible pydantic-ai content Agent
  -> persist_generated_resource
```

不保留 LiteLLM fallback。RAG 增强也由资源 Agent 承担检索与编排，内容落盘由资源 Agent 完成。Resource Agent 的 `tool_status_events` 会被聚合回 Total Agent 结果，并携带 `payload.resource_type` / `payload.task_id`，用于前端生成状态回显。

当前全真实 E2E 已生成并校验：

```text
documents
quiz
mindmap
```

人工抽查结论：document 和 mindmap 质量可用；quiz 内容有效。已补充 quiz markdown 选项前缀清洗，避免模型输出 `A. xxx` 时渲染成 `A. A. xxx`。

## E2E 分层

默认单元和集成测试不访问真实 LLM/RAG/DB。Total Agent 当前统一到一个 E2E 主入口：

```text
default deterministic
  -> fast regression for routing, context, strategy, feedback

tests/total_agent/test_total_agent_e2e.py
  -> deep student state fixture
  -> persisted profile + deep study graph + active plan
  -> no real LLM/RAG/DB by default
  -> opt-in real profile / recommendation / resource / RAG / DB cases
  -> real Profile Agent
  -> real Total Agent
  -> real resource generation Agent
  -> real DB
  -> real study graph sync
```

深状态 fixture 固化在：

```text
tests/fixtures/total_agent/deep_student_state.json
```

该 fixture 只保存测试语料和场景定义，不提交运行后生成的 profile、learning plan、study graph 或 Total Agent result。运行产物写入 `tests/artifacts/`。

`tests/total_agent/e2e_cases_*.py` 只承载场景实现，不作为用户或 CI 回归入口；不保留旧拆分 E2E 入口回退。

当前 E2E 场景矩阵：

| 场景 | 入口 | 覆盖重点 |
|---|---|---|
| 默认深状态夹具 | `test_e2e_state_fixture_builds_deep_student_state` | profile、learning plan、study graph、current resource、message 历史均可构造 |
| 策略型即时答疑 | `test_total_agent_e2e_answer_learning_question_learning_strategy` | active plan / next task / weak points / session context 进入 answer，不推进 plan、不生成资源 |
| profile-driven continue | `test_total_agent_e2e_profile_driven_continue` | persisted profile 原生字段归一化为资源策略信号 |
| study graph weak continue | `test_total_agent_e2e_study_graph_weak_step_continue` | 当前 step weak 时资源策略 targeted |
| study graph stale review | `test_total_agent_e2e_study_graph_stale_step_review` | 当前 step stale 时资源策略 review/mindmap |
| feedback update | `test_total_agent_e2e_feedback_updates_plan_and_study_graph` | feedback 写 learning plan manifest、推进 step、同步 study graph |
| no-force clarification | `test_total_agent_e2e_vague_goal_asks_clarification_without_plan` | 无 active plan 且目标不清时追问，不强推节点 |
| unclear with active plan | `test_total_agent_e2e_continue_existing_plan_when_goal_unclear_but_plan_active` | 目标不清但已有 active plan 时继续当前 step |
| natural real RAG large E2E | `test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db` | 真实 DB/Profile/Recommendation/RAG 入口；无路径时稳定 `ask_goal_clarification` |
| aligned success large E2E | `test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph` | 确定性推荐路径 + 真实资源生成/DB/study graph 成功闭环 |
| real deep all agents | `test_total_agent_e2e_real_deep_state_all_agents` | 深状态 + 真实 Profile/Total/Resource/DB/study graph 全链路 |
| real RAG QA | `test_total_agent_e2e_real_deep_state_answer_learning_question` | 深状态 + 真实 RAG 概念型即时答疑 |

## 最近收口

默认 E2E 入口已通过：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

即时答疑质量默认回归已通过：

```bash
python -m pytest -q tests/test_total_agent_answer_quality.py tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_answer_learning_question_learning_strategy -rs
```

全真实 opt-in 统一入口：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

最近一次全真实 deep-state 记录：

```text
model: openai/qwen3.5-27b
result: 1 passed
user_id: 76
syllabus_id: 29
continue intent: generate_current_step_resource
feedback intent: record_learning_feedback
resource strategy: persisted_profile, documents/quiz/mindmap, targeted
learning plan: feedback 后推进到 HBase RowKey 设计
study graph: 12 nodes / 7 edges, feedback synced
```

关键 artifact：

```text
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/real_deep_state_all_agents_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/student_state_fixture_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/profiles/29-76.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/learning_plan/learning_plan/user_76/syllabus_29/manifest.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/manifest.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/change_log.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/documents/documents-20260604181856-f7ce0b/document.md
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/quiz/quiz-20260604182424-04ee82/quiz.md
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/mindmap/mindmap-20260604182520-1339b8/mindmap.mmd
```

## 测试命令

默认回归：

```bash
python -m pytest -q tests/test_total_agent_task.py tests/test_total_agent_answer_quality.py
```

上下文策略前置样本：

```bash
python -m pytest -q tests/total_agent/test_context_strategy_contract.py
```

统一 E2E 默认深状态：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

统一全真实 opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

## 文档事实源

`docs/total_agent_dev_doc.md` 是 Total Agent 唯一事实源。旧 `small_plan` / `contract` 的有效内容已经融合进本文：

- 即时答疑质量、结构化 answer、会话上下文、tone/style。
- 深状态 E2E、profile-driven continue、study graph weak/stale、feedback sync、clarification/no-force。
- 全真实 opt-in 与 aligned graph 稳定成功闭环。
- Agent 状态事件与 `tool_status_events`。

旧阶段文档可删除；如果后续发现旧文档仍有有效事实，应先融合进本文或测试，再删除旧文档。

## 后续非阻塞项

- Profile Agent 的 `concept_gaps` 已增加短语化过滤；后续仍可继续提升知识点抽取质量。
- Quiz markdown 选项前缀重复已在 renderer 层修正。
- API/前端接入还未纳入本关闭报告。
- 真正的前端“进行中”状态需要单独设计 SSE、WebSocket 或 polling 出口；当前 dev doc 只承诺同步结果里的 `tool_status_events` schema。
