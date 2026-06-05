# Total Agent next closure contract

本文档是 `docs/total_agent_next_closure_small_plan.md` 的函数级收口契约，用于指导下一轮 Total Agent 能力落地。

边界：

- 本文档不替代 `docs/total_agent_contract.md`，只定义下一轮闭环增量。
- 默认测试不得访问真实 LLM/RAG/DB。
- opt-in E2E 必须保留真实 Agent/RAG/DB 入口。
- 不新增专职 QA Agent 作为起步要求；优先通过 Total Agent intent + 工具闭环完成即时答疑。
- 资源生成 Agent 不按资源类型硬拆；个人资源库查询和复用判断从生成链路中拆出。

## 总体裁决

本轮先做“适度划分”：

```text
Total Agent
  -> 识别 intent
  -> 读取上下文
  -> 做策略决策
  -> 调用资源库查询 / RAG / 资源生成 / 学习树工具

ResourceLibraryTool
  -> 查询个人资源库
  -> 评分是否可复用
  -> 记录学生对资源的反馈

ResourceGenerationAgent
  -> 给定明确生成请求后，完成计划读取、材料检索、草稿、内容结构化、持久化

StudyGraphTool
  -> 学生个人学习树读写
  -> 课程/班级聚合摘要读取
```

不做：

- 不让 Resource Agent 自己决定“复用还是生成”。
- 不把全局 RAG 原文直接推荐给学生当资源。
- 不让班级全局弱点覆盖学生个人掌握度。
- 不把即时问答偷偷变成资源生成。

## 阶段 1：共享常量、枚举和结果结构

### 0. 新增的常量定义

建议新增或扩展：

```text
tasks/total_agent/agent_contracts.py
tasks/generative/resource_contracts.py
tasks/study_graph/contracts.py
```

Total Agent intent：

```python
INTENT_ANSWER_LEARNING_QUESTION = "answer_learning_question"
```

Total Agent tool：

```python
TOOL_RETRIEVE_LEARNING_EVIDENCE = "retrieve_learning_evidence"
TOOL_ANSWER_LEARNING_QUESTION = "answer_learning_question"
TOOL_FIND_PERSONAL_RESOURCES = "find_personal_resources"
TOOL_DECIDE_RESOURCE_REUSE = "decide_resource_reuse"
TOOL_APPLY_LEARNING_EFFECT_SIGNAL = "apply_learning_effect_signal"
TOOL_GET_COURSE_LEARNING_TREE_SUMMARY = "get_course_learning_tree_summary"
```

即时答疑深度：

```python
QA_LEVEL_FAST = "fast"                 # RAG + 当前上下文，默认
QA_LEVEL_CONTEXTUAL = "contextual"     # RAG + profile + active plan
QA_LEVEL_ASYNC_RESOURCE = "async_resource"  # 转资源生成/异步深加工
```

资源推荐模式：

```python
RESOURCE_RECOMMENDATION_REUSE_EXISTING = "reuse_existing"
RESOURCE_RECOMMENDATION_GENERATE_MISSING = "generate_missing"
RESOURCE_RECOMMENDATION_GENERATE_ALL = "generate_all"
```

资源质量状态：

```python
RESOURCE_QUALITY_USABLE = "usable"
RESOURCE_QUALITY_INVALID = "invalid"
RESOURCE_QUALITY_LOW_QUALITY = "low_quality"
RESOURCE_QUALITY_NEEDS_REVIEW = "needs_review"
```

资源新鲜度状态：

```python
RESOURCE_FRESHNESS_FRESH = "fresh"
RESOURCE_FRESHNESS_STALE = "stale"
RESOURCE_FRESHNESS_EXPIRED = "expired"
```

学生反馈状态：

```python
RESOURCE_FEEDBACK_UNKNOWN = "unknown"
RESOURCE_FEEDBACK_ACCEPTED = "accepted"
RESOURCE_FEEDBACK_DISLIKED = "disliked"
RESOURCE_FEEDBACK_REJECTED = "rejected"
```

全局学习树策略动作：

