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
STREAM_EVENT_TOOL_CALL = "tool_call"       # LLM 决定调某个工具（PartStartEvent.ToolCallPart）
STREAM_EVENT_TOOL_START = "tool_start"     # 工具开始执行（FunctionToolCallEvent）
STREAM_EVENT_TOOL_END = "tool_end"         # 工具执行完成（FunctionToolResultEvent）
STREAM_EVENT_TOOL_STATUS = "tool_status"   # 复用现有 tool_status_events 格式
STREAM_EVENT_FINAL = "final"               # 最终 TotalAgentResult

STREAM_EVENT_TYPES = {
    STREAM_EVENT_TEXT_DELTA,
    STREAM_EVENT_TEXT_START,
    STREAM_EVENT_TOOL_CALL,
    STREAM_EVENT_TOOL_START,
    STREAM_EVENT_TOOL_END,
    STREAM_EVENT_TOOL_STATUS,
    STREAM_EVENT_FINAL,
}
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
                │       ├─ PartStartEvent(TextPart)
                │       │    → yield {type: "text_start", data: {content: "..."}}
                │       ├─ PartStartEvent(ToolCallPart)
                │       │    → yield {type: "tool_call", data: {tool_name, tool_call_id, args}}
                │       ├─ PartDeltaEvent(TextPartDelta)
                │       │    → yield {type: "text_delta", data: {content_delta: "..."}}
                │       └─ FinalResultEvent → 记下但不产出（等 EndNode）
                │
                ├─ CallToolsNode (工具执行阶段)
                │   async with node.stream(run.ctx) as stream:
                │     async for event in stream:
                │       ├─ FunctionToolCallEvent
                │       │    → yield {type: "tool_start", data: {tool_name, args}}
                │       │    → (同时 emit_status_event 产出 tool_status running)
                │       └─ FunctionToolResultEvent
                │            → yield {type: "tool_end", data: {tool_name, result_summary}}
                │            → (同时 emit_status_event 产出 tool_status succeeded/failed)
                │
                └─ EndNode
                     → _build_agent_final_result(state, run.result.output)
                     → yield {type: "final", data: <TotalAgentResult dict>}
```

**关键内部逻辑**：

- `tool_status` 事件复用在 `_stream_total_agent_agent` 内部。函数构造一个内部 `status_callback`，挂到 `state["status_callback"]` 上，该 callback 在被 `emit_status_event` 调用时直接 yield 一个 `{type: "tool_status", data: event}`。工具层的 `emit_status_pair` / `_tool_result` 不需要任何改动。
- `TextPartDelta` 与 `ToolCallPart` 可能交叉出现（LLM 会先说后调、调完再说），事件按模型产出顺序 yield。
- `agent.iter()` 是 pydantic_ai 的异步迭代器，需 `async for` 消费。调用方用 `asyncio.run()` 或 async route 包裹。

### 3. 函数签名与内部逻辑

#### `async def _stream_total_agent_agent(payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]`

```
输入: payload = {user_id, syllabus_id, message, intent, context, resource_types, auto_accept, ...}
      （与现有 run_total_agent_agent 的 payload 完全一致）

逐事件 yield:
  {type: "text_delta" | "text_start" | "tool_call" | "tool_start" | "tool_end" | "tool_status" | "final",
   data: <事件相关数据>, timestamp: int}

最终事件:
  {type: "final", data: <TotalAgentResult 同现有 build_total_agent_result 返回结构>}
```

内部逻辑步骤：
1. 创建 `state` 字典（同现有逻辑）
2. 注册内部 `status_callback = lambda event: yield {type: "tool_status", data: event}`
3. `agent = get_total_agent()`
4. `async with agent.iter(user_prompt, deps=TotalAgentDeps(state=state)) as run:`
5. 遍历 nodes，分发到 `ModelRequestNode`、`CallToolsNode`、`EndNode` 处理
6. 所有 `PartStartEvent` / `PartDeltaEvent` 按类型映射为流式事件 yield

#### `def run_total_agent_agent(payload, *, stream=False)`

```
输入: payload: Dict, stream: bool = False

输出:
  stream=False → Dict（行为不变）
  stream=True  → AsyncGenerator（新增）

实现:
  if stream:
      return _stream_total_agent_agent(payload)
  # 原有逻辑
  result = agent.run_sync(...)
  return _build_agent_final_result(state, result.output)
