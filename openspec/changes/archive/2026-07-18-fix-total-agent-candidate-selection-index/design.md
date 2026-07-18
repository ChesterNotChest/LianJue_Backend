## Context

The previous Total Agent state fix made `candidate_path` explicit and added snapshot fallback acceptance. The latest run shows two remaining issues in the LLM-driven path:

- A selection utterance such as "第三个路径" can be routed to `call_recommendation_agent`, replacing the candidate set the user intended to accept.
- A selection utterance such as "第三条路径" can be passed as `candidate_index=3`, while the storage layer interprets candidate indexes as zero-based.
- After `accept_learning_plan` succeeds, later tools in the same run can still see stale `plan_state_kind="candidate_path"` and return `no_active_plan` before a fresh context load.

The public recommendation accept endpoint and recommendation snapshot storage already use zero-based candidate indexes. That contract should remain stable for existing frontend code and tests.

## Goals / Non-Goals

**Goals:**

- Prevent Total Agent from regenerating recommendations when the current context has a proposed candidate set and the user is selecting one of those candidates.
- Normalize user-facing candidate ordinals deterministically in the Total Agent path.
- Keep state consistent after successful candidate acceptance within the same run.
- Add focused tests that exercise tool behavior without relying on prompt compliance.

**Non-Goals:**

- Do not change recommendation ranking or candidate generation.
- Do not change `/api/recommendations/<id>/accept` index semantics.
- Do not redesign the full LLM intent parser.
- Do not require frontend changes for this backend Agent bug.

## Decisions

### Decision 1: Preserve zero-based storage, normalize at Total Agent boundary

The recommendation snapshot and learning-plan code will continue to use zero-based `candidate_index`. Total Agent will accept a user-facing ordinal from LLM tool calls and convert it to zero-based before calling recommendation acceptance.

Rationale: changing storage/API semantics would risk breaking frontend button flows and existing tests. The ambiguity exists at the natural-language boundary, so the conversion belongs there.

### Decision 2: Prefer explicit display ordinal in the LLM tool schema

Expose an optional `display_candidate_number` argument on the LLM `accept_learning_plan` tool. If present, it is interpreted as one-based and converted to zero-based. Keep `candidate_index` for internal/backward compatibility, but guide the model to use `display_candidate_number` when the user speaks in natural-language ordinals.

Rationale: "candidate_index" invites the LLM to pass the visible number directly. A display-number parameter names the semantics directly and avoids relying on prompt-only arithmetic.

### Decision 3: Add deterministic fallback for obvious off-by-one LLM calls

When Total Agent is in `candidate_path` state and `candidate_index` is supplied from the LLM wrapper, normalize it as a display ordinal unless the wrapper explicitly marks it as already zero-based. This catches the current observed failure where the model sends `candidate_index=3` for "third path".

Rationale: prompt guidance alone already failed. The tool layer should be robust to common LLM ordinal mistakes.

### Decision 4: Block regenerate-on-select through prompt and deterministic guard

The system prompt will state that candidate selection in `candidate_path` must accept the pending snapshot and must not regenerate. A deterministic guard should also make the accept path easy: the tool can load the latest proposed snapshot and validate the normalized index without needing transient `state["recommendation_result"]`.

Rationale: the model can still choose tools incorrectly, but reducing ambiguity and validating state lowers recurrence. Full forced tool routing can be added later if needed.

### Decision 5: Refresh state after acceptance

After successful `accept_learning_plan`, update `state["total_context"]` to `selected_path`, clear the pending recommendation summary for current-run routing, and set `active_plan`/`next_task`.

Rationale: later tools in the same run should not see stale `candidate_path` and incorrectly skip `get_next_learning_task`.

## Risks / Trade-offs

- Natural language can mention both old and new candidate sets -> Use latest current context only; historical snapshots remain non-authoritative.
- Treating LLM `candidate_index` as display ordinal could affect an internal test that directly supplies zero-based values through the LLM wrapper -> Keep lower-level tool/API zero-based behavior available and add an explicit source marker for zero-based calls if needed.
- Prompt updates alone may not fully stop regeneration -> This change pairs prompt guidance with acceptance-path normalization; if regeneration still occurs, a stricter runtime gate can be added around `call_recommendation_agent`.
- Main OpenSpec `total-agent` spec is older and not yet synchronized with the previous delta -> Keep this delta narrowly focused so implementation can proceed without broad spec cleanup.

## Migration Plan

No database migration is required. Existing recommendation snapshots and learning plans remain valid.

Deployment can be rolled back by reverting Total Agent runtime/tool changes. Public API semantics remain unchanged, so rollback does not require frontend coordination.