```python
GLOBAL_SIGNAL_REINFORCE_SHARED_WEAKNESS = "reinforce_shared_weakness"
GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE = "checkpoint_then_advance"
GLOBAL_SIGNAL_INDIVIDUAL_TARGETED_SUPPORT = "individual_targeted_support"
GLOBAL_SIGNAL_ADVANCE_OR_ENRICH = "advance_or_enrich"
```

资源复用拒绝原因：

```python
REUSE_REJECT_INVALID_RESOURCE = "invalid_resource"
REUSE_REJECT_EXPIRED_RESOURCE = "expired_resource"
REUSE_REJECT_STUDENT_REJECTED = "student_rejected"
REUSE_REJECT_REPEATED_FAILURE = "repeated_failure"
REUSE_REJECT_TOO_EASY = "too_easy"
REUSE_REJECT_TOO_HARD = "too_hard"
REUSE_REJECT_TOPIC_MISMATCH = "topic_mismatch"
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tasks/generative/resource_contracts.py
tasks/generative/resource_manifest.py       # 如不存在，可合并到 storage/persistence 模块
tasks/study_graph/contracts.py
tests/total_agent/test_total_agent_next_closure_contract.py
tests/TEST_REPORT.md
docs/total_agent_next_closure_contract.md
```

### 2. 函数级收口的完整数据流

```text
raw payload
  -> normalize_total_agent_payload
  -> load_total_context
  -> infer_user_intent
  -> route by intent
  -> intent-specific tool chain
  -> build stable TotalAgentResult
```

所有新增链路都必须回到统一结果结构：

```json
{
  "success": true,
  "schema_version": "total_agent.v1",
  "intent": "answer_learning_question",
  "tool_trace": [],
  "result": {},
  "suggested_next_action": "",
  "error_code": "",
  "error_message": ""
}
```

### 3. 精确到输入输出的函数级收口

`normalize_total_agent_payload(payload: dict) -> dict`

输入：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "message": "为什么 RowKey 会热点？",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "documents_xxx"
  }
}
```

输出：

```json
{
  "success": true,
  "user_id": 76,
  "syllabus_id": 29,
  "message": "为什么 RowKey 会热点？",
  "context": {},
  "warnings": []
}
```

内部逻辑：

- `user_id`、`syllabus_id` 必须是正整数。
- `message` 缺失时返回结构化错误。
- `context` 缺失时按空字典处理。
- 不在 normalize 阶段读取外部系统。

### 4. 测试用例的构建描述

新增默认测试：

```text
test_next_closure_contract_constants_are_unique
test_next_closure_payload_normalization_requires_user_and_syllabus
test_next_closure_result_shape_is_stable_for_new_intents
```

断言：

- intent/tool/action 枚举无重复值。
- 所有新增 intent 都能返回统一 `TotalAgentResult`。
- 默认测试不访问真实 LLM/RAG/DB。

## 阶段 2：即时答疑闭环

### 0. 新增的常量定义

复用阶段 1：

```python
INTENT_ANSWER_LEARNING_QUESTION
TOOL_RETRIEVE_LEARNING_EVIDENCE
TOOL_ANSWER_LEARNING_QUESTION
QA_LEVEL_FAST
QA_LEVEL_CONTEXTUAL
QA_LEVEL_ASYNC_RESOURCE
```

建议新增超时配置常量，不在工具内部写死：

```python
QA_FAST_TIMEOUT_SECONDS = 5
QA_CONTEXTUAL_TIMEOUT_SECONDS = 10
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tasks/total_agent_task.py
tests/total_agent/test_total_agent_answer_learning_question.py
tests/total_agent/test_total_agent_answer_learning_question_real.py
tests/artifacts/total_agent/next_closure/answer_learning_question/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
run_total_agent(payload)
  -> load_total_context
  -> infer_user_intent
  -> answer_learning_question route
  -> retrieve_learning_evidence
  -> answer_learning_question
  -> build answer result
