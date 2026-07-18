## Context

The observed debug conversation shows Total Agent mixing three different state sources:

- Current authoritative tool state from `load_total_context`.
- Historical PydanticAI `message_history`, including previous tool calls and tool results.
- Streaming ChatTurn persistence, which currently records the first terminal tool response in a run.

The specific 2026-07-18 19:34 run loaded `message_history` with 24 messages, then called `call_recommendation_agent`, then called `accept_learning_plan`. Logs show the final state mutation succeeded (`plan_20260718113454_23d0ad` accepted), but the intermediate recommendation tool was persisted as the assistant turn while the later accept tool was skipped as "already persisted".

Current code already stores `pending_recommendation` inside `state["total_context"]`, but the `load_total_context` tool result returned to the LLM omits that field. This makes the current authoritative state less visible than stale history.

## Goals / Non-Goals

**Goals:**

- Make the distinction between an accepted plan and proposed candidates explicit and testable.
- Let the LLM accept an existing proposed snapshot without regenerating recommendations.
- Prevent historical tool results from overriding the current turn's authoritative context.
- Add enough debug output to inspect prompt inputs, loaded history size, current context summaries, tool result summaries, and terminal-tool progression.
- Keep the fix narrowly scoped to Total Agent orchestration and diagnostics.

**Non-Goals:**

- Do not change recommendation ranking, candidate generation, graph construction, or learning-plan storage semantics.
- Do not change public endpoint shapes except additive fields.
- Do not introduce new external services or dependencies.
- Do not remove `message_history`; it remains useful for multi-turn intent continuity.

## Decisions

### Decision 1: Add an explicit plan-state discriminator

Add a small string field, tentatively `plan_state_kind`, computed by `load_total_context`:

- `selected_path` when `active_plan` is non-empty.
- `candidate_path` when no active plan exists but `pending_recommendation` is present.
- `no_path` when neither exists.

Expose this field both inside `state["total_context"]` and in the returned `load_total_context` tool result.

Alternative considered: infer the state from `active_plan` and `pending_recommendation` every time. That keeps the schema smaller but leaves the LLM to infer semantics from two fields, which is exactly where the current bug appears.

### Decision 2: Promote `pending_recommendation` into the tool result

`load_total_context` already builds `pending_recommendation`; return it in `_tool_result(...)` as a top-level field. Keep the payload summary small: `recommendation_id`, `candidate_count`, `best_path_titles`, `status`, and possibly `candidate_summaries` if already available from snapshot summaries.

Alternative considered: fetch full recommendation detail during context loading. That would increase token usage and risks reintroducing the ~150KB tool-result issue noted in existing docs.

### Decision 3: Treat current context as authoritative over historical tool results

Update the Total Agent system prompt to state that `message_history` tool results are historical evidence only. For current plan state, the LLM must rely on the current turn's `load_total_context` result.

This is a prompt-level safeguard, not the only defense. Tests should verify tool behavior independently from LLM phrasing.

### Decision 4: Prefer accept over regenerate when `candidate_path`

When the user confirms a numbered option and current context says `candidate_path`, the expected tool path is:

`load_total_context -> accept_learning_plan(candidate_index=N-1) -> get_next_learning_task`

The recommendation agent should only run when current context says `no_path`, or when the user explicitly requests a fresh recommendation.

This preserves existing user behavior while preventing accidental recomputation.

### Decision 5: Defer ChatTurn persistence until final output in streaming runs

The streaming path currently persists an assistant chat turn as soon as any terminal tool returns. This is unsafe for multi-tool runs where `call_recommendation_agent` can be followed by `accept_learning_plan`.

Change persistence behavior so streaming runs track terminal tool progression in state/debug logs but persist only the final assistant result after `_build_agent_final_result`. If immediate streaming UI text still needs to be shown, keep SSE events unchanged and only alter ChatTurn persistence.

Alternative considered: persist every terminal tool as separate assistant turns. That would make the chat history noisy and still confuse future `message_history`.

### Decision 6: Add bounded debug summaries

Add debug logs behind the existing chat debug mechanism or a dedicated environment flag. Log summaries, not full graphs or large resources:

- `run_id`, `session_id`, `user_id`, `syllabus_id`.
- `message_history_len`.
- user prompt character length and optional stable hash.
- `load_total_context` summary: `plan_state_kind`, `active_plan_id`, active status, next task title, pending recommendation id, candidate count.
- each tool end summary: tool name, success, error code, `_status`, important ids, candidate count, accepted plan id.
- terminal tool sequence for the run.

Do not log full `graph.nodes`, `graph.edges`, generated content, API keys, or full prompts by default.

## Risks / Trade-offs

- Prompt-only controls are not sufficient -> Pair prompt wording with structured fields and deterministic tests.
- Adding new tool result fields increases token usage slightly -> Keep pending recommendation summaries compact.
- Changing streaming ChatTurn persistence may affect UI timing -> SSE events remain unchanged; only durable chat history should change.
- If latest snapshot is stale but still `proposed`, accept fallback may select an old candidate -> Preserve existing snapshot status rules and add debug fields to reveal snapshot id and created time.
- Existing dirty worktree may include unrelated docs and frontend artifacts -> Implementation should touch only Total Agent code/tests unless explicitly extending docs.

## Migration Plan

No schema migration is required. The change is additive at the API/tool-result level.

Deployment can be rolled back by reverting Total Agent code changes. Existing chat sessions may still contain stale historical tool results, but the new current-context rule should reduce reliance on them immediately after deployment.

## Open Questions

- Should `pending_recommendation` include all candidate titles or only count and best path? The safer initial choice is count plus best path, with optional bounded summaries if already present.
- Should debug logging be always enabled in `logs/chat_debug.log`, or gated by an env var such as `TOTAL_AGENT_DEBUG_CONTEXT=1`? The safer default is bounded always-on summaries without full payloads.
