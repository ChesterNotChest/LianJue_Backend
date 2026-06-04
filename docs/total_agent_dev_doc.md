# Total Agent dev doc

本文档记录正式 `total_agent` 第一轮实现的关闭状态。产品或论文中可以称为 Teacher Agent，但代码、测试和 artifact 统一使用 `total_agent` 命名。

## 已完成范围

正式 runtime 已落在：

```text
tasks/total_agent/
tasks/total_agent_task.py
```

当前实现完成了最小多轮学习调度闭环：

```text
user message
  -> load_total_context
  -> infer_user_intent
  -> route by intent
  -> call task portals
  -> return TotalAgentResult
```

已支持的 intent：

- `recommend_learning_path`
- `accept_recommendation`
- `generate_current_step_resource`
- `record_learning_feedback`
- `skip_current_step`
- `ask_goal_clarification`

## 工具边界

Agent 可调用工具定义在 `tasks/total_agent/agent_tools.py`：

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

正式 task 门户定义在 `tasks/total_agent_task.py`：

```python
run_total_agent(payload, use_llm=False)
run_total_agent_agent(payload)
get_total_agent()
```

默认入口是 deterministic runtime；`use_llm=True` 或 `run_total_agent_agent` 才走 pydantic-ai tool-choice。

## 子能力调用

Total Agent 不直接编造业务产物，只通过 task 门户调用子能力：

```text
personal_recommendation_task
  -> run_recommendation_route_from_payload
  -> accept_recommendation_path
  -> get_active_learning_plan
  -> append_learning_plan_manifest_entry
  -> update_learning_plan_step_status

generative_task
  -> generate_resources_from_request

study_graph_task
  -> 通过 learning plan step completed 同步学习事实

profile context
  -> learning_profile_task.get_persisted_learning_profile
  -> learning_profile_task.get_or_build_learning_profile  # only when explicitly opted in
  -> load_profile_summary
  -> normalize_profile_summary

study graph context
  -> get_study_graph_features
  -> normalize_study_graph_state
```

Profile 读取当前通过 `learning_profile_task` 的 task 门户进入 Total Agent。默认只读已持久化画像；只有显式 `profile_read_action="build_if_missing"` 时才允许构建缺失画像。缺失或读取失败不会阻断 active plan、next task 或资源生成链路，也不会 fallback 到 mock profile。

## 关键行为

- 推荐成功后不会隐式采纳，返回 `wait_user_acceptance`。
- 只有用户明确确认或 `auto_accept=true` 时才创建 active learning plan。
- 有 active plan 时，“继续学习”优先使用当前 active/pending step。
- 资源生成默认围绕当前 step，不一次性生成全套资源。
- `load_total_context` 会返回 `profile_summary` 和归一化后的 `study_graph_state`。
- `profile_summary.profile_source` 会标记画像来源：`persisted_profile`、`built_profile` 或 `none`。
- `generate_current_step_resource` 会先构建 `resource_strategy`，再调用 `generative_task`。
- 资源生成请求会带上 `resource_types`、`knowledge_items`、`difficulty`、`strategy_reason` 和 `strategy_signals`。
- 用户显式传入的 `payload.resource_types` 优先级最高，不会被 profile 偏好覆盖。
- 当前 step 命中弱点时，默认资源策略会从轻量 `documents` 扩展到 `documents + quiz`。
- mock profile 只允许存在于测试 monkeypatch / fixture；正式链路读取失败时只返回空 summary + warning。
- mock resource result 也不进入正式 payload 分支；资源生成测试通过 monkeypatch `generate_resources_from_request` 完成。
- 反馈完成或跳过当前 step 后，会激活下一个 pending step。
- 学习反馈先写 learning plan manifest，再推进 step。
- completed step 会尝试同步 study graph；同步失败不回滚 learning plan 事件。
- 所有失败返回结构化 `error_code/error_message`。

## 测试结果

已跑通过：

```bash
wsl /home/chest/miniconda3/envs/lianjue/bin/python -m pytest -q tests/test_total_agent_task.py
```

结果：

```text
8 passed
```

当前结果：

```text
17 passed
```

已跑通过：

```bash
wsl /home/chest/miniconda3/envs/lianjue/bin/python -m pytest -q tests/test_total_agent_task.py tests/total_agent/test_process_contract.py
```

结果：

```text
13 passed
```

已跑通过：

```bash
wsl /home/chest/miniconda3/envs/lianjue/bin/python -m pytest -q tests/test_total_agent_task.py tests/total_agent/test_context_strategy_contract.py
```

结果：

```text
19 passed
```

已跑通过：

```bash
wsl /home/chest/miniconda3/envs/lianjue/bin/python -m pytest -q tests/test_total_agent_task.py tests/total_agent/test_context_strategy_contract.py tests/total_agent/test_process_contract.py
```

结果：

```text
24 passed
```

LLM tool-choice 默认未设置环境变量时正常跳过：

```bash
wsl /home/chest/miniconda3/envs/lianjue/bin/python -m pytest -q tests/test_total_agent_agent_choice.py -m llm -rs
```

结果：

```text
1 skipped
```

用户手动运行过：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_total_agent_agent_choice.py -m llm
```

产物位于：

```text
tests/artifacts/total_agent/agent_choice_continue/agent_choice_continue_result.json
```

## Artifact

正式默认测试和 opt-in 测试产物统一写入：

```text
tests/artifacts/total_agent/
```

不会写入 `tests/total_agent/`。

## 后续边界

Profile / Study Graph / Resource Strategy 的最小正式 runtime 已完成。测试侧契约继续保留为行为样本和回归基线：

```text
tests/total_agent/small_plan.md
tests/total_agent/contract.md
```
