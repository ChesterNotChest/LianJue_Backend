# 总 Agent 流式输出计划

## 目的

让总 Agent 在工具调用链中不再是"沉默执行"，而是将 LLM 在工具调用间隙自然产生的文本（如"我先查看你的学习计划……""当前这一步薄弱点是 RowKey 设计，为你生成针对性资料……"）实时透出。底层从 `run_sync` 切换到 `agent.iter()` 即可，pydantic_ai 原生支持。

---

## 1. 影响范围

| 文件 | 变更 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 改 | 核心变更：`run_total_agent_agent()` 加 `stream` 参数；新增 `_stream_total_agent_agent()` 异步生成器 |
| `tasks/total_agent_task.py` | 改 | `run_total_agent()`、`run_total_agent_agent()` 透传 `stream` |
| `blueprint/total_agent_api.py` | 改 | `/total_agent/agent_run` 端点支持 `stream=true` 时走 SSE |
| `tasks/total_agent/agent_tools.py` | 不改 | `tool_status_events` 和 `emit_status_event` 机制继续复用 |
| `tasks/common/status_events.py` | 不改 | 现有状态事件结构不变 |
| `config.py` / `agent_model.py` | 不改 | qwen-max via DashScope 已支持 streaming，无需配置变更 |

---

## 2. 数据流

### 非流式（现有，不变）

```
run_total_agent → run_total_agent_agent → agent.run_sync() → TotalAgentResult
                                                    └─ 中间 text delta 丢弃
```

### 流式（新增）

```
run_total_agent(stream=True) → _stream_total_agent_agent() → agent.iter()
                                                                  ├─ ModelRequestNode.stream()
                                                                  │   ├─ PartStartEvent(TextPart)     → yield {type: "text_start", ...}
                                                                  │   ├─ PartDeltaEvent(TextPartDelta) → yield {type: "text_delta", content: "..."}
                                                                  │   └─ PartStartEvent(ToolCallPart)  → yield {type: "tool_call", tool: "..."}
                                                                  ├─ CallToolsNode.stream()
                                                                  │   ├─ FunctionToolCallEvent        → yield {type: "tool_start", ...}
                                                                  │   └─ FunctionToolResultEvent      → yield {type: "tool_end", ...}
                                                                  └─ EndNode                         → yield {type: "final", result: {...}}
```

统一事件结构：

```python
StreamEvent = {
    "type": "text_delta" | "text_start" | "tool_call" | "tool_start" | "tool_end" | "tool_status" | "final",
    "data": Any,       # 事件数据
    "timestamp": int,  # UTC 秒
}
```

- `text_delta`：LLM 逐 token 输出的文本片段
- `tool_status`：沿用现有 `tool_status_events` 格式（从 `emit_status_event` 回调中产出）
- `final`：最终的 `TotalAgentResult`（与现有非流式返回一致）

---

## 3. 关键函数签名

### 新增：`async _stream_total_agent_agent(payload) -> AsyncGenerator[dict, None]`

```python
async def _stream_total_agent_agent(payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """流式运行总 agent，逐事件 yield。
    
    Yields:
        {"type": "text_delta", "data": {"content": "好的", ...}, "timestamp": 1234567890}
        {"type": "tool_start", "data": {"tool_name": "load_total_context"}, ...}
        {"type": "tool_status", "data": {"stage": "load_total_context", "status": "running"}, ...}
        {"type": "tool_end", "data": {"tool_name": "load_total_context", ...}, ...}
        {"type": "tool_status", "data": {"stage": "load_total_context", "status": "succeeded"}, ...}
        {"type": "final", "data": {<TotalAgentResult dict>}, ...}
    """
```

### 变更：`run_total_agent_agent(payload, *, stream=False)`

```python
def run_total_agent_agent(payload: Dict[str, Any], *, stream: bool = False):
    """运行 LLM 版总 agent。
    
    Args:
        payload: 总 agent 输入 payload
        stream: True 时返回 AsyncGenerator，False 时返回 dict（行为不变）
    
    Returns:
        dict（非流式） 或 AsyncGenerator[dict, None]（流式）
    """
```

### 变更：`run_total_agent(payload, *, use_llm=False, stream=False)`

透传参数，不变更现有调用方的行为。

---

## 4. 测试

### 4.1 单元/集成测试（pytest）

由于 streaming 本质依赖真实 LLM，采用 **opt-in 测试**（`RUN_LLM_TESTS=1`），放在现有 LLM 测试文件中：

**文件**: `tests/test_total_agent_agent_choice.py`

```python
@pytest.mark.llm
@pytest.mark.asyncio
async def test_total_agent_stream_text_deltas_emitted():
    """流式模式下应产出 text_delta 事件"""
    events = []
    async for event in run_total_agent_agent(payload, stream=True):
        events.append(event)
    text_events = [e for e in events if e["type"] == "text_delta"]
    assert len(text_events) > 0, "LLM should produce natural language between tool calls"

@pytest.mark.llm
@pytest.mark.asyncio
async def test_total_agent_stream_tool_events_complete():
    """流式模式下应产出完整的 tool_start/tool_end 配对"""
    ...

@pytest.mark.llm
@pytest.mark.asyncio
async def test_total_agent_stream_final_result_matches_nonstream():
    """流式和非流式最终结果语义一致（intent/suggested_next_action 相同）"""
    ...

@pytest.mark.llm
def test_total_agent_nonstream_unchanged():
    """非流式调用行为不变"""
    result = run_total_agent(payload, use_llm=True, stream=False)
    assert result["success"] is True
    assert "tool_status_events" in result
```

### 4.2 终端手动测试

```bash
# 在项目根目录，进 Python REPL
python -c "
import asyncio, json
from tasks.total_agent_task import run_total_agent_agent

async def main():
    payload = {
        'user_id': 1,
        'syllabus_id': 1,
        'message': '帮我生成 RowKey 设计的学习资料',
        'intent': 'generate_current_step_resource',
    }
    async for event in run_total_agent_agent(payload, stream=True):
        t = event['type']
        if t == 'text_delta':
            print(event['data']['content'], end='', flush=True)
        elif t == 'tool_start':
            print(f'\n[工具] {event[\"data\"][\"tool_name\"]}', flush=True)
        elif t == 'final':
            print(f'\n\n完成: intent={event[\"data\"].get(\"intent\")}')
        elif t == 'tool_status':
            icon = '✅' if event['data']['status'] == 'succeeded' else '❌'
            print(f'  {icon} {event[\"data\"][\"stage\"]}', flush=True)

asyncio.run(main())
"
```

---

## 5. 注意事项

- **异步桥接**：`run_total_agent_agent(stream=True)` 返回 async generator，在同步 Flask 路由中需用 `asyncio.run()` 收集或换 Quart/async 路由
- **SSE 端点**：后续 `blueprint/total_agent_api.py` 的 `/agent_run?stream=true` 需改为 async 路由并用 `text/event-stream` 响应
- **向后兼容**：`stream` 默认 `False`，所有现有调用方不受影响
- **status_callback**：流式模式下，现有 `emit_status_event` 的 callback 机制可作为 tool_status 事件的产出源，无需重写工具层
