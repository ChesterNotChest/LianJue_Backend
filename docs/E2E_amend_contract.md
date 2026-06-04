# Total Agent E2E amend contract

本文档用于收口 Total Agent 的 E2E 黑盒补充验收。E2E 的目标不是证明“多问几轮”，而是证明 Total Agent 在一个已经真实学习过一段时间的学生状态上，能够读取并利用深画像、学习进度记录树、学习计划和近期资源记录做决策。

总体原则：

- 默认 E2E amend 使用测试自产的深状态夹具，不访问真实 LLM/RAG/DB。
- 真实 Profile Agent / DB / RAG 只在 opt-in 测试中开启。
- mock 只允许存在于测试侧构造状态或隔离昂贵外部依赖；正式 `tasks/total_agent/` runtime 不伪造 profile、study graph 或资源生成结果。
- 每个 E2E 场景必须写 artifact；artifact 必须包含完整学生状态、Total Agent payload、tool trace、关键子产物和最终决策。
- 逆向工程场景必须强断言；正向工程预留场景只能 xfail 或写 diagnostic artifact，不伪装成已完成能力。

## 阶段 1：深学生状态夹具

本阶段构建后续所有 E2E 共用的学生状态。它不验证 Total Agent 决策，只验证状态本身足够深、足够真实、可复现。

### 0. 高标准状态前置

必须通过测试自产方式构建一个“已学习一段时间”的学生状态，不允许依赖历史脏数据。状态至少包含以下产物：

```text
test artifact root
  -> persisted learning_profile.json
  -> learning_plan manifest.jsonl
  -> study_graph manifest / nodes / edges / change_log
  -> current resource stub metadata
  -> first user question
  -> follow-up message list
  -> state_fixture_result.json
```

画像必须不是扁平偏好表，也不能凭空发明字段。它分为两层：

1. `profile_input_records`：E2E 自产的原始学习用例记录，格式必须符合 `learning_profile` 工具链真实输入，即 `dialogue_text`、`learning_records`、`answer_records`、`resource_usage`。
2. `persisted_profile`：必须由 `tasks.learning_profile.agent_tools._tool_normalize_events -> _tool_compute_features -> _tool_assemble_profile -> profile_storage.save_personal_profile` 生成并保存，或由真实 Profile Agent opt-in 生成。它的结构必须贴近现有真实产物，例如 `real_profile_to_total_agent_result.json` 中的 `built_profile/persisted_profile`，不把原始记录列表直接塞进 profile 本体。

`profile_input_records` 最小字段如下：

```json
{
  "dialogue_text": [
    "我想两周内掌握 HBase RowKey 设计。",
    "我做 RowKey 热点题时经常不知道怎么选前缀。",
    "我希望先看短文档，再做一点测验。"
  ],
  "learning_goal": "掌握 HBase RowKey 热点规避和预分区策略",
  "learning_records": [
    {
      "event_type": "study_session",
      "topic": "HBase 基础",
      "duration_minutes": 38,
      "status": "completed",
      "score": 0.72
    },
    {
      "event_type": "study_session",
      "topic": "HBase RowKey 设计",
      "duration_minutes": 45,
      "status": "partial",
      "score": 0.48
    }
  ],
  "answer_records": [
    {
      "question": "RowKey 如何避免写入热点？",
      "correct": false,
      "time_spent_seconds": 170,
      "meta": {"knowledge_points": ["RowKey 热点", "加盐前缀"]}
    },
    {
      "question": "HBase 表为什么按 RowKey 字典序维护？",
      "correct": true,
      "time_spent_seconds": 95,
      "meta": {"knowledge_points": ["HBase 数据模型"]}
    }
  ],
  "resource_usage": [
    {
      "resource_id": "documents-hbase-basics-001",
      "resource_type": "documents",
      "action": "complete",
      "duration_seconds": 900,
      "meta": {"knowledge_points": ["HBase 基础"]}
    },
    {
      "resource_id": "quiz-rowkey-hotspot-001",
      "resource_type": "quiz",
      "action": "submit",
      "score": 0.43,
      "meta": {"knowledge_points": ["RowKey 热点", "预分区"]}
    }
  ]
}
```