```

### 4. 测试用例

**文件**: `tests/test_total_agent_agent_choice.py`（追加）

所有 LLM 测试标 `@pytest.mark.llm`，需 `RUN_LLM_TESTS=1`。

```python
@pytest.mark.llm
@pytest.mark.asyncio
async def test_stream_text_deltas_emitted():
    """流式模式下 LLM 至少产生一段自然语言 text_delta"""
    payload = {...}
    events = []
    async for event in run_total_agent_agent(payload, stream=True):
        events.append(event)
    text_deltas = [e for e in events if e["type"] == "text_delta"]
    assert len(text_deltas) > 0

@pytest.mark.llm
@pytest.mark.asyncio
async def test_stream_tool_events_paired():
    """每个 tool_start 都应有对应的 tool_end / tool_status"""
    payload = {...}
    events = []
    async for event in run_total_agent_agent(payload, stream=True):
        events.append(event)
    tool_starts = {e["data"]["tool_name"] for e in events if e["type"] == "tool_start"}
    tool_ends = {e["data"]["tool_name"] for e in events if e["type"] == "tool_end"}
    assert tool_starts == tool_ends

@pytest.mark.llm
def test_nonstream_backward_compatible():
    """stream=False 时行为与改造前一致"""
    result = run_total_agent(payload, use_llm=True, stream=False)
    assert "success" in result
    assert "tool_status_events" in result
    assert "intent" in result
```

---

## 阶段 2：门面透传

### 0. 常量定义

无新增。沿用阶段 1 的事件类型常量。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `tasks/total_agent_task.py` | `run_total_agent()` 和 `run_total_agent_agent()` 加 `stream` 参数透传 |

其他文件**不动**。

### 2. 函数级数据流

```
run_total_agent(payload, use_llm=True, stream=True)
  │
  ├─ stream=True & use_llm=True
  │    → return run_total_agent_agent(payload, stream=True)
  │       → return _stream_total_agent_agent(payload)   ← AsyncGenerator
  │
  ├─ stream=False & use_llm=True
  │    → return run_total_agent_agent(payload, stream=False)
  │       → run_sync, return dict（原行为）
  │
  └─ use_llm=False (stream 无视)
       → return deterministic_run_total_agent(payload)   ← dict（原行为）
```

调用方语义：

| 调用 | 返回 | 说明 |
|---|---|---|
| `run_total_agent(payload)` | `dict` | 默认路径：确定性执行 |
| `run_total_agent(payload, use_llm=True)` | `dict` | 同步 LLM，现有行为 |
| `run_total_agent(payload, use_llm=True, stream=True)` | `AsyncGenerator` | 流式 LLM，新增 |

### 3. 函数签名

#### `def run_total_agent(payload, *, use_llm=False, stream=False)`

```
输入:
  payload:   Dict     — 同现有
  use_llm:   bool     — 同现有，默认 False
  stream:    bool     — 新增，默认 False。仅 use_llm=True 时生效

输出:
  Dict 或 AsyncGenerator（同阶段 1 的 run_total_agent_agent）

实现:
  if use_llm:
      return run_total_agent_agent(payload, stream=stream)
  return deterministic_run_total_agent(payload)
```

#### `def run_total_agent_agent(payload, *, stream=False)`

```
输入:
  payload: Dict
  stream:  bool, 默认 False

输出:
  Dict 或 AsyncGenerator

实现:
  if stream:
      return _stream_total_agent_agent(payload)
  # 原有同步逻辑不变
  ...
```

### 4. 测试用例

```python
def test_run_total_agent_nonstream_default():
    """默认参数保持确定性执行"""
    result = run_total_agent(payload)
    assert isinstance(result, dict)

@pytest.mark.llm
def test_run_total_agent_llm_nonstream():
    """LLM 非流式返回 dict"""
    result = run_total_agent(payload, use_llm=True, stream=False)
    assert isinstance(result, dict)
    assert result["success"] is True

@pytest.mark.llm
@pytest.mark.asyncio
async def test_run_total_agent_llm_stream():
    """LLM 流式返回 AsyncGenerator"""
    gen = run_total_agent(payload, use_llm=True, stream=True)
    assert hasattr(gen, '__aiter__')
    events = [e async for e in gen]
    assert any(e["type"] == "final" for e in events)