```

`answer_learning_question` 不推进计划、不创建资源、不写学习反馈。

### 3. 精确到输入输出的函数级收口

`retrieve_learning_evidence(state: dict) -> dict`

输入来自 `state["payload"]` 和 `state["context"]`：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "message": "为什么 RowKey 会热点？",
  "qa_level": "fast",
  "context": {
    "active_plan_id": "plan_xxx",
    "current_resource_id": "documents_xxx"
  }
}
```

输出：

```json
{
  "tool": "retrieve_learning_evidence",
  "success": true,
  "qa_level": "fast",
  "evidence_summary": [
    {
      "title": "HBase RowKey 热点",
      "summary": "单调递增 RowKey 会让写入集中到少数 Region。",
      "source": "RAG",
      "score": 0.82
    }
  ],
  "context_used": {
    "profile": false,
    "active_plan": true,
    "study_graph": true,
    "rag": true
  },
  "warnings": [],
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- `fast`：只使用用户问题、当前 active context、压缩 study graph 摘要和单轮 RAG evidence。
- `contextual`：允许读取 profile summary 和 active plan，但不读取完整 profile 原文。
- `async_resource`：不在本函数生成资源，只返回建议切换到资源生成流程。
- RAG 只返回压缩摘要，不返回长原文。
- 无 evidence 时仍可回答，但必须带 `warnings=["no_rag_evidence"]`，并降低置信度。

`answer_learning_question(state: dict) -> dict`

输入：

```json
{
  "question": "为什么 RowKey 会热点？",
  "qa_level": "fast",
  "evidence_summary": [],
  "profile_summary": {},
  "active_plan": {},
  "study_graph_state": {}
}
```

输出：

```json
{
  "tool": "answer_learning_question",
  "success": true,
  "answer": {
    "text": "RowKey 热点通常来自连续写入集中落到同一段 key range...",
    "key_points": [
      "HBase 按 RowKey 字典序组织数据",
      "单调递增 RowKey 容易集中写入最后一个 Region",
      "加盐前缀、散列前缀和预分区可以打散写入"
    ],
    "confidence": 0.82
  },
  "evidence_summary": [],
  "suggested_next_action": "offer_practice_or_resource",
  "plan_mutation": false,
  "resource_generation": false,
  "error_code": "",
  "error_message": ""
}
```

深度裁决：

```text
Level 1 / fast
  -> 默认
  -> 单轮 RAG + 当前上下文
  -> 适合概念解释、错题解释、短比较

Level 2 / contextual
  -> 只在问题明显依赖个人学习状态时使用
  -> 增加 profile summary 和 active plan
  -> 仍同步返回

Level 3 / async_resource
  -> 需要长表格、成套练习、PPT、完整专题材料时使用
  -> 不在答疑链路内生成
  -> 返回 suggested_next_action = generate_current_step_resource
```

禁止逻辑：

- 不在即时答疑里调用 `generate_current_step_resource`。
- 不在即时答疑里推进 `learning_plan.current_step_index`。
- 不把全局 RAG 资料作为学生可见资源返回。

### 4. 测试用例的构建描述

默认测试：

```text
test_answer_learning_question_routes_to_answer_intent
test_answer_learning_question_uses_mock_evidence_and_does_not_mutate_plan
test_answer_learning_question_contextual_reads_profile_summary_only
test_answer_learning_question_async_resource_returns_generation_suggestion
test_answer_learning_question_no_evidence_returns_warning_not_failure
```

opt-in 测试：

```text
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 \
python -m pytest -q tests/total_agent/test_total_agent_answer_learning_question_real.py -m "llm and search" -rs
```

opt-in 断言：

- intent 是 `answer_learning_question`。
- result 包含 `answer.text` 和 `evidence_summary`。
- 不创建学习计划事件。
- 不生成资源目录。

## 阶段 3：个人资源库、复用判断与生成缺口

### 0. 新增的常量定义

复用阶段 1 的资源状态和推荐模式常量。

建议新增复用阈值：

```python
RESOURCE_REUSE_MIN_MATCH_SCORE = 0.72
RESOURCE_REUSE_REPEATED_FAILURE_THRESHOLD = 2
RESOURCE_REUSE_DEFAULT_MAX_AGE_DAYS = 30
```

### 1. 影响的文件范围

```text
tasks/generative_task.py
tasks/generative/resource_contracts.py
tasks/generative/resource_manifest.py
tasks/generative/storage.py
tasks/generative/renderers.py
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_runtime.py
tests/test_generative_resource_manifest.py
tests/total_agent/test_total_agent_resource_reuse.py
tests/artifacts/total_agent/next_closure/resource_reuse/
tests/TEST_REPORT.md
```

如果当前没有 `resource_manifest.py`，实现时可以先落在现有 generative storage/persistence 模块；契约层仍建议独立出 manifest 读写逻辑。

### 2. 函数级收口的完整数据流

```text
build_current_step_resource_strategy
  -> find_personal_resources
  -> decide_resource_reuse
  -> if enough usable matches:
       return existing resources
     else:
       generate_current_step_resource for missing types
  -> persist generated resources
  -> return resource recommendation result
