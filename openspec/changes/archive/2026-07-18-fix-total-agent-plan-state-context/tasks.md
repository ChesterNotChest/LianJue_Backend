## 1. Context State Contract

- [x] 1.1 Add a small helper in Total Agent tools to compute `plan_state_kind` from `active_plan` and `pending_recommendation`.
- [x] 1.2 Update `tool_load_total_context` to include `pending_recommendation` in the returned tool result as well as `state["total_context"]`.
- [x] 1.3 Update `tool_load_total_context` to include `plan_state_kind` in both returned tool result and `state["total_context"]`.
- [x] 1.4 Keep `pending_recommendation` compact and avoid returning full recommendation graphs from context loading.

## 2. Candidate Acceptance Routing

- [x] 2.1 Update Total Agent system prompt so current plan state must come from the current turn's `load_total_context`, not older `message_history` tool results.
- [x] 2.2 Update prompt/tool guidance so candidate confirmation with `plan_state_kind="candidate_path"` maps to `accept_learning_plan(candidate_index=...)`, not `call_recommendation_agent`.
- [x] 2.3 Review `tool_accept_learning_plan` snapshot fallback and add any missing candidate-index validation or debug output without changing recommendation ranking behavior.
- [x] 2.4 Add a current-turn guard for `get_next_learning_task` only if needed so it does not reuse stale in-memory plan state after context says no selected plan exists.

## 3. Streaming Persistence

- [x] 3.1 Inspect streaming runtime persistence path around terminal tools and final result construction.
- [x] 3.2 Stop persisting assistant ChatTurn from the first terminal tool result in a streaming run.
- [x] 3.3 Persist the assistant ChatTurn from the final TotalAgentResult after all tool calls complete.
- [x] 3.4 Preserve existing SSE `tool_start`, `tool_end`, and `final` event shapes.

## 4. Debug Diagnostics

- [x] 4.1 Add bounded context debug logging for `load_total_context`: user id, syllabus id, session id, `plan_state_kind`, active plan id, pending recommendation id, candidate count, next task title, warning count.
- [x] 4.2 Add bounded tool-result debug summaries for Total Agent tools: tool name, success, error code, status, key ids, candidate count, accepted plan id when applicable.
- [x] 4.3 Add run-start debug logging for loaded `message_history` length and current identifiers.
- [x] 4.4 Add terminal-tool sequence debug logging for each streaming run.
- [x] 4.5 Ensure debug logs do not include API keys, full prompts, full recommendation graphs, full generated content, or large resource bodies by default.

## 5. Regression Tests

- [x] 5.1 Add a unit test where no active plan exists but a proposed snapshot exists; assert `load_total_context` returns `plan_state_kind="candidate_path"` and top-level `pending_recommendation`.
- [x] 5.2 Add a unit test where no active plan and no snapshot exist; assert `plan_state_kind="no_path"` and empty plan fields.
- [x] 5.3 Add a unit test where an active plan exists; assert `plan_state_kind="selected_path"` and next task is present.
- [x] 5.4 Add a test for `accept_learning_plan` accepting candidate index 2 from snapshot fallback when transient `state["recommendation_result"]` is absent.
- [x] 5.5 Add a test that historical accepted-plan data does not override current `candidate_path` or `no_path` context in plan-state reporting.
- [x] 5.6 Add a focused streaming persistence test or integration-style test proving a run with recommendation then accept persists the final accepted-plan assistant turn, not the intermediate recommendation turn.

## 6. Verification

- [x] 6.1 Run focused Total Agent tests in the WSL/project Python environment.
- [x] 6.2 Run compile/static checks for touched Python files.
- [x] 6.3 Manually inspect `logs/chat_debug.log` after a candidate-selection run and confirm it shows current context, tool sequence, and final persisted state clearly.
- [x] 6.4 Verify `/api/total_agent/run` or `/api/total_agent/agent_run` still returns existing fields and only adds compatible fields.
