# Total Agent

全局调度中枢（论文/产品中可称为 Teacher Agent）。负责意图识别、上下文加载、工具路由、异常回退和统一输出。

**不直接生成教学内容、不直接改写画像、不直接编辑学习树。**（注：当前代码存在旁路，见 Known Issues）

## API Endpoints

### GET /api/total_agent/detail
返回 Total Agent 的模式信息。
- **Output**: `{intents, tool_order, entry_points}`

### POST /api/total_agent/run
运行 Total Agent（同步）。
- **Input**: `{user_id, syllabus_id, message: str, session_id?, use_llm?: bool}`
- **Output**: `{success, intent, tool_trace, tool_status_events, result, suggested_next_action, buddy_message?}`

### POST /api/total_agent/agent_run
运行 LLM 驱动的 Total Agent（同步，use_llm=true）。
- **Input**: 同上
- **Output**: 同上

### GET /api/chat/sessions
列出聊天会话。
- **Query**: `?user_id=N&syllabus_id=N`
- **Output**: `[{session_id, title, turn_count, created_at, updated_at}]`

### GET /api/chat/sessions/<session_id>/turns
获取会话的所有轮次。
- **Output**: `[{role, content, metadata_json, created_at}]`

## 主链路

```
student message
  → load_total_context
      → read active learning_plan
      → read persisted profile (summary)
      → read study graph features
  → infer_user_intent / note_intent
  → route by intent (TOTAL_AGENT_TOOL_ORDER)
  → call task portals
  → return TotalAgentResult + tool_trace + suggested_next_action
```

## 支持的 Intent

| Intent | 工具链 |
|--------|--------|
| `recommend_learning_path` | load_total_context → call_recommendation_agent |
| `accept_recommendation` | load_total_context → accept_learning_plan → get_next_learning_task |
| `generate_current_step_resource` | load_total_context → get_next_learning_task → generate_current_step_resource |
| `record_learning_feedback` | load_total_context → record_learning_feedback → get_next_learning_task |
| `skip_current_step` | load_total_context → skip_current_step → get_next_learning_task |
| `answer_learning_question` | load_total_context → retrieve_learning_evidence → answer_learning_question |
| `abandon_learning_plan` | load_total_context → abandon_learning_plan → get_next_learning_task |
| `ask_goal_clarification` | 无工具，返回澄清提示 |

## 双运行时模式

```
run_total_agent(payload, use_llm=False)  → deterministic_run_total_agent()  [默认]
run_total_agent(payload, use_llm=True)   → run_total_agent_agent()          [pydantic-ai tool-choice]
```

默认走 deterministic（规则路由），LLM 模式是 opt-in。

## 输出结构

```
TotalAgentResult:
  success: bool
  intent: str
  tool_trace: [str]              // 执行过的工具列表
  tool_status_events: [...]      // 工具阶段状态事件
  result: {context, ...}         // 各工具的输出聚合
  suggested_next_action: str
  buddy_message?: str            // 触发学伴的主动消息
```

## 即时答疑 (answer_learning_question)

答疑不推进 plan、不生成资源、不写 feedback。结构化输出：
```
{
  question_type: concept_explanation | learning_strategy | exercise_help | unknown,
  text: str,
  key_points: [str],
  evidence_used: [str],
  plan_reference: str,
  next_actions: [offer_resource | offer_practice | continue_current_step | clarify_goal],
  confidence: float,
  warnings: [low_relevance_evidence | profile_weak_points_filtered],
  tone_style: pragmatic | friendly_pragmatic | encouraging,
  answer_style: concise | normal | detailed
}
```

## Data Model

```
chat_session                        chat_turn
├── session_id (PK)                 ├── id (PK)
├── user_id (FK→user)               ├── session_id (FK)
├── syllabus_id                     ├── role
├── title                           ├── content
├── turn_count                      ├── metadata_json
├── message_history_json            └── created_at
├── created_at
└── updated_at
```

`message_history_json` is retained only for schema compatibility. Total Agent MUST NOT use persisted PydanticAI raw `message_history` as cross-turn context. The authoritative conversation history for Total Agent is `chat_turn` plus the frontend-provided recent visible `conversation_history`; current learning state MUST come from `load_total_context`.

## Requirements

### Requirement: Current Plan State Classification