```

资源库查询不是 ResourceGenerationAgent 内部工具，而是 Total Agent 策略阶段调用的查询工具。

### 3. 精确到输入输出的函数级收口

`find_personal_resources(payload: dict) -> dict`

输入：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "node_id": "hbase_intro",
  "knowledge_items": ["HBase 基础", "RowKey 热点"],
  "resource_types": ["documents", "quiz"],
  "max_age_days": 30
}
```

输出：

```json
{
  "success": true,
  "matches": [
    {
      "resource_id": "documents-xxx",
      "resource_type": "documents",
      "topic": "HBase 基础",
      "node_id": "hbase_intro",
      "knowledge_items": ["HBase 基础"],
      "quality_state": "usable",
      "freshness_state": "fresh",
      "student_feedback_state": "accepted",
      "failure_count": 0,
      "match_score": 0.86,
      "paths": {
        "json": "...",
        "markdown": "..."
      }
    }
  ],
  "missing_resource_types": ["quiz"],
  "warnings": [],
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：

- 只能查询 `user_id + syllabus_id` 范围内资源。
- 不返回其他学生资源。
- 不返回全局 RAG 原文。
- `match_score` 至少考虑 `resource_type`、`node_id`、`knowledge_items`、`topic`、新鲜度。
- 资源 manifest 缺失可用性字段时按保守规则处理：`student_feedback_state=unknown`、`quality_state=needs_review`。

`decide_resource_reuse(payload: dict) -> dict`

输入：

```json
{
  "requested_resource_types": ["documents", "quiz"],
  "matches": [],
  "learning_effect": {
    "recent_low_score": true,
    "weak_knowledge_items": ["RowKey 热点"],
    "current_need": "review"
  }
}
```

输出：

```json
{
  "success": true,
  "resource_recommendation_mode": "generate_missing",
  "reusable_resources": [
    {
      "resource_id": "documents-xxx",
      "resource_type": "documents",
      "reuse_reason_codes": ["fresh", "high_match", "accepted"]
    }
  ],
  "skipped_resources": [
    {
      "resource_id": "quiz-old",
      "resource_type": "quiz",
      "skip_reason_codes": ["repeated_failure"]
    }
  ],
  "missing_resource_types": ["quiz"],
  "warnings": []
}
```

复用裁决表：

```text
validation.valid = false
  -> 永不复用

quality_state = invalid
  -> 永不复用

quality_state = low_quality
  -> 默认不复用；只有人工 review 后改为 usable 才可复用

freshness_state = expired
  -> 永不复用

freshness_state = stale
  -> 不作为主推荐优先复用；可作为生成 evidence 或复习参考

student_feedback_state = rejected
  -> 永不复用

student_feedback.explicitly_rejected = true
  -> 永不复用

student_feedback_state = disliked 且 failure_count >= 1
  -> 不复用，生成替代资源

student_feedback.too_easy = true 且 current_need != foundation_review
  -> 不复用，生成更高难度资源

student_feedback.too_hard = true 且 current_need != challenge
  -> 不复用，生成更低门槛资源