`persisted_profile` 必须保留真实画像产物风格。默认 fixture 版允许用 `_tool_assemble_profile` 生成后，在不破坏真实格式的前提下保存。最小可审查字段如下：

```json
{
  "user_id": 808,
  "syllabus_id": 2020,
  "learning_goal": "掌握 HBase RowKey 热点规避和预分区策略",
  "goal_clarity": {"level": "high", "score": 0.9},
  "term_familiarity": {"level": "low", "score": 0.12},
  "knowledge_mastery": {
    "overall_level": "weak",
    "overall_score": 0.0,
    "week_items": [],
    "weak_weeks": [],
    "mastered_weeks": [],
    "by_knowledge_point": {
      "RowKey 热点": 0.0,
      "预分区": 0.0
    },
    "knowledge_point_details": {
      "RowKey 热点": {
        "score": 0.0,
        "confidence": 0.43,
        "attempt_count": 2,
        "level": "low"
      }
    }
  },
  "concept_gaps": ["RowKey 热点", "预分区", "Region 划分"],
  "bottleneck_topics": ["RowKey 热点", "预分区"],
  "resource_preference": ["practice", "video"],
  "source_events": ["answer_records", "learning_records", "resource_usage"],
  "signals": {
    "learning_record_count": 5,
    "answer_record_count": 5,
    "resource_event_count": 5
  },
  "profile_schema_version": 1,
  "profile_saved": true,
  "profile_refreshed": false
}
```

Total Agent 的 `normalize_profile_summary` 必须能从真实 profile 风格中读取调度所需摘要：

```text
learning_goal -> profile_summary.learning_goal
weak_points / concept_gaps / bottleneck_topics / knowledge_mastery.knowledge_point_details(low) -> profile_summary.weak_points
preferred_formats / preferences.preferred_formats / resource_preference -> profile_summary.preferred_formats
risk_level / dropout_risk -> profile_summary.risk_level
time_budget / constraints.time_budget -> profile_summary.time_budget
```

也就是说，E2E 不应通过给 persisted profile 硬塞 `weak_points/preferred_formats` 来让策略变好；如果真实 profile 只给出 `concept_gaps/resource_preference`，正式 Total Agent 应完成归一化。

学习记录树必须不是 2-3 个节点的演示树，而是包含层级、边和多种学习状态。最小约束：

```json
{
  "node_count_min": 10,
  "edge_count_min": 6,
  "required_topics": [
    "大数据基础",
    "HDFS 基础",
    "HBase 基础",
    "HBase 数据模型",
    "HBase RowKey 设计",
    "Region 划分",
    "预分区",
    "RowKey 热点",
    "加盐前缀",
    "热点监控"
  ],
  "required_state_distribution": {
    "weak_topics": ["HBase 基础", "RowKey 热点", "预分区"],
    "mastered_topics": ["大数据基础", "HDFS 基础"],
    "recently_grown": ["HBase RowKey 设计", "RowKey 热点"],
    "stale_topics": ["MapReduce 基础"]
  },
  "required_edges": [
    ["HBase 基础", "HBase 数据模型"],
    ["HBase 数据模型", "HBase RowKey 设计"],
    ["HBase RowKey 设计", "Region 划分"],
    ["Region 划分", "预分区"],
    ["HBase RowKey 设计", "RowKey 热点"],
    ["RowKey 热点", "加盐前缀"]
  ]
}
```

学习计划必须来自推荐路径采纳，不允许直接拼字典后伪装成 active plan：

```json
{
  "source": "recommendation",
  "status": "active",
  "steps": [
    {"node_id": "hbase_intro", "title": "HBase 基础", "status": "active"},
    {"node_id": "rowkey_design", "title": "HBase RowKey 设计", "status": "pending"},
    {"node_id": "rowkey_hotspot", "title": "RowKey 热点规避", "status": "pending"}
  ]
}
```