Total Agent SHALL classify the current learning-path state from the current turn's authoritative context as exactly one of `selected_path`, `candidate_path`, or `no_path`.

#### Scenario: Active plan exists
- **WHEN** `load_total_context` finds an active learning plan for the current user and syllabus
- **THEN** the returned tool result MUST include `plan_state_kind: "selected_path"`
- **AND** the returned tool result MUST include the active plan summary and next task.

#### Scenario: Proposed recommendation exists without active plan
- **WHEN** `load_total_context` finds no active learning plan but finds a latest non-expired recommendation snapshot with `status: "proposed"`
- **THEN** the returned tool result MUST include `plan_state_kind: "candidate_path"`
- **AND** the returned tool result MUST include `pending_recommendation` with at least `recommendation_id`, `candidate_count`, `best_path_titles`, and `status`.
- **AND** the returned tool result MUST NOT describe the pending recommendation as an active plan.

#### Scenario: No plan and no proposal exists
- **WHEN** `load_total_context` finds neither an active learning plan nor a proposed recommendation snapshot
- **THEN** the returned tool result MUST include `plan_state_kind: "no_path"`
- **AND** `active_plan`, `next_task`, and `pending_recommendation` MUST be empty objects.

### Requirement: Candidate Acceptance Without Regeneration

Total Agent SHALL accept an existing proposed recommendation candidate directly when the user confirms a candidate option and the current plan state is `candidate_path`.

#### Scenario: User selects a numbered candidate
- **WHEN** the current `load_total_context` result has `plan_state_kind: "candidate_path"`
- **AND** the user asks to confirm or select candidate N
- **THEN** the LLM-driven Total Agent MUST call `accept_learning_plan` with the zero-based candidate index for N
- **AND** it MUST NOT call `call_recommendation_agent` unless the user explicitly asks for a fresh recommendation.

#### Scenario: Recommendation result is absent from transient state
- **WHEN** `accept_learning_plan` is called and `state["recommendation_result"]` is absent
- **AND** a latest proposed recommendation snapshot exists for the current user and syllabus
- **THEN** `accept_learning_plan` MUST load the snapshot detail and accept the selected candidate.

#### Scenario: No proposed snapshot exists
- **WHEN** the user asks to select a candidate
- **AND** `load_total_context` returns `plan_state_kind: "no_path"`
- **THEN** Total Agent MAY ask to regenerate recommendations or call `call_recommendation_agent`
- **AND** it MUST NOT claim that a selected path exists.

#### Scenario: User asks for a fresh recommendation
- **WHEN** the current `load_total_context` result has `plan_state_kind: "candidate_path"`
- **AND** the user explicitly asks to regenerate, replace, refresh, or produce a new recommendation set
- **THEN** Total Agent MAY call `call_recommendation_agent`
- **AND** the new recommendation MUST become the current pending candidate set.

### Requirement: User-Facing Candidate Ordinals Are Normalized

Total Agent SHALL treat natural-language candidate numbers as one-based display ordinals and normalize them to the zero-based candidate index used by recommendation storage.

#### Scenario: User selects the third candidate
- **WHEN** the current pending recommendation has at least three candidates
- **AND** the user says "third path", "third option", "plan three", or an equivalent selection phrase
- **THEN** Total Agent MUST accept the candidate at zero-based index `2`
- **AND** it MUST NOT accept the candidate at zero-based index `3`.

#### Scenario: Candidate ordinal is out of range
- **WHEN** the user selects candidate N
- **AND** the current pending recommendation contains fewer than N candidates
- **THEN** Total Agent MUST reject the acceptance attempt with an out-of-range error or ask the user to choose a valid candidate
- **AND** it MUST NOT silently accept a different candidate.

### Requirement: Accepted Candidate State Is Current Within The Same Run

After Total Agent successfully accepts a recommendation candidate, subsequent tools in the same run SHALL observe a selected active plan, not stale candidate-path state.

#### Scenario: Accept then load next task
- **WHEN** `accept_learning_plan` succeeds
- **AND** a later tool in the same run needs the current learning task
- **THEN** Total Agent state MUST contain `plan_state_kind: "selected_path"`
- **AND** `get_next_learning_task` MUST be allowed to read the newly active plan instead of returning `no_active_plan` due to stale `candidate_path` context.

### Requirement: Historical Tool Results Are Not Current State

Total Agent SHALL treat historical tool results as historical context and SHALL use the current turn's `load_total_context` result as the authority for current plan state.