match_score < RESOURCE_REUSE_MIN_MATCH_SCORE
  -> 不复用
```

学习效果冲突裁决：

- 低分不自动证明资源质量差；它先证明“当前学生对相关知识点未掌握”。
- 如果低分后学生明确表示资源无效、太难、太简单或不喜欢，才写入 `student_feedback_state` 或 `student_feedback`。
- 如果同一资源关联的低分/失败次数达到阈值，即使没有明确差评，也不再作为主推荐复用。
- 对低分场景，优先生成 targeted/review 资源，而不是复用原普通资源。

### 4. 测试用例的构建描述

默认测试：

```text
test_find_personal_resources_only_reads_same_user_and_syllabus
test_resource_reuse_reuses_fresh_accepted_high_match_resource
test_resource_reuse_skips_rejected_resource
test_resource_reuse_skips_invalid_or_expired_resource
test_resource_reuse_skips_disliked_resource_after_failure
test_resource_reuse_generates_missing_resource_types
test_resource_reuse_low_quiz_score_prefers_targeted_review_over_same_resource
```

不要求 opt-in 覆盖所有复用规则；复用规则以 deterministic 单元/默认 E2E 为主。

## 阶段 4：学习效果评估闭环

### 0. 新增的常量定义

建议新增：

```python
LEARNING_EFFECT_LOW_SCORE_THRESHOLD = 0.6
LEARNING_EFFECT_MASTERED_SCORE_THRESHOLD = 0.85
LEARNING_EFFECT_STRATEGY_STANDARD = "standard"
LEARNING_EFFECT_STRATEGY_TARGETED = "targeted"
LEARNING_EFFECT_STRATEGY_REVIEW = "review"
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_contracts.py
tasks/total_agent/agent_tools.py
tasks/learning_plan_task.py
tasks/study_graph_task.py
tasks/learning_profile_task.py
tasks/generative/resource_manifest.py
tests/total_agent/test_total_agent_learning_effect.py
tests/total_agent/test_total_agent_learning_effect_real.py
tests/artifacts/total_agent/next_closure/learning_effect/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
record_learning_feedback
  -> append learning_plan event
  -> update current step status
  -> sync study_graph weak/mastered/practiced signal
  -> apply_learning_effect_signal
  -> optionally update resource feedback manifest
  -> recompute next resource strategy
```

### 3. 精确到输入输出的函数级收口

`apply_learning_effect_signal(payload: dict) -> dict`

输入：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "plan_id": "plan_xxx",
  "step_id": "step_xxx",
  "resource_id": "quiz-xxx",
  "resource_type": "quiz",
  "score": 0.43,
  "status": "submitted",
  "wrong_knowledge_items": ["RowKey 热点", "预分区"],
  "student_feedback": {
    "too_hard": true,
    "explicitly_rejected": false
  }
}
```

输出：

```json
{
  "success": true,
  "learning_effect": {
    "mastery_signal": "struggled",
    "weak_knowledge_items": ["RowKey 热点", "预分区"],
    "mastered_knowledge_items": [],
    "resource_feedback_state": "disliked",
    "next_resource_strategy": "targeted"
  },
  "study_graph_changes": {
    "attempted": true,
    "success": true,
    "updated_nodes": []
  },
  "profile_signal": {
    "refresh_recommended": true,
    "reason_codes": ["low_score", "weak_knowledge_items"]
  },
  "warnings": []
}
```

内部逻辑：

- `score < LEARNING_EFFECT_LOW_SCORE_THRESHOLD`：产生 `struggled` 信号。
- `score >= LEARNING_EFFECT_MASTERED_SCORE_THRESHOLD`：产生 `mastered` 或 `practiced` 信号。
- 错题知识点优先写入 study graph weak nodes。
- 如果学生反馈 `too_hard=true`，资源不一定 low_quality；只说明当前学生不适合该难度。
- 如果学生反馈 `explicitly_rejected=true`，该资源后续不复用。
- profile 不一定同步重建完整画像；至少返回 `profile_signal.refresh_recommended` 或写入轻量弱点信号。
- 下一轮 resource strategy 必须能区分 `standard`、`targeted`、`review`。

