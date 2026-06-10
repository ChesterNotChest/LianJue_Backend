# 总 Agent 流式输出 — 收口计划

本文档将 `stream_output_small_plan.md` 拆为 3 个阶段，每阶段独立可测、可合入。

---

## 阶段 1：流式运行内核

### 0. 常量定义

新增 `tasks/total_agent/agent_contracts.py`：

```python
# 流式事件类型
STREAM_EVENT_TEXT_DELTA = "text_delta"
STREAM_EVENT_TEXT_START = "text_start"
STREAM_EVENT_TOOL_CALL = "tool_call"
STREAM_EVENT_TOOL_START = "tool_start"
STREAM_EVENT_TOOL_END = "tool_end"
STREAM_EVENT_TOOL_STATUS = "tool_status"
STREAM_EVENT_FINAL = "final"

STREAM_EVENT_TYPES = {STREAM_EVENT_TEXT_DELTA, STREAM_EVENT_TEXT_START, STREAM_EVENT_TOOL_CALL, STREAM_EVENT_TOOL_START, STREAM_EVENT_TOOL_END, STREAM_EVENT_TOOL_STATUS, STREAM_EVENT_FINAL}
```

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tasks/total_agent/agent_contracts.py` | 新增流式事件常量 |
| `tasks/total_agent/agent_runtime.py` | 新增 `_stream_total_agent_agent()`；修改 `run_total_agent_agent()` |

其他文件**不动**。

### 2. 函数级数据流

```
run_total_agent_agent(payload, stream=True)
  │
  └─→ _stream_total_agent_agent(payload)   ← AsyncGenerator
        │
        ├─ 创建 state = {payload, tool_trace, tool_status_events, run_id, status_callback}
        ├─ agent = get_total_agent()
        │
        └─ async with agent.iter(user_prompt, deps=TotalAgentDeps(state=state)) as run:
              async for node in run:
                │
                ├─ ModelRequestNode (LLM 响应阶段)
                │   async with node.stream(run.ctx) as stream:
                │     async for event in stream:
                │       ├─ PartStartEvent(TextPart)        → yield text_start
                │       ├─ PartStartEvent(ToolCallPart)    → yield tool_call
                │       ├─ PartDeltaEvent(TextPartDelta)   → yield text_delta
                │       └─ FinalResultEvent                → 记下但不产出
                │
                ├─ CallToolsNode (工具执行阶段)
                │   async with node.stream(run.ctx) as stream:
                │     async for event in stream:
                │       ├─ FunctionToolCallEvent           → yield tool_start
                │       └─ FunctionToolResultEvent         → yield tool_end
                │   (emit_status_event → callback → queue → yield tool_status)
                │
                └─ EndNode
                     → _build_agent_final_result(state, run.result.output)
                     → yield {type: "final", data: <TotalAgentResult dict>}
```

**关键内部逻辑**：

- `tool_status` 事件：`_stream_total_agent_agent` 内部构造 `status_callback`，`emit_status_event` 调用时通过 `asyncio.Queue` 桥接为异步 `yield tool_status`。工具层的 `emit_status_pair` / `_tool_result` 不需要任何改动。
- `agent.iter()` 是 pydantic_ai 的异步 context manager + 异步迭代器，需 `async for` 消费。

### 3. 函数签名

#### `async def _stream_total_agent_agent(payload) -> AsyncGenerator[dict, None]`

逐事件 yield：`text_delta | text_start | tool_call | tool_start | tool_end | tool_status | final`。

#### `def run_total_agent_agent(payload, *, stream=False)`

`stream=False` → `dict`（行为不变）。`stream=True` → `AsyncGenerator`。

### 4. 验证

**Mock 管道测试**（无 LLM，CI 可用）：`test_total_agent_stream_pipeline_with_mock`

**向后兼容**：`test_total_agent_nonstream_unchanged`、`test_agent_run_api_nonstream_unchanged`

---

## 阶段 2：门面透传

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tasks/total_agent_task.py` | `run_total_agent()` 和 `run_total_agent_agent()` 加 `stream` 参数透传 |

### 2. 函数签名

#### `def run_total_agent(payload, *, use_llm=False, stream=False)`

`use_llm=True, stream=True` → `AsyncGenerator`。其他组合 → `dict`（行为不变）。

### 3. 验证

透传层由阶段 1 的 mock 管道测试 + 向后兼容测试间接覆盖。

---

## 阶段 3：SSE 端点

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `blueprint/total_agent_api.py` | `/total_agent/agent_run` + `/total_agent/run` 支持 `stream=true` 时走 `text/event-stream` |

其他文件**不动**。

### 2. 验证

- `test_agent_run_api_nonstream_unchanged`：无 LLM，端点不带 `stream` 时返回 `application/json`。
- SSE 流式效果通过 E2E（阶段 4）或浏览器 `EventSource` 手动验证。

---

## 阶段 4：E2E 接入

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tests/total_agent/e2e_cases_real_deep_state.py` | 新增内部 `_stream_run()` helper，3 处 `run_total_agent_agent` → `_stream_run` |

`_stream_run` 是测试内部函数，`asyncio.run()` 驱动 `run_total_agent_agent(payload, stream=True)`，逐事件打印到 stdout，返回最终 result dict。与生产代码零耦合。

### 2. 验证

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

---

## 整体依赖关系

```
阶段 1（流式内核）
  └─→ 阶段 2（门面透传）
        └─→ 阶段 3（SSE 端点）
              └─→ 阶段 4（E2E 接入，测试内部 _stream_run）
```
