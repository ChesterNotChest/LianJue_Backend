## ADDED Requirements

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

### Requirement: Historical Tool Results Are Not Current State

Total Agent SHALL treat `message_history` tool results as historical context and SHALL use the current turn's `load_total_context` result as the authority for current plan state.

#### Scenario: Historical accepted plan was later abandoned
- **WHEN** `message_history` contains an older `accept_learning_plan` or `get_next_learning_task` result
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