资源与消息状态必须能模拟一个真实学生的上下文：

```json
{
  "current_resource": {
    "resource_id": "documents-hbase-basics-001",
    "resource_type": "documents",
    "topic": "HBase 基础",
    "status": "ready",
    "attached_step_id": "<active_step_id>"
  },
  "first_question": "我下一步应该怎么学习 HBase RowKey 热点规避？",
  "follow_up_messages": [
    "继续学习，给我一点练习",
    "我刚看完文档，但 RowKey 热点还是不懂",
    "帮我复习 HBase 基础和 Region 划分",
    "我学完了这份资料，测验得分 0.86",
    "这个 HBase 基础太简单了，跳过"
  ],
  "dialogue_history": [
    {"role": "student", "content": "我想两周内掌握 HBase RowKey 设计。"},
    {"role": "agent", "content": "建议先补 HBase 基础，再进入 RowKey 和热点规避。"}
  ]
}
```

### 1. 影响的文件范围

```text
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/e2e_amend/
tests/TEST_REPORT.md
docs/total_agent_dev_doc.md
```

必要时只允许微调：

```text
tasks/total_agent/agent_tools.py
tasks/total_agent_task.py
tasks/study_graph_task.py
tasks/learning_profile_task.py
```

### 2. 函数级收口的完整数据流

```text
build_total_agent_e2e_student_state(config)
  -> reset artifact root
  -> build profile_input_records
  -> run learning_profile toolchain without LLM
      -> normalize_events
      -> compute_features
      -> assemble_profile
      -> save_or_update_profile
  -> accept recommendation fixture through personal_recommendation_task
  -> submit deep study graph in multiple timestamped batches
      -> old stale nodes
      -> mastered foundation nodes
      -> active weak HBase node
      -> recent RowKey/Region/Hotspot branch
  -> read study graph features
  -> attach current resource stub metadata
  -> write state_fixture_result.json
  -> StudentE2EState
```

### 3. 精确到输入输出的函数级收口

`build_total_agent_e2e_student_state(config: dict) -> StudentE2EState`

输入：

```json
{
  "artifact_name": "profile_driven_continue",
  "profile_mode": "deep_fixture_persisted",
  "study_graph_mode": "deep_mixed_state",
  "plan_mode": "accepted_fixture_path",
  "resource_mode": "current_step_stub",
  "stale_current_step": false
}
```

输出：

```json
{
  "user_id": 808,
  "syllabus_id": 2020,
  "profile_input_records": {"learning_records": [], "answer_records": [], "resource_usage": []},
  "profile": {"profile_saved": true, "profile_schema_version": 1},
  "learning_plan": {"status": "active", "steps": []},
  "study_graph_state": {
    "weak_topics": [],
    "mastered_topics": [],
    "recently_grown": [],
    "stale_topics": []
  },
  "study_graph_tree": {"tree": {"nodes": [], "edges": []}},
  "current_resource": {},
  "messages": {},
  "artifact_root": "tests/artifacts/total_agent/e2e_amend/profile_driven_continue"
}
```

重要内部逻辑：

- profile 必须通过 `learning_profile` 工具链生成并保存，再通过 `learning_profile_task.get_persisted_learning_profile` 读回。
- artifact 必须同时保留 `profile_input_records` 和最终 `persisted_profile`，方便核查“输入记录 -> 画像产物”的对应关系。
- learning plan 必须通过 `personal_recommendation_task.accept_recommendation_path` 创建。
- study graph 必须通过 `study_graph_task.submit_learning_tree_changes` 写入，不直接写 manifest。
- study graph 必须分批写入，保证父节点先存在，子节点才能形成真实 parent edge。
- 构建完成后必须强断言：profile 记录数量、tree node/edge 数量、weak/mastered/recent/stale 分布、active plan、current resource、messages 均存在。

### 4. 测试用例的构建描述