### 4. 测试用例的构建描述

默认测试：

```text
test_learning_effect_low_quiz_score_updates_plan_and_study_graph
test_learning_effect_low_score_marks_next_strategy_targeted
test_learning_effect_explicit_resource_rejection_prevents_reuse
test_learning_effect_high_score_can_advance_or_master_step
test_learning_effect_profile_signal_contains_new_weak_points
```

opt-in 测试：

```text
RUN_LLM_TESTS=1 RUN_DB_TESTS=1 \
python -m pytest -q tests/total_agent/test_total_agent_learning_effect_real.py -m "llm and mysql" -rs
```

opt-in 断言：

- learning plan manifest 有 feedback event。
- study graph manifest/change_log 有对应更新。
- `next_resource_strategy` 不再是普通 `standard`。

## 阶段 5：课程/班级全局学习树摘要与策略仲裁

### 0. 新增的常量定义

复用阶段 1 的全局策略动作常量。

建议新增隐私阈值：

```python
COURSE_TREE_SUMMARY_DEFAULT_LIMIT = 20
COURSE_TREE_SUMMARY_MIN_GROUP_SIZE = 5
COURSE_TREE_NODE_MIN_SAMPLE_SIZE = 3
```

### 1. 影响的文件范围

```text
tasks/study_graph_task.py
tasks/study_graph/features.py
tasks/study_graph/storage.py
tasks/total_agent/agent_tools.py
tests/test_study_graph_course_summary.py
tests/total_agent/test_total_agent_global_signal_arbitration.py
tests/artifacts/total_agent/next_closure/course_summary/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
get_course_learning_tree_summary
  -> read course/class aggregate study graph features
  -> compress top weak/mastered/recent nodes
  -> redact student-level details
  -> return summary
  -> combine_global_and_personal_learning_signals
  -> produce strategy_signals
```

### 3. 精确到输入输出的函数级收口

`get_course_learning_tree_summary(payload: dict) -> dict`

输入：

```json
{
  "teacher_id": 3,
  "syllabus_id": 29,
  "class_id": "class_hbase_2026",
  "focus_user_id": 76,
  "limit": 20
}
```

输出：

```json
{
  "success": true,
  "summary": {
    "syllabus_id": 29,
    "class_id": "class_hbase_2026",
    "student_count": 42,
    "weak_nodes": [
      {
        "title": "RowKey 热点",
        "weak_student_count": 18,
        "average_mastery": 0.34,
        "common_wrong_points": ["单调递增 RowKey", "预分区边界"]
      }
    ],
    "mastered_nodes": [],
    "recently_active_nodes": [],
    "recommended_intervention": [
      "下一节课建议补 RowKey 热点和预分区案例。"
    ]
  },
  "privacy": {
    "aggregation": true,
    "student_ids_redacted": true,
    "min_group_size": 5
  },
  "warnings": []
}
```

内部逻辑：

- 学生侧 Total Agent 只能读取压缩摘要。
- 不返回其他学生 id、画像、完整个人树。
- 如果样本量低于隐私阈值，隐藏该节点或只返回 coarse summary。
- 全局摘要只能作为策略信号，不直接修改学生学习树。

`combine_global_and_personal_learning_signals(payload: dict) -> dict`

输入：

```json
{
  "personal_signal": {
    "knowledge_item": "RowKey 热点",
    "mastery_label": "weak",
    "mastery_score": 0.22
  },
  "course_signal": {
    "knowledge_item": "RowKey 热点",
    "is_class_weak": true,
    "average_mastery": 0.34
  }
}
```

输出：

```json
{
  "success": true,
  "strategy_signal": {
    "knowledge_item": "RowKey 热点",
    "matched_profile_weak_point": true,
    "matched_own_study_graph_weak_node": true,
    "matched_course_global_weak_node": true,
    "action": "reinforce_shared_weakness",
    "resource_strategy": "targeted"
  }
}
```

仲裁矩阵：

