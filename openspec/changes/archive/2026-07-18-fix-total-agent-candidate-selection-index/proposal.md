## Why

Total Agent still mishandles candidate selection after recommendation generation. In the observed run, the user asked to choose the third candidate path, but the agent first regenerated recommendations and later passed `candidate_index=3`, which can select the fourth candidate under the current zero-based storage contract.

This matters because candidate acceptance is state-changing. A user-confirmed candidate set must not be silently replaced, and natural-language ordinal selection must not accept the wrong learning plan.

## What Changes

- Add deterministic candidate-selection normalization for Total Agent natural-language acceptance turns.
- Treat user-facing ordinals such as "第3条", "第三个路径", and "方案三" as one-based display numbers, then convert to the zero-based index used by recommendation storage.
- Prevent Total Agent from calling `call_recommendation_agent` when current context is `candidate_path` and the user intent is to select or confirm an existing candidate.
- Refresh Total Agent in-memory plan context after successful acceptance so later tools in the same run do not still see stale `candidate_path` state.
- Add focused regression tests for ordinal mapping, no-regeneration routing, and accept-then-next-task behavior.

No public API breaking change is intended. The recommendation snapshot and learning-plan storage APIs continue to use zero-based `candidate_index`.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `total-agent`: Strengthen candidate acceptance routing so natural-language candidate selection is deterministic, does not regenerate proposed candidates, and keeps current-turn state consistent after acceptance.

## Impact

- `tasks/total_agent/agent_runtime.py`
  - Tool wrapper semantics for LLM-driven candidate acceptance.
  - System prompt/tool guidance around candidate selection.
- `tasks/total_agent/agent_tools.py`
  - Candidate-index normalization for Total Agent tool calls.
  - State refresh after successful plan acceptance.
  - Optional bounded debug fields for raw vs normalized candidate index.
- Tests under the Total Agent test suite.
- No expected changes to recommendation ranking, graph construction, public recommendation accept endpoint semantics, or frontend button payload contract.