- `test_e2e_state_fixture_builds_deep_student_state`
  - 默认不访问真实 LLM/RAG/DB。
  - 断言 `profile_input_records` 包含 learning/answer/resource 三类记录。
  - 断言 persisted profile 是真实画像产物风格，包含 `knowledge_mastery`、`concept_gaps`、`source_events`、`signals`。
  - 断言学习记录树满足 `node_count_min=10`、`edge_count_min=6`。
  - 断言 weak/mastered/recent/stale 四类状态均存在。
  - 写出 `student_state_fixture_result.json`。

- `test_e2e_state_fixture_real_profile_agent_optional`
  - opt-in：`RUN_LLM_TESTS=1 RUN_DB_TESTS=1`。
  - 用真实 Profile Agent 生成画像并持久化。
  - 该测试只证明真实 profile 可被保存读取，不替代深 fixture 默认场景。

## 阶段 2：Profile-driven continue 闭环

本阶段验证：Total Agent 在有 active plan 时不会重新推荐，而是读取深画像，把学生长期弱点和偏好用于当前 step 的资源策略。

### 0. 高标准状态前置

沿用阶段 1 深状态，其中必须满足：

```json
{
  "active_step": {"node_id": "hbase_intro", "title": "HBase 基础"},
  "profile": {
    "weak_points": ["HBase 基础", "RowKey 热点", "预分区"],
    "preferred_formats": ["documents", "quiz"],
    "answer_records_min": 4,
    "resource_usage_min": 4
  },
  "study_graph_state": {
    "weak_topics": ["HBase 基础"],
    "mastered_topics": ["大数据基础", "HDFS 基础"]
  },
  "message": "继续学习，给我一点练习"
}
```

### 1. 影响的文件范围

```text
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/e2e_amend/profile_driven_continue/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
StudentE2EState
  -> run_total_agent(payload)
      -> load_total_context
          -> read persisted profile
          -> read study graph features
      -> infer_user_intent=generate_current_step_resource
      -> get_next_learning_task
      -> generate_current_step_resource
          -> build_current_step_resource_strategy
  -> artifact
```

### 3. 精确到输入输出的函数级收口

输入：

```json
{
  "user_id": 808,
  "syllabus_id": 2020,
  "message": "继续学习，给我一点练习"
}
```

输出要点：

```json
{
  "success": true,
  "intent": "generate_current_step_resource",
  "result": {
    "context": {
      "profile_summary": {"profile_source": "persisted_profile"},
      "study_graph_state": {
        "weak_node_ids": ["HBase 基础"],
        "mastered_node_ids": ["大数据基础", "HDFS 基础"]
      }
    },
    "resource_generation": {
      "resource_strategy": {
        "resource_types": ["documents", "quiz"],
        "difficulty": "targeted",
        "strategy_signals": {
          "matched_profile_weak_point": true,
          "matched_study_graph_weak_node": true
        }
      }
    }
  }
}
```

重要内部逻辑：

- 必须走 history-driven current step，不重新调用推荐。
- profile 必须来自持久化读取，不来自 runtime mock。
- 资源生成可由测试侧 monkeypatch 隔离，但 resource request 必须保留 `resource_strategy`。

### 4. 测试用例的构建描述

- `test_total_agent_e2e_profile_driven_continue`
  - 断言 `profile_source=persisted_profile`。
  - 断言策略使用 `documents + quiz` 和 `targeted`。
  - 断言 artifact 中保留深 profile 和深 study graph。

## 阶段 3：Study graph weak / stale 闭环

本阶段验证：学习记录树不只是反馈同步目标，也能作为当前学习策略信号。

### 0. 高标准状态前置

构造两类深树状态：

```json
{
  "weak_current_step_case": {
    "current_step": "HBase 基础",
    "weak_topics": ["HBase 基础", "RowKey 热点", "预分区"],
    "stale_topics": ["MapReduce 基础"]
  },
  "stale_current_step_case": {
    "current_step": "HBase 基础",
    "weak_topics": ["HBase 基础", "RowKey 热点", "预分区"],
    "stale_topics": ["HBase 基础", "MapReduce 基础"]
  }
}
```