```text
个人弱 + 班级弱
  -> action = reinforce_shared_weakness
  -> 加强解释 + targeted quiz/review

个人强 + 班级弱
  -> action = checkpoint_then_advance
  -> 只给短 checkpoint 或可选复习，不强制重学

个人弱 + 班级强
  -> action = individual_targeted_support
  -> 个别化补救，必要时给教师侧提示

个人强 + 班级强
  -> action = advance_or_enrich
  -> 跳过重复基础练习，推进或拓展

个人信号未知 + 班级弱
  -> action = checkpoint_then_advance
  -> 先短测确认，不直接判定学生薄弱
```

优先级：

```text
明确个人掌握度 > 个人 profile 弱点 > 个人学习树弱点 > 班级全局弱点 > RAG 常识信号
```

### 4. 测试用例的构建描述

默认测试：

```text
test_course_learning_tree_summary_redacts_student_ids
test_course_learning_tree_summary_hides_small_sample_nodes
test_global_signal_personal_weak_class_weak_reinforces
test_global_signal_personal_strong_class_weak_checkpoint_only
test_global_signal_personal_weak_class_strong_individual_support
test_global_signal_personal_strong_class_strong_advances
```

opt-in 暂不强制；课程聚合可先用 deterministic fixture。

## 阶段 6：E2E 闭环矩阵

### 0. 新增的常量定义

不新增 runtime 常量。测试侧建议统一 artifact 根目录：

```python
TOTAL_AGENT_NEXT_CLOSURE_ARTIFACT_ROOT = "tests/artifacts/total_agent/next_closure"
```

### 1. 影响的文件范围

```text
tests/fixtures/total_agent/
tests/total_agent/test_total_agent_next_closure_e2e.py
tests/total_agent/test_total_agent_next_closure_real_e2e.py
tests/artifacts/total_agent/next_closure/
tests/TEST_REPORT.md
docs/total_agent_next_closure_contract.md
```

### 2. 函数级收口的完整数据流

默认 E2E：

```text
fixture student state
  -> deterministic/mock Agent adapters
  -> Total Agent tools
  -> persisted artifact
  -> assert stable contracts
```

opt-in E2E：

```text
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1
  -> real Profile Agent / Recommendation Agent / Resource Agent where applicable
  -> real RAG / DB where applicable
  -> persisted artifact
  -> assert contract-level behavior, not exact wording
```

统一入口裁决：

```text
tests/total_agent/test_total_agent_next_closure_e2e.py
  -> 默认 deterministic / fixture 场景统一入口

tests/total_agent/test_total_agent_next_closure_real_e2e.py
  -> opt-in 全真实场景统一入口
```

文件名可以沿用现有 E2E 文件，但调用入口和报告表述必须统一：

```text
允许：
  -> 沿用 tests/total_agent/test_total_agent_e2e.py 作为统一 opt-in 入口
  -> 沿用 tests/total_agent/test_total_agent_e2e_amend.py 作为默认 fixture 场景入口

不允许：
  -> 同时维护“大型端到端 opt-in”和“E2E amend opt-in”两套平行入口
  -> TEST_REPORT.md 继续推荐多条职责重叠的 opt-in 命令
  -> 只新增 next_closure case，而不评估旧 case 是否应删除
```

旧 E2E 职责迁移裁决：

```text
旧大型端到端 opt-in
  -> 职责是证明“真实 DB + 真实 Profile + 真实推荐/RAG + 真实资源生成 + study graph sync”的全链路可用性

E2E amend
  -> 职责是证明“深学生状态 + active plan + persisted profile + study graph weak/stale + feedback 推进”的 Total Agent 决策稳定性

统一 E2E
  -> 必须吸收两者的独有证明点
  -> 按场景 case 拆分
  -> 可以保留少量交集断言，但不能保留重复测试入口
  -> 新 case 覆盖旧 case 职责后，优先直接删除旧 case
```

统一入口的 case 命名必须表达场景，而不是表达旧目录来源；例如：

