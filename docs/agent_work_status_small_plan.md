# Agent work status small plan

本文档为前端交互界面的 Agent 工作进度展示做后端准备。目标不是立即实现 streaming API，而是先收口现有子 Agent 能提供哪些状态、哪些状态只能在后续 runtime 改造后提供。

## 背景

当前大多数 Agent 调用是同步返回：

```text
request
  -> agent/tool chain runs
  -> final result + tool_trace + artifact
```

测试里已经可以通过 `--capture=tee-sys` 打印类似：

```text
profile agent: building deep profile
material agent: material generated
study graph: feedback synced to learning tree
```

但这仍是测试侧状态输出，不是生产 API 的实时状态协议。前端如果要展示 `calling profile agent... profile writing... material agent... material writing...`，后端需要把这些状态从临时 print / artifact 提升为结构化事件。

## 困难程度判断

先给结论：子 Agent 的工具调用是可以拿到的。当前 Profile Agent、Recommendation Agent、Resource Agent 都是 pydantic-ai `@agent.tool(sequential=True)` 显式工具链；Resource Agent 甚至已经在工具里维护 `tool_trace`。因此 `resource_agent.write_generation_draft.running`、`resource_agent.generate_resource_payload.running` 这类工具级阶段不是纯黑盒。

当前限制是：默认同步调用只能在工具跑完后拿到 `tool_trace`；如果要让前端在执行过程中看到 `running`，需要在工具 wrapper 开始和结束时发结构化事件。前端展示文案应由 `agent/stage/status` 或 `label_key` 映射，不依赖后端中文。

难度分三档：

```text
低：同步完成后展示阶段结果
  -> 直接复用 tool_trace / tool_status_events / artifact summary
  -> 不需要改 Agent runtime

中：请求执行中展示工具级 running/succeeded
  -> 在子 Agent tool wrapper 或 task portal 插入 status callback
  -> API 可用 SSE/WebSocket/polling 暴露
  -> 不要求模型 token 流式输出

高：展示 Agent 内部 tool calling 的实时细节
  -> 需要 pydantic-ai runtime 事件 hook 或统一 wrapper
  -> 要处理 retry、ModelRetry、工具失败、并发资源生成
  -> 需要稳定事件 schema 和前端容错
```

当前最合理的第一步是“中档”：在子 Agent 工具边界发阶段事件，不追求模型 token streaming。

## 当前可见性盘点

Profile Agent：

```text
runtime: tasks/learning_profile/agent_runtime.py
tool style: @agent.tool(sequential=True)
tools:
  load_existing_profile_context
  load_history_context
  load_personal_syllabus_context
  normalize_events
  compute_features
  assemble_profile
  save_or_update_profile
```

建议事件枚举：

```text
profile_agent.load_existing_profile_context
profile_agent.load_history_context
profile_agent.load_personal_syllabus_context
profile_agent.normalize_events
profile_agent.compute_features
profile_agent.assemble_profile
profile_agent.save_or_update_profile
```

Resource Agent：

```text
runtime: tasks/generative/resource_agent_runtime.py
tool style: @agent.tool(sequential=True)
trace: tasks/generative/resource_agent_tools.py 已维护 state["tool_trace"]
tools:
  read_generation_request
  read_generation_plan
  retrieve_generation_materials
  write_generation_draft
  generate_resource_payload
  persist_generated_resource
```

建议事件枚举：

```text
resource_agent.read_generation_request
resource_agent.read_generation_plan
resource_agent.retrieve_generation_materials
resource_agent.write_generation_draft
resource_agent.generate_resource_payload
resource_agent.persist_generated_resource
```

Recommendation Agent：

```text
runtime: tasks/personal_recommendation/agent_runtime.py
tool style: @agent.tool(sequential=True)
tools include graph/context loading, path search/ranking, final recommendation validation
```

建议事件枚举：

```text
recommendation_agent.load_graph
recommendation_agent.parse_goal
recommendation_agent.search_rag
recommendation_agent.rank_path
recommendation_agent.finalize_recommendation
```

Study Graph 当前更多是 task/service 同步写入，不是完整 pydantic-ai 工具链；但仍能在 task portal 层展示：

```text
study_graph.read_features
study_graph.submit_changes
study_graph.merge_nodes
study_graph.persist_tree
```

## 状态事件契约

建议新增统一事件结构：

```json
{
  "event_id": "evt_20260605_0001",
  "run_id": "total_agent_run_xxx",
  "agent": "profile_agent",
  "stage": "assemble_profile",
  "status": "running",
  "event_key": "profile_agent.assemble_profile.running",
  "label_key": "agent.profile.assemble_profile.running",
  "message": "",
  "timestamp": 1780640000,
  "payload": {
    "user_id": 76,
    "syllabus_id": 29
  }
}
```

字段约束：

- `agent`：稳定枚举，不用中文。
- `stage`：稳定枚举，用于前端 icon / stepper。
- `status`：`pending | running | succeeded | failed | skipped | warning`。
- `event_key`：`${agent}.${stage}.${status}`，便于日志、测试和前端直接匹配。
- `label_key`：前端 i18n / 文案映射 key。后端可以生成默认值，但前端不应依赖中文。
- `message`：debug / fallback 短文本，允许为空；不作为 UI 状态判断依据。
- `payload`：轻量摘要，不塞完整 profile、RAG 文本、资源正文。
- `run_id`：一次 Total Agent 请求内共享。

示例前端映射：

```json
{
  "agent.resource.write_generation_draft.running": "正在编写资源草稿",
  "agent.resource.generate_resource_payload.running": "正在构建资源内容",
  "agent.profile.save_or_update_profile.running": "正在写入画像"
}
```

