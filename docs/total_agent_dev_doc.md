# Total Agent dev doc

本文档记录当前 `total_agent` 后端运行时的关闭状态。产品或论文中可以称为 Teacher Agent；代码、测试和 artifact 统一使用 `total_agent` 命名。

## 当前状态

Total Agent 后端核心链路已经完成，不包含 API/前端接入。当前已验证的主链路是：

```text
student message
  -> load_total_context
      -> read active learning_plan
      -> read persisted profile
      -> read study graph state
  -> infer_user_intent
  -> route by intent
  -> call task portals
  -> return TotalAgentResult + tool_trace + suggested_next_action
```

支持的 intent：

- `recommend_learning_path`
- `accept_recommendation`
- `generate_current_step_resource`
- `record_learning_feedback`
- `skip_current_step`
- `ask_goal_clarification`

正式入口：

```python
run_total_agent(payload, use_llm=False)
run_total_agent_agent(payload)
get_total_agent()
```

默认入口是 deterministic runtime；`use_llm=True` 或 `run_total_agent_agent` 才走 pydantic-ai tool-choice。

## 工具边界

Agent 工具定义在 `tasks/total_agent/agent_tools.py`：

```text
load_total_context
infer_user_intent
run_learning_recommendation
normalize_learning_goal_for_recommendation
accept_learning_plan
get_next_learning_task
generate_current_step_resource
record_learning_feedback
skip_current_step
```

Total Agent 不直接编造业务产物，只通过 task 门户调用子能力：

```text
learning_profile_task
  -> get_persisted_learning_profile
  -> get_or_build_learning_profile only when explicitly opted in

personal_recommendation_task
  -> run_recommendation_route_from_payload
  -> accept_recommendation_path
  -> get_active_learning_plan
  -> append / update learning_plan manifest

generative_task
  -> generate_resources_from_request

study_graph_task
  -> get_learning_tree_features
  -> submit_learning_tree_changes for feedback sync
```

## 关键行为

- 推荐成功后默认不自动采纳，返回 `wait_user_acceptance`。
- 只有用户明确确认或 payload 显式 `auto_accept=true` 时，才创建 active learning plan。
- 有 active plan 时，“继续学习”优先沿用当前 active step，不重新随机推荐。
- 没有语义证据时返回追问，不用任意 syllabus 节点强行推进。
- `load_total_context` 会读取 persisted profile 和 study graph state；读取失败只产生 warning，不阻断 active plan。
- Total Agent 不在 runtime 里伪造 mock profile、mock study graph 或 mock resource result。
- `profile_summary.profile_source` 用于审查画像来源：`persisted_profile`、`built_profile` 或 `none`。
- 真实画像字段保持 Profile Agent 原生风格，例如 `concept_gaps`、`bottleneck_topics`、`knowledge_mastery`、`resource_preference`。
- `normalize_profile_summary` 将真实画像归一为调度摘要：`weak_points`、`preferred_formats`、`risk_level`、`time_budget`。
- `build_current_step_resource_strategy` 根据 message、当前 step、profile 和 study graph 生成资源策略。
- 用户显式 `resource_types` 优先，不被 profile 偏好覆盖。
- 当前 step 命中画像或学习树弱点时，资源策略会倾向 `targeted`，并可扩展到 `documents + quiz + mindmap`。
- `record_learning_feedback` 先写 learning plan manifest，再推进 step，并尝试同步 study graph。
- study graph sync 失败不回滚 learning plan 事件，但必须记录 warning。
- 所有失败返回结构化 `error_code/error_message`。

## 资源生成

资源生成已经全量逐出 LiteLLM 内容生成路径。当前资源内容生成由资源 Agent 自己完成：

```text
Total Agent resource_strategy
  -> generative_task.generate_resources_from_request
  -> resource agent planning / retrieval / draft
  -> OpenAI-compatible pydantic-ai content Agent
  -> persist_generated_resource
```