### 1. 影响的文件范围

```text
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/e2e_amend/study_graph_weak_continue/
tests/artifacts/total_agent/e2e_amend/study_graph_stale_review/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
StudentE2EState
  -> run_total_agent("继续学习" or "复习总结")
  -> load_total_context.study_graph_state
  -> build_current_step_resource_strategy
  -> artifact
```

### 3. 精确到输入输出的函数级收口

输入：

```json
{
  "message": "继续学习"
}
```

输出：

```json
{
  "resource_strategy": {
    "difficulty": "targeted",
    "strategy_signals": {"matched_study_graph_weak_node": true}
  }
}
```

复习输入：

```json
{
  "message": "继续学习，帮我复习总结一下"
}
```

复习输出：

```json
{
  "resource_strategy": {
    "resource_types": ["mindmap"],
    "difficulty": "review",
    "strategy_signals": {"message_requests_review": true}
  }
}
```

重要内部逻辑：

- weak/stale 信号只能影响资源策略，不自动推进 learning plan。
- 当前 step 仍以 active learning plan 为准。
- study graph 读取失败不应让 Total Agent 失败；但本阶段要求读取成功。

### 4. 测试用例的构建描述

- `test_total_agent_e2e_study_graph_weak_step_continue`
  - 深树当前 step 为 weak。
  - 断言 `matched_study_graph_weak_node=true`。

- `test_total_agent_e2e_study_graph_stale_step_review`
  - 深树当前 step 同时 stale。
  - 学生请求复习总结。
  - 断言 `mindmap + review`。

## 阶段 4：Feedback -> learning plan -> study graph 闭环

本阶段验证：学生完成当前资源后，Total Agent 能记录执行事实、推进 learning plan，并把学习事件同步到学习记录树。

### 0. 高标准状态前置

沿用阶段 1 深状态，并附加当前资源：

```json
{
  "active_step": {"node_id": "hbase_intro", "status": "active"},
  "current_resource": {
    "resource_id": "documents-hbase-basics-001",
    "resource_type": "documents",
    "topic": "HBase 基础",
    "status": "ready"
  },
  "feedback_payload": {
    "message": "我学完了这份资料",
    "status": "completed",
    "score": 0.86
  }
}
```

### 1. 影响的文件范围

```text
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/e2e_amend/feedback_updates_plan_and_graph/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
StudentE2EState
  -> run_total_agent(feedback payload)
      -> record_learning_feedback
      -> update learning_plan manifest
      -> sync study_graph from resource event
      -> get_next_learning_task
  -> read active plan
  -> read plan manifest
  -> read study graph
  -> artifact
```

### 3. 精确到输入输出的函数级收口

输入：

```json
{
  "message": "我学完了这份资料",
  "resource_id": "documents-hbase-basics-001",
  "status": "completed",
  "score": 0.86
}
```

输出：

```json
{
  "intent": "record_learning_feedback",
  "result": {
    "record_learning_feedback": {
      "updated_step": {"status": "completed"},
      "activated_step": {"status": "active"},
      "study_graph_sync": {"attempted": true}
    }
  }
}
```

重要内部逻辑：

- learning plan manifest 是执行事实，必须强断言有 `learning_event_recorded`。
- study graph sync 失败不能回滚 plan，但本阶段默认要求同步成功。
- artifact 必须包含反馈前学生状态、Total Agent 输出、反馈后 active plan、manifest entries、反馈后 study graph。

### 4. 测试用例的构建描述

- `test_total_agent_e2e_feedback_updates_plan_and_study_graph`
  - 断言当前 step completed。
  - 断言下一 step active。
  - 断言 study graph sync attempted/success。
  - 断言 manifest 有学习事件。

## 阶段 5：Clarification / no-force fallback 闭环

