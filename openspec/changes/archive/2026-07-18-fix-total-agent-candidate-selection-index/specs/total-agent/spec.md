## ADDED Requirements

### Requirement: Candidate Selection Does Not Regenerate Proposed Paths
Total Agent SHALL accept an existing proposed recommendation candidate when the user selects or confirms a numbered candidate while the current plan state is `candidate_path`.

#### Scenario: User selects an existing candidate
- **WHEN** the current `load_total_context` result has `plan_state_kind: "candidate_path"`
- **AND** the user asks to choose, confirm, start, or accept candidate N from the visible recommendation list
- **THEN** Total Agent MUST call `accept_learning_plan` for the current pending recommendation
- **AND** Total Agent MUST NOT call `call_recommendation_agent` unless the user explicitly asks to discard the current candidates and generate a fresh recommendation.

#### Scenario: User asks for a fresh recommendation
- **WHEN** the current `load_total_context` result has `plan_state_kind: "candidate_path"`
- **AND** the user explicitly asks to regenerate, replace, refresh, or produce a new recommendation set
- **THEN** Total Agent MAY call `call_recommendation_agent`
- **AND** the new recommendation MUST become the current pending candidate set.

### Requirement: User-Facing Candidate Ordinals Are Normalized
Total Agent SHALL treat natural-language candidate numbers as one-based display ordinals and normalize them to the zero-based candidate index used by recommendation storage.

#### Scenario: User selects the third candidate
- **WHEN** the current pending recommendation has at least three candidates
- **AND** the user says "第三条路径", "第三个路径", "方案三", or an equivalent selection phrase
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