不保留 LiteLLM fallback。RAG 增强也由资源 Agent 承担检索与编排，内容落盘由资源 Agent 完成。

当前全真实 E2E 已生成并校验：

```text
documents
quiz
mindmap
```

人工抽查结论：document 和 mindmap 质量可用；quiz 内容有效。已补充 quiz markdown 选项前缀清洗，避免模型输出 `A. xxx` 时渲染成 `A. A. xxx`。

## E2E 分层

默认单元和集成测试不访问真实 LLM/RAG/DB。Total Agent 当前保留三层验收：

```text
default deterministic
  -> fast regression for routing, context, strategy, feedback

e2e_amend
  -> deep student state fixture
  -> persisted profile + deep study graph + active plan
  -> no real LLM/RAG/DB by default

e2e_real_deep_state
  -> opt-in all real agents
  -> real Profile Agent
  -> real Total Agent
  -> real resource generation Agent
  -> real DB
  -> real study graph sync
```

深状态 fixture 固化在：

```text
tests/fixtures/total_agent/deep_student_state.json
```

该 fixture 只保存测试语料和场景定义，不提交运行后生成的 profile、learning plan、study graph 或 Total Agent result。运行产物写入 `tests/artifacts/`。

## 最近收口

全真实 deep-state E2E 已通过：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e_real_deep_state.py -m "llm and search and mysql" --capture=tee-sys -rs
```

最近一次记录：

```text
model: openai/qwen3.5-27b
result: 1 passed
user_id: 76
syllabus_id: 29
continue intent: generate_current_step_resource
feedback intent: record_learning_feedback
resource strategy: persisted_profile, documents/quiz/mindmap, targeted
learning plan: feedback 后推进到 HBase RowKey 设计
study graph: 12 nodes / 7 edges, feedback synced
```

关键 artifact：

```text
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/real_deep_state_all_agents_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/student_state_fixture_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/profiles/29-76.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/learning_plan/learning_plan/user_76/syllabus_29/manifest.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/manifest.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/change_log.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/documents/documents-20260604181856-f7ce0b/document.md
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/quiz/quiz-20260604182424-04ee82/quiz.md
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/mindmap/mindmap-20260604182520-1339b8/mindmap.mmd
```

## 测试命令

默认回归：

```bash
python -m pytest -q tests/test_total_agent_task.py
```

上下文策略前置样本：

```bash
python -m pytest -q tests/total_agent/test_context_strategy_contract.py
```

E2E amend 默认深状态：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e_amend.py -m "not llm and not mysql"
```

全真实 deep-state opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e_real_deep_state.py -m "llm and search and mysql" --capture=tee-sys -rs
```

## 文档保留建议

当前建议保留：

- `docs/E2E_amend_contract.md`：仍是深状态和全真实 E2E 的验收基线。
- `docs/total_agent_dev_doc.md`：当前关闭报告和事实口径。
- `tests/TEST_REPORT.md`：测试复现命令、结果和 artifact 索引。

可归档或后续删除：

- `docs/total_agent_small_plan.md`
- `docs/total_agent_contract.md`
- `tests/total_agent/small_plan.md`
- `tests/total_agent/contract.md`

这些文档主要记录实现前计划和测试侧前置契约。当前正式 runtime、E2E amend、全真实 deep-state opt-in 已经落地后，它们不再适合作为最新事实来源；如果删除，需要同时清理旧引用，避免新读者误以为仍应按早期阶段推进。

## 后续非阻塞项

- Profile Agent 的 `concept_gaps` 已增加短语化过滤；后续仍可继续提升知识点抽取质量。
- Quiz markdown 选项前缀重复已在 renderer 层修正。
- API/前端接入还未纳入本关闭报告。
- 真正的前端“进行中”状态需要单独设计 streaming 或 heartbeat 状态协议；当前 E2E 只提供终端 tee 输出和 artifact 中的 `tool_status_events` 样本。小计划见 `docs/agent_work_status_small_plan.md`。