本阶段验证：Total Agent 在证据不足时不强行推进；有 active plan 时优先继续已有计划。

### 0. 高标准状态前置

两类状态：

```json
{
  "no_plan_case": {
    "profile": null,
    "study_graph": null,
    "message": "随便给我来一个"
  },
  "active_plan_case": {
    "deep_profile": true,
    "deep_study_graph": true,
    "active_plan": true,
    "message": "继续"
  }
}
```

### 1. 影响的文件范围

```text
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/e2e_amend/clarification_no_force/
tests/artifacts/total_agent/e2e_amend/continue_existing_plan_when_unclear/
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
payload
  -> run_total_agent
  -> infer_user_intent
  -> ask_goal_clarification or continue_existing_plan
  -> artifact
```

### 3. 精确到输入输出的函数级收口

无计划模糊输入：

```json
{"message": "随便给我来一个"}
```

输出：

```json
{
  "suggested_next_action": "ask_goal_clarification",
  "active_plan_after": null
}
```

有计划继续输入：

```json
{"message": "继续"}
```

输出：

```json
{
  "intent": "generate_current_step_resource",
  "result": {"next_task": {"node_id": "hbase_intro"}}
}
```

重要内部逻辑：

- 没有语义证据时不创建 learning plan。
- 没有用户确认时不 accept。
- 已有 active plan 且用户表达继续时，不能重新推荐或随机进入任意 syllabus 节点。

### 4. 测试用例的构建描述

- `test_total_agent_e2e_vague_goal_asks_clarification_without_plan`
  - 断言不创建 plan。

- `test_total_agent_e2e_continue_existing_plan_when_goal_unclear_but_plan_active`
  - 使用深状态。
  - 断言继续当前 step。

## 阶段 6：正向工程预留场景

本阶段只记录暂未完全具备的能力，不作为当前强验收。

### 0. 高标准状态前置

沿用阶段 1 深状态，并额外突出：

```json
{
  "time_budget_pressure": {"minutes_per_day": 15, "risk_level": "high"},
  "mastered_current_step": {"mastered_node_ids": ["HBase 基础"]},
  "wrong_answer_cluster": ["RowKey 热点", "预分区", "加盐前缀"]
}
```

### 1. 影响的文件范围

```text
docs/total_agent_small_plan.md
docs/total_agent_dev_doc.md
tests/total_agent/test_total_agent_e2e_amend.py
```

### 2. 函数级收口的完整数据流

```text
desired E2E scenario
  -> run_total_agent
  -> if current runtime cannot satisfy:
      -> xfail or diagnostic artifact
      -> follow-up implementation plan
```

### 3. 精确到输入输出的函数级收口

候选：

```json
{
  "message": "我最近很忙，帮我压缩计划",
  "expected_capability": "profile.time_budget drives plan/resource load reduction",
  "current_status": "planned"
}
```

```json
{
  "message": "我已经会 HBase 基础，直接学 RowKey",
  "expected_capability": "study_graph.mastered_node_ids can suggest skip/review",
  "current_status": "planned"
}
```

```json
{
  "message": "根据我最近错题重新规划路径",
  "expected_capability": "profile + study_graph + recommendation jointly drive reranking",
  "current_status": "planned"
}
```

重要内部逻辑：

- 不把 planned 能力写成强断言。
- 只有 runtime 具备对应行为后，才能把 xfail 转成强验收。

### 4. 测试用例的构建描述

- `test_total_agent_e2e_time_budget_reduces_resource_load`
- `test_total_agent_e2e_mastered_step_suggests_skip_or_review`
- `test_total_agent_e2e_wrong_answers_trigger_recommendation_retry`

以上初期可 xfail 或只写 diagnostic artifact。

## 阶段 7：全真实 opt-in 验收矩阵

本阶段把已有大型 E2E 纳入 Total Agent 收口，但不把它和默认 amend 场景合并。默认 amend 负责深学生状态；全真实 opt-in 负责证明真实 Agent / RAG / DB / 资源生成链路可用。

