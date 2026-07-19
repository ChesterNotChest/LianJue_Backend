## Why

Total Agent can confuse proposed recommendation candidates with an accepted active plan during multi-turn sessions. The observed 2026-07-18 19:34 debug run shows the agent loading history, regenerating recommendations, and only then accepting a plan even though the user asked to choose an existing candidate.

This matters because plan acceptance is a state-changing operation. The agent must distinguish candidate paths from selected paths using current authoritative tool state, not stale historical tool results or intermediate streaming text.

## What Changes

- Make the current plan state explicit to the LLM and API result as one of:
  - `selected_path`: an accepted active learning plan exists.
  - `candidate_path`: a proposed recommendation snapshot exists but has not been accepted.
  - `no_path`: neither an active plan nor a proposed recommendation exists.
- Expose `pending_recommendation` in the `load_total_context` tool result, not only in internal `state["total_context"]`.
- Require candidate acceptance turns to prefer `accept_learning_plan(candidate_index=...)` when a proposed snapshot exists, instead of calling the recommendation agent again.
- Add debug instrumentation for prompt/context diagnosis:
  - current user/syllabus/session ids,
  - loaded message history length,
  - current `active_plan` summary,
  - current `pending_recommendation` summary,
  - tool result summaries,
  - terminal tool progression within one streaming run.
- Correct streaming chat persistence so a turn that calls multiple terminal tools does not persist an intermediate recommendation response as the final assistant answer.
- Add focused regression tests for candidate-vs-selected state, snapshot fallback acceptance, and multi-terminal streaming persistence behavior.

No breaking API changes are intended. Existing fields remain; new fields are additive.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `total-agent`: Clarify and enforce Total Agent's plan-state contract across active plans, pending recommendation candidates, message history, and streaming persistence.

## Impact

- `tasks/total_agent/agent_tools.py`
  - `tool_load_total_context`
  - `tool_accept_learning_plan`
  - `tool_get_next_learning_task` if current-turn state guards are needed
- `tasks/total_agent/agent_runtime.py`
  - system prompt wording
  - message history usage guardrails
  - streaming terminal-tool chat persistence
  - debug logging helpers
- Tests under `tests/test_total_agent_task.py`, `tests/test_total_agent_agent_choice.py`, or a new focused total-agent test file.
- No changes expected in the recommendation ranking algorithm, learning plan lifecycle storage schema, study graph, resource generation, or Study Buddy behavior except clearer downstream events after correct acceptance.