测试只断言枚举和 key，不断言中文文案。

## 建议 Agent / Stage 枚举

Total Agent：

```text
total_agent.load_context
total_agent.infer_intent
total_agent.route_tool
total_agent.finalize
```

Profile Agent：

```text
profile_agent.load_context
profile_agent.normalize_events
profile_agent.compute_features
profile_agent.assemble_profile
profile_agent.persist_profile
```

Recommendation Agent：

```text
recommendation_agent.load_graph
recommendation_agent.search_rag
recommendation_agent.rank_path
recommendation_agent.persist_plan
```

Resource Agent：

```text
resource_agent.read_request
resource_agent.read_generation_plan
resource_agent.retrieve_generation_materials
resource_agent.write_generation_draft
resource_agent.generate_resource_payload
resource_agent.persist_generated_resource
```

Study Graph：

```text
study_graph.read_features
study_graph.submit_changes
study_graph.persist_tree
```

## 最小实现计划

### 阶段 1：同步事件收集器

新增轻量 helper：

```text
tasks/common/status_events.py
```

函数级收口：

```python
create_status_event(run_id, agent, stage, status, message="", payload=None) -> dict
append_status_event(state_or_payload, event) -> None
```

先只写入当前 state / result：

```json
{
  "tool_status_events": []
}
```

不改 API，不引入队列。

### 阶段 2：Total Agent 编排层接入

接入位置：

```text
tasks/total_agent/agent_runtime.py
tasks/total_agent/agent_tools.py
```

先覆盖：

```text
load_total_context running/succeeded
infer_user_intent running/succeeded
generate_current_step_resource running/succeeded/failed
record_learning_feedback running/succeeded/failed
```

输出要求：

```json
{
  "tool_trace": ["load_total_context", "..."],
  "tool_status_events": [
    {"agent": "total_agent", "stage": "load_context", "status": "succeeded"}
  ]
}
```

### 阶段 3：子 Agent task portal 接入

优先接入成本高、用户等待明显的链路：

```text
learning_profile_task
generative_task
personal_recommendation_task
study_graph_task
```

原则：

- Profile / Resource / Recommendation 这类 pydantic-ai 子 Agent，优先在 `@agent.tool` wrapper 发 `running/succeeded/failed`。
- Study Graph 这类 task/service 链路，先在 task portal 发 `running/succeeded/failed`。
- 资源生成多类型并行或串行时，每个 resource_type 发独立 stage。
- 失败必须发 `failed`，并保留 `error_code`。

最小代码形态：

```python
def emit_tool_status(state, agent, stage, status, message="", payload=None):
    event = create_status_event(
        run_id=state.get("run_id"),
        agent=agent,
        stage=stage,
        status=status,
        event_key=f"{agent}.{stage}.{status}",
        label_key=f"agent.{agent.replace('_agent', '')}.{stage}.{status}",
        message=message,
        payload=payload,
    )
    append_status_event(state, event)
    callback = state.get("status_callback")
    if callable(callback):
        callback(event)
```

工具 wrapper 形态：

```python
@agent.tool(sequential=True)
def write_generation_draft(ctx):
    emit_tool_status(ctx.deps.state, "resource_agent", "write_generation_draft", "running")
    try:
        result = tool_write_generation_draft(ctx.deps.state)
    except Exception:
        emit_tool_status(ctx.deps.state, "resource_agent", "write_generation_draft", "failed")
        raise
    emit_tool_status(ctx.deps.state, "resource_agent", "write_generation_draft", "succeeded")
    return result
```

这样同步测试仍可从 `state["tool_status_events"]` 拿完整历史；API 接入 SSE/polling 时，只需要把 `status_callback` 接到事件存储或推送层。

### 阶段 4：API 暴露方案

三种可选：

```text
polling
  -> 最容易接入
  -> request 返回 run_id
  -> 前端轮询 /agent-runs/{run_id}/events

SSE
  -> 适合单向状态流
  -> 前端实现简单
  -> 后端需要保持连接

WebSocket
  -> 适合复杂双向交互
  -> 当前阶段过重
```

建议第一版用 polling 或 SSE，不做 token streaming。

## 当前可立即复用的证据

已有 E2E artifact 中可以保留或扩展：

```text
tool_trace
tool_status_events
profile path
learning_plan manifest path
study_graph manifest/change_log path
resource json/md/mmd path
```

全真实 deep-state E2E 已能作为前端状态文案样本来源：

```text
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/real_deep_state_all_agents_result.json
```

这些 artifact 中的中文状态行只能作为展示样例；正式前端应以 `event_key` / `label_key` 映射为准。

## 风险和边界

- 不建议一开始做 token streaming；多数用户关心的是“哪个 Agent 在工作”，不是模型逐 token 输出。
- 不建议前端依赖自然语言 status 文案做状态判断；必须依赖 `agent/stage/status` 或 `event_key` 枚举。
- 不建议把完整 RAG 文本、profile 或资源正文塞进 status event；会放大 token/隐私/带宽成本。
- 模型内部多次 tool retry 是正常现象，前端应展示为同一 stage 的 retry count，而不是多个互相冲突的步骤。

## 推荐下一步

```text
1. 新增 status event helper。
2. Total Agent result 加 `tool_status_events` 稳定字段。
3. generative_task 和 learning_profile_task 先发 portal 级事件。
4. 在全真实 deep-state E2E 中强断言 status events 包含 profile/resource/feedback 三类。
5. API 阶段再决定 polling 还是 SSE。
```