### 0. 高标准状态前置

全真实 opt-in 分三档执行，每档状态前置不同：

```json
{
  "profile_to_total_agent": {
    "profile_source": "real_profile_agent",
    "requires": ["RUN_LLM_TESTS=1"],
    "proves": "真实 Profile Agent 产物可以被 Total Agent 读取并进入 resource strategy",
    "does_not_prove": "真实资源生成质量和真实推荐/RAG 闭环"
  },
  "large_real_llm_rag_db": {
    "profile_source": "real_profile_agent",
    "recommendation_source": "real_personal_recommendation_agent_with_real_rag",
    "resource_source": "real_generative_agent",
    "study_graph_source": "real_study_graph_task",
    "db_source": "real_test_db_rows",
    "requires": ["RUN_LLM_TESTS=1", "RUN_REAL_RAG_TESTS=1", "RUN_DB_TESTS=1"],
    "proves": "真实 DB + Profile + Recommendation/RAG + Resource Generation + Study Graph 可以完成端到端闭环"
  },
  "deep_state_real_agents": {
    "profile_source": "real_profile_agent_from_deep_records",
    "study_graph_source": "deep_study_graph_task_batches",
    "recommendation_source": "accepted_plan_from_stable_fixture; real_recommendation_rag remains covered by large_real_llm_rag_db",
    "resource_source": "real_generative_agent",
    "requires": ["RUN_LLM_TESTS=1", "RUN_REAL_RAG_TESTS=1", "RUN_DB_TESTS=1"],
    "status": "implemented_opt_in",
    "proves": "深学生状态和全真实 Agents 在单一黑盒 E2E 中同时闭环"
  }
}
```

三档均有可运行入口。第三档不替代默认 amend，也不进入默认 CI；它用于发布前或阶段收口时证明深学生状态能在真实 Profile Agent、真实 Total Agent、真实资源生成 Agent、真实 DB 和真实 study graph sync 下闭环。

### 1. 影响的文件范围

```text
tests/test_total_agent_agent_choice.py
tests/total_agent/test_total_agent_e2e.py
tests/total_agent/test_total_agent_e2e_amend.py
tests/artifacts/total_agent/real_profile_to_total_agent/
tests/artifacts/total_agent/e2e/
tests/artifacts/total_agent/e2e_amend/
tests/TEST_REPORT.md
```

```text
tests/total_agent/test_total_agent_e2e_real_deep_state.py
tests/artifacts/total_agent/e2e_real_deep_state/
```

### 2. 函数级收口的完整数据流

现有窄集成 opt-in：

```text
real Profile Agent
  -> save persisted profile
  -> run_total_agent
      -> load_total_context reads persisted profile
      -> build_current_step_resource_strategy
  -> artifact
```

现有大型 opt-in：

```text
test DB user/syllabus/UserSyllabus
  -> learning_profile_task.get_or_build_learning_profile(refresh_profile=True)
  -> personal_recommendation_task.run_personal_recommendation_agent
      -> real LLM tool choice
      -> real RAG search when RUN_REAL_RAG_TESTS=1
      -> recommendation_result.best_path
  -> accept learning_plan
  -> generative_task.generate_resources_from_request
      -> real resource generation Agent
      -> real search/planning/generation/persistence
  -> record learning event
  -> study_graph_task.submit_learning_tree_changes
  -> artifact
```

深状态全真实 opt-in：

```text
deep profile input records
  -> real Profile Agent
  -> persisted profile
deep study graph batches
  -> study_graph_task.submit_learning_tree_changes
real DB user/syllabus
  -> run_total_agent over student messages
      -> read deep persisted profile
      -> read deep study graph
      -> real resource generation Agent
      -> feedback sync
  -> artifact
```

### 3. 精确到输入输出的函数级收口

`test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db`

输入侧要求：