```

---

## 阶段 3：SSE 端点

### 0. 常量定义

无新增。

### 1. 影响文件

| 文件 | 操作 |
|---|---|
| `blueprint/total_agent_api.py` | `/total_agent/agent_run` 支持 `stream=true` 时走 `text/event-stream` |
| `app.py` | **不改**（蓝图已注册，阶段 3 之前 agent-r 已做完） |

其他文件**不动**。

### 2. 函数级数据流

```
POST /api/total_agent/agent_run  {"stream": true, ...payload}
  │
  ├─ stream=false（默认）
  │    → total_agent_task.run_total_agent_agent(payload, stream=False)
  │    → return jsonify(dict), 200    ← 同现有
  │
  └─ stream=true
       → Response(stream_with_context(async_gen), mimetype="text/event-stream")
         │
         └─ 对每个 event:
              SSI: data: {json}\n\n
              │
              ├─ text_delta     → data: {"type":"text_delta","data":{"content_delta":"好"}}
              ├─ tool_start     → data: {"type":"tool_start","data":{"tool_name":"load_total_context"}}
              ├─ tool_end       → data: {"type":"tool_end","data":{"tool_name":"load_total_context"}}
              ├─ tool_status    → data: {"type":"tool_status","data":{"stage":"...","status":"running"}}
              └─ final          → data: {"type":"final","data":{...TotalAgentResult...}}
                                   + event: close\n\n
```

### 3. 函数签名与内部逻辑

#### 改造 `total_agent_agent_run_api()`

```
POST /api/total_agent/agent_run
输入 JSON:
  {
    "stream": true,           // 新增，可选，默认 false
    "use_llm": true,          // 已有
    "user_id": 1,
    "message": "...",
    ...  // 其余 payload 字段同前
  }

输出:
  stream=false → Content-Type: application/json, 状态码 200/500, JSON body
  stream=true  → Content-Type: text/event-stream, 状态码 200, SSE 流
```

内部逻辑（stream=true 分支）：

```python
@bp.route("/total_agent/agent_run", methods=["POST"])
def total_agent_agent_run_api():
    data = request.get_json(silent=True) or {}
    use_stream = _parse_bool(data.get("stream"), default=False)

    if not use_stream:
        # 原逻辑不变
        result = total_agent_task.run_total_agent_agent(data)
        return jsonify(result), 200

    # 流式分支
    async_gen = total_agent_task.run_total_agent_agent(data, stream=True)

    def generate():
        async def _consume():
            async for event in async_gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "event: close\ndata: {}\n\n"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            agen = _consume()
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

**关键内部逻辑**：

- Flask 是同步的，async generator 需要在同步函数内驱动。用 `asyncio.new_event_loop()` 在每条消息上 `run_until_complete`，避免全局 event loop 冲突。
- `stream_with_context` 确保 Flask 应用上下文在 generator 生命周期内可用。
- 前端通过 `EventSource` 消费：`new EventSource("/api/total_agent/agent_run")` POST 变体或 fetch + ReadableStream。

### 4. 测试用例

```python
@pytest.mark.llm
def test_agent_run_api_stream_sse_format(client):
    """SSE 响应格式正确：Content-Type 为 text/event-stream，数据行以 data: 开头"""
    payload = {
        "stream": True,
        "user_id": 1,
        "syllabus_id": 1,
        "message": "帮我生成学习资料",
    }
    response = client.post("/api/total_agent/agent_run", json=payload)
    assert response.content_type == "text/event-stream"
    body = response.get_data(as_text=True)
    lines = body.strip().split("\n")
    assert any(line.startswith("data: ") for line in lines)
    final_lines = [line for line in lines if '"type":"final"' in line]
    assert len(final_lines) >= 1

@pytest.mark.llm
def test_agent_run_api_nonstream_unchanged(client):
    """stream=false 时行为不改"""
    payload = {"user_id": 1, "message": "test"}
    response = client.post("/api/total_agent/agent_run", json=payload)
    assert response.content_type == "application/json"
    data = response.get_json()
    assert "success" in data
```

---

## 整体依赖关系

```
阶段 1（流式内核）
  └─→ 阶段 2（门面透传）
        └─→ 阶段 3（SSE 端点）
```

每阶段完成后可独立测试，不需要等后续阶段。
