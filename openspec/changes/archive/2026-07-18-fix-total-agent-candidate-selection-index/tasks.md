## 1. Candidate Selection Routing

- [x] 1.1 Update the LLM `accept_learning_plan` tool wrapper to support a user-facing `display_candidate_number` parameter.
- [x] 1.2 Add deterministic normalization from one-based display number to zero-based `candidate_index` before calling lower-level acceptance.
- [x] 1.3 Update Total Agent prompt/tool guidance so selection phrases in `candidate_path` use `accept_learning_plan`, not `call_recommendation_agent`.

## 2. Acceptance State Consistency

- [x] 2.1 Refresh `state["total_context"]` after successful acceptance so current-run state becomes `selected_path`.
- [x] 2.2 Ensure `get_next_learning_task` no longer skips with stale `candidate_path` immediately after successful acceptance.
- [x] 2.3 Add bounded debug fields showing raw display number, raw candidate index, normalized candidate index, and source semantics.

## 3. Regression Tests

- [x] 3.1 Add a test that display candidate number 3 accepts zero-based candidate index 2 from snapshot fallback.
- [x] 3.2 Add a test that out-of-range display candidate numbers are rejected without accepting a different path.
- [x] 3.3 Add a test that accept followed by `get_next_learning_task` in the same state does not return `no_active_plan`.

## 4. Verification

- [x] 4.1 Run focused Total Agent tests in the WSL `lianjue` environment.
- [x] 4.2 Run compile/static checks for touched Python files.
- [x] 4.3 Inspect debug output or test assertions to confirm selection no longer regenerates proposed candidates for candidate-selection turns.