```json
{
  "env": {
    "RUN_LLM_TESTS": "1",
    "RUN_REAL_RAG_TESTS": "1",
    "RUN_DB_TESTS": "1"
  },
  "question": "我下一步应该怎么学习 HBase RowKey 热点规避？",
  "learning_goal": "掌握 HBase RowKey 设计和热点规避",
  "graph_name": "RAG"
}
```

输出侧必须至少包含：

```json
{
  "summary": {
    "recommendation_flow": "natural_language_goal or graph_aligned_retry",
    "best_path": [],
    "generated_resource_type": "documents",
    "study_graph_created_nodes": [],
    "metrics_after_event": {}
  },
  "learning_profile": {},
  "recommendation_attempts": [],
  "resource_result": {},
  "event_result": {},
  "study_graph_result": {},
  "learning_plan_manifest_entries": []
}
```

`test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph`

输入侧要求：

```json
{
  "goals": ["rowkey_hotspot_avoidance"],
  "recommendation_graph": "aligned_hbase_graph",
  "resource_types": ["documents"]
}
```

输出侧必须至少断言：

```json
{
  "best_path_contains": "rowkey_*",
  "resource_result.success_count": 1,
  "generated_resource_type": "documents",
  "learning_event_recorded": true
}
```

重要内部逻辑：

- 全真实 opt-in 允许外部模型、RAG 和 DB 波动；artifact 必须保留失败原因、推荐尝试和 goal alignment 信息。
- 真实 RAG 推荐失败但有合法 clarification 时，不应伪造 `best_path`。
- 已有大型 E2E 侧重真实推荐/RAG链路，不要求构造 amend 级深状态。
- amend 默认 E2E 侧重深状态，不要求真实 LLM/RAG/DB。
- 深状态全真实 opt-in 同时要求“深状态”和“全真实 Agents”，但已有 active plan 时不强制重新触发推荐；真实推荐/RAG 仍由大型 E2E 覆盖。

### 4. 测试用例的构建描述

现有可运行：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_total_agent_agent_choice.py::test_total_agent_reads_real_profile_agent_output_for_resource_strategy -m llm
```

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" -rs
```

```bash
RUN_LLM_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e_amend.py::test_e2e_state_fixture_real_profile_agent_optional -m "llm and mysql"
```

- `test_total_agent_e2e_real_deep_state_all_agents`
  - 用真实 Profile Agent 消化深 `dialogue_text / learning_records / answer_records / resource_usage`。
  - 断言真实画像原生保留 `resource_preference / concept_gaps / knowledge_mastery`，不把资源生成枚举写回画像结构。
  - 断言 Total Agent 把 `resource_preference` 归一化为资源生成支持的 `documents / quiz / mindmap / coding_practice / ppt`。
  - 用真实 study graph task 构建深树。
  - 用真实 Total Agent 跑继续学习、资源生成和反馈。
  - 已有 active plan 时不重新推荐；真实推荐/RAG 由大型 E2E 继续覆盖。
  - 默认不进入 CI，仅作为发布前 opt-in。

运行命令：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e_real_deep_state.py -m "llm and search and mysql" -rs
```

## 推荐执行顺序

```text
1. 阶段 1：深学生状态夹具
2. 阶段 2：profile_driven_continue
3. 阶段 3：study_graph weak/stale continue
4. 阶段 4：feedback_updates_plan_and_study_graph
5. 阶段 5：clarification / no-force fallback
6. 阶段 6：正向工程预留
7. 阶段 7：全真实 opt-in 验收矩阵
```

通过标准：

- 默认 E2E amend 不访问真实 LLM/RAG/DB，但必须构建深 profile 和深 study graph。
- 深状态 artifact 必须能直接人工审查画像记录、树节点、树边、状态分布、学习计划和当前资源。
- Total Agent 输出 artifact 必须能看到 profile / study graph 如何进入 context 和 resource strategy。
- 旧大型 E2E 继续作为真实推荐 Agent/RAG/DB/资源生成闭环验收入口。
- 深状态全真实 opt-in 单独存在，不把默认 amend 改成慢测。