```text
test_real_first_learning_loop_from_goal_to_first_resource
test_real_deep_state_continue_and_feedback_loop
test_real_answer_learning_question_loop
test_real_learning_effect_low_score_loop
test_real_release_multiturn_loop
```

旧 case 去留评估表必须在实施 PR 中给出：

```text
旧 case 名称
  -> 原证明点
  -> 新 case 覆盖情况
  -> 处理动作：delete | merge_into_new_case | keep_with_reason
  -> 如果 keep，必须说明为什么不是重复入口
```

收口完成标准：

```text
1. TEST_REPORT.md 只推荐统一后的默认 E2E 命令和统一后的 opt-in E2E 命令。
2. 旧“大型端到端 opt-in”和“E2E amend opt-in”的重复命令不再作为推荐入口出现。
3. 全真实 opt-in 至少覆盖：
   -> 初次学习/推荐/采纳/资源生成
   -> deep-state continue/resource generation
   -> feedback/study graph sync
4. 默认 deterministic E2E 至少覆盖：
   -> no-force clarification
   -> profile-driven continue
   -> study graph weak/stale continue
   -> feedback 推进 plan + graph
5. 如果旧测试文件仍存在，只能作为统一入口承载场景；不能按旧分类继续扩张。
```

### 3. 精确到输入输出的函数级收口

三类必须补齐的闭环：

```text
初次学习闭环
  input: 自然语言目标
  output: profile + recommendation + accepted plan + first personal resource

即时答疑闭环
  input: 学生概念/题目问题
  output: answer + evidence_summary + no plan/resource mutation by default

学习效果评估闭环
  input: resource completion / quiz score / wrong points
  output: plan event + study graph update + profile signal + targeted/review next strategy
```

release 级多轮闭环：

```text
Turn 1: 学生表达自然语言目标
  -> build profile
  -> recommend path

Turn 2: 学生确认计划
  -> accept plan
  -> generate/reuse documents + quiz

Turn 3: 学生问“为什么 RowKey 会热点？”
  -> answer_learning_question

Turn 4: 学生完成 quiz，分数偏低
  -> record feedback
  -> update study graph/profile signal
  -> next strategy targeted/review

Turn 5: 学生要求总结
  -> generate/reuse mindmap or ppt
```

资源类型覆盖：

- 至少 5 种资源的格式正确性继续依赖已有 generative 集成测试。
- Total Agent E2E 只验证“推荐/生成/复用调度是否正确”，不重复深测每种 renderer。

### 4. 测试用例的构建描述

默认 E2E：

```text
test_next_closure_first_learning_loop_from_goal_to_first_resource
test_next_closure_answer_learning_question_fast_loop
test_next_closure_learning_effect_low_quiz_score_loop
test_next_closure_resource_reuse_uses_good_personal_resource
test_next_closure_resource_reuse_skips_bad_personal_resource
test_next_closure_global_signal_arbitration_loop
```

opt-in E2E：

```text
test_next_closure_real_first_learning_loop
test_next_closure_real_answer_learning_question
test_next_closure_real_learning_effect_loop
test_next_closure_real_release_multiturn_loop
```

推荐命令：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 \
python -m pytest -q tests/total_agent/test_total_agent_next_closure_real_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

测试断言原则：

- 断言 intent、tool_trace、结构化字段、artifact 路径、状态变化。
- 不断言模型自然语言精确文本。
- opt-in 允许外部波动，但不允许 fallback 静默伪造关键产物。
- 默认测试覆盖所有业务裁决表。

## 实施顺序

建议顺序：

```text
1. 阶段 1：常量/结构统一
2. 阶段 2：answer_learning_question + retrieve_learning_evidence
3. 阶段 3：find_personal_resources + decide_resource_reuse
4. 阶段 4：学习效果评估闭环
5. 阶段 5：全局学习树摘要与仲裁
6. 阶段 6：默认 E2E + opt-in E2E
```

阶段 2 和阶段 3 可以并行开发，但合并前必须确保：

- 即时答疑不会直接生成资源。
- 资源复用不会返回被拒绝、过期、无效或反复失败的资源。
- 全局学习树信号不会覆盖个人掌握度。
