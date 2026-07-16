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

message_history 最大保留 20 轮（`MESSAGE_HISTORY_MAX_TURNS = 20`）。

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