#### Scenario: Historical accepted plan was later abandoned
- **WHEN** historical context contains an older `accept_learning_plan` or `get_next_learning_task` result
- **AND** the current `load_total_context` result has `plan_state_kind: "candidate_path"` or `plan_state_kind: "no_path"`
- **THEN** Total Agent MUST NOT answer that an active selected path exists based only on historical tool results.

#### Scenario: User asks whether candidates or selected path are visible
- **WHEN** the user asks whether Total Agent sees candidate paths or a selected path
- **THEN** Total Agent MUST answer from current `load_total_context.plan_state_kind`, `active_plan`, and `pending_recommendation`
- **AND** it MUST identify stale historical tool outputs as non-authoritative if they conflict.

### Requirement: Streaming Chat Persistence Uses Final Assistant State

The streaming Total Agent runtime SHALL persist the assistant chat turn from the final run result, not from the first terminal tool result in the run.

#### Scenario: Recommendation then accept in one streaming run
- **WHEN** a single streaming run calls `call_recommendation_agent` and later calls `accept_learning_plan`
- **THEN** the durable assistant ChatTurn MUST reflect the final accepted-plan outcome
- **AND** it MUST NOT persist only the intermediate recommendation response as the assistant's final answer.

#### Scenario: Terminal tool sequence is recorded for debugging
- **WHEN** a streaming run executes one or more terminal tools
- **THEN** debug logs MUST record the terminal tool sequence in execution order.

### Requirement: Bounded Total Agent Debug Diagnostics

Total Agent SHALL emit bounded debug summaries that make plan-state and tool-routing issues diagnosable without logging large payloads or secrets.

#### Scenario: Context load debug summary
- **WHEN** `load_total_context` completes
- **THEN** debug logs MUST include user id, syllabus id, session id when available, `plan_state_kind`, active plan id if present, pending recommendation id if present, candidate count if present, next task title if present, and warning count.

#### Scenario: Tool result debug summary
- **WHEN** any Total Agent tool returns
- **THEN** debug logs MUST include tool name, success, error code, status, and key ids relevant to the tool.
- **AND** debug logs MUST NOT include full recommendation graphs, full generated resource contents, API keys, or full unredacted prompts by default.

#### Scenario: Message history debug summary
- **WHEN** an LLM-driven Total Agent run starts
- **THEN** debug logs MUST include loaded message history length and current user/syllabus/session identifiers.

## Known Issues

### 🔴 agent_runtime.py 导入断裂
`agent_runtime.py` 导入 `tool_call_profile_agent` 和 `tool_call_recommendation_agent`，但这两个函数在 `agent_tools.py` 中不存在（旧名 `tool_note_profile_observation` / `tool_run_learning_recommendation` 未被重命名或别名）。导致 LLM 路径无法启动，`/api/total_agent/*` blueprint 注册失败（被 app.py 静默吞掉）。

### 🔴 旁路 1: profile_agent
`tool_note_profile_observation` 直调 `merge_profile_update + save_personal_profile`，未通过 `run_learning_profile_agent`。缺失 compute_features → assemble_profile 管线。

### 🔴 旁路 2: student_agent
`_record_step_status` 直调 `submit_learning_tree_changes`，未通过 `run_student_agent`。缺失 parent_candidate 解析、evidence 评分、RAG 融合。

### 🟡 旁路 3: recommendation_agent
`tool_run_learning_recommendation` 直调 `run_recommendation_route_from_payload`（确定性函数），未通过 `run_personal_recommendation_agent`。

### 🟡 其他
- 推荐结果 ~150KB 跨轮丢失，`load_total_context` 不 restore pending recommendation
- Study Buddy 事件 payload 极薄（0-2 字段）
- Streaming/SSE 尚未正式支持（`tool_status_events` 只是同步轨迹）

## Integration

Total Agent 是全局调度中枢，调用所有子模块：
- Learning Profile（`load_profile_summary`，只读）
- Personal Recommendation（`run_learning_recommendation`，读；`accept_learning_plan`，写）
- Resource Generation（`process_resource_generation_request`，写）
- Study Graph（`get_study_graph_features`，读；`submit_learning_tree_changes`，写）
- Study Buddy（`_select_buddy_event`，单向通知）
- Knowledge Search（`retrieve_learning_evidence`，只读）
