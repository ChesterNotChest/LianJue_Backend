# 方案 A：接入 PydanticAI message_history — 全量影响评估

## 1. PydanticAI API 确认

PydanticAI 原生支持，代码已在使用 `pydantic-ai-slim[openai]`。

**当前调用：**
```python
# agent_runtime.py:1085
agent.iter(user_prompt, deps=deps)  # ← 无 message_history
```

**目标调用：**
```python
agent.iter(user_prompt, message_history=history, deps=deps)
```

**关键 API：**
- `agent.iter(prompt, message_history: list[ModelMessage], deps)` — 传入历史消息
- `run.result.new_messages()` → `list[ModelMessage]` — 仅本轮新消息（含 tool_call + tool_result）
- `run.result.all_messages()` → `list[ModelMessage]` — 全部历史（含传入的 message_history）
- 当 `message_history` 非空时，框架**不重新生成 system prompt** — 需要 `ReinjectSystemPrompt` capability

## 2. 当前数据流 vs 目标数据流

### 当前（文本记忆）
```
每轮 SSE 连接:
  1. _inject_chat_history(payload)
     → 从 ChatTurn 表加载 {role, content} 纯文本
     → 注入 payload['context']['conversation_history']
  2. state = {} (全新空状态)
  3. build_total_agent_user_prompt(state)
     → {"message": "确认，选路径3", "context": {"conversation_history": [...]}}
  4. agent.iter(user_prompt, deps=deps)  ← LLM 只看到文本历史
  5. 流式循环: text_start/delta, tool_call, tool_start, tool_end
  6. _persist_agent_chat_turn → ChatTurn 表存文本
  7. state 丢弃
```

### 目标（结构化记忆）
```
每轮 SSE 连接:
  1. history = load_message_history(session_id)
     → [ModelRequest(user), ModelResponse(agent+tool_calls), ModelRequest(tool_results), ...]
  2. state = {} (全新空状态，工具函数仍用它)
  3. agent.iter(user_prompt, message_history=history, deps=deps)
     ← LLM 看到完整历史：文本 + tool_call + tool_result
  4. 流式循环: 不变（SSE 格式不变）
  5. new_msgs = run.result.new_messages()
     history.extend(new_msgs)
     save_message_history(session_id, history)
  6. _persist_agent_chat_turn → ChatTurn 表存文本（保留，前端需要）
  7. state 丢弃
```

## 3. 影响文件清单

| 文件 | 改动级别 | 说明 |
|---|---|---|
| `agent_runtime.py` | 🔴 核心 | `_stream_total_agent_agent` 加 `message_history` 参数；循环后捕获 `new_messages()`；`get_total_agent()` 加 `ReinjectSystemPrompt` |
| `agent_runtime.py` | 🟡 简化 | `build_total_agent_user_prompt` 可去掉 `conversation_history` 注入；`_inject_chat_history` 可能冗余 |
| `agent_runtime.py` | 🟢 新增 | `_save_message_history()` / `_load_message_history()` — 序列化/反序列化 `list[ModelMessage]` |
| `schemas/agent_runtime_state.py` | 🟡 新增 | `ChatSession` 加 `message_history_json MEDIUMTEXT` 列；或新建文件存储 |
| `agent_contracts.py` | 🟢 新增 | 可能需 import `ModelMessage` 类型注解 |
| `agent_tools.py` | ⚪ 不改 | 工具函数操作 state，与 message_history 正交 |
| `total_agent_api.py` | ⚪ 不改 | SSE 端点签名不变 |
| `蓝图: learning_api.py` | ⚪ 不改 | 推荐/计划 API 不变 |
| 前端全部 | ⚪ 不改 | SSE 事件格式不变 |

## 4. 状态机变化

```
                    ┌──────────────┐
                    │  session_id  │
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │  load_message_history() │
              │  → list[ModelMessage]   │
              │  (含 tool_call+result)  │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  agent.iter(            │
              │    prompt,              │
              │    message_history=..., │  ← LLM 看到全部上下文
              │    deps=deps            │
              │  )                      │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  流式循环 (不变)         │
              │  text / tool_start /    │
              │  tool_end / tool_status │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  run.result             │
              │    .new_messages()      │  ← 本轮增量
              │  history.extend(new)    │
              │  save_message_history() │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  state 丢弃              │
              │  history 持久化在存储层  │
              └─────────────────────────┘
```

**关键洞察：state 和 message_history 分层**
- `state` — 工具函数的运行时工作区，仍然每轮重建
- `message_history` — LLM 的对话记忆，包含完整 tool_call+tool_result，跨轮持久化
- 两者**互不替代**。state 是给代码用的，message_history 是给 LLM 用的

## 5. 关键设计决策

### 5.1 存储格式
`ModelMessage` 是 Pydantic 模型，支持 `.model_dump(mode='json')` 序列化。
```python
# 序列化
raw = [m.model_dump(mode='json') for m in history]
json.dumps(raw)

# 反序列化
from pydantic_ai.messages import ModelMessage
raw = json.loads(data)
history = [ModelMessage.model_validate(m) for m in raw]
```

⚠️ `ModelMessage` 是抽象基类，`model_validate` 会自动解析到正确的子类（`ModelRequest`/`ModelResponse`）。需验证此行为是否稳定。

### 5.2 存储位置
| 方案 | 优点 | 缺点 |
|---|---|---|
| DB: `ChatSession.message_history_json MEDIUMTEXT` | 事务安全、已有 session 表 | schema migration，最大 16MB |
| File: `{session_id}_messages.json` | 无 schema 变更，与现有 chat history 同目录 | 无事务、并发风险 |

建议：**DB + file fallback**，与现有 `ChatTurn` 存储模式一致。

### 5.3 System Prompt 管理
`message_history` 非空时 PydanticAI 不生成 system prompt。

解决：在 `get_total_agent()` 注册 `ReinjectSystemPrompt` capability，或在 history 开头手动插入 system prompt 的 `ModelRequest`。

### 5.4 历史截断
完整 tool result（推荐图可达 150KB）存全量会爆炸。

策略：
- 存储层：**存全量**（不做截断，保证数据完整）
- 送 LLM 前：**PydanticAI 框架自动管理 token 窗口**（超过上下文长度时自动截断早期消息）
- 额外保护：保留最近 20 轮，超出部分 summarize 或丢弃

### 5.5 并发安全
同一 session 两个 SSE 连接 → history 并发写冲突。

解决：session 级别的写锁，或乐观锁（版本号）。

## 6. 简化项

接入后以下代码可简化或删除：

| 当前代码 | 变化 |
|---|---|
| `_inject_chat_history(payload)` | 可能简化或删除——LLM 从 message_history 获取对话 |
| `build_total_agent_user_prompt` 中的 `context.conversation_history` | 可移除——LLM 不需要文本历史了 |
| `payload['context']` 整体 | 可精简——只需 user_id, syllabus_id, message |
| `load_total_context` 工具调用频率 | 预期降低——plan 状态在 history 中可见 |
| `infer_user_intent` 工具调用频率 | 预期降低——用户意图在 history 中可追溯 |

## 7. 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Token 爆炸（大 tool result） | 高 | 上下文超限 | 存储全量 + 框架自动截断 + 20 轮限制 |
| System prompt 丢失 | 中 | Agent 行为异常 | ReinjectSystemPrompt capability |
| Tool schema 变更后历史不兼容 | 低 | LLM 混乱 | 版本标记 + 旧历史清理 |
| 并发写历史 | 低 | 消息丢失 | 写锁或乐观锁 |
| ModelMessage 序列化格式变化 | 低 | 历史加载失败 | try-except + 降级到空历史 |
| 首次迁移：现有 session 无历史 | 确定 | 首轮降级 | 自动检测空历史 → 不传 message_history |

## 8. 不改的部分（确认）

- ✅ 前端 SSE 事件格式 — text_start/delta, tool_call/start/end/status, final 完全不变
- ✅ 前端 AgentStore — ToolCall、ToolStatusEvent 解析逻辑不变
- ✅ 后端 tool 函数 — `tool_accept_learning_plan` 等完全不变
- ✅ ChatTurn 表 — 继续存文本消息供前端显示
- ✅ Snapshot / LearningPlan 持久化 — 不变，state machine 不变

## 9. 实施步骤（预估）

```
Phase 1: 存储层
  - Schema: ChatSession.message_history_json
  - save_message_history / load_message_history 函数
  - 序列化/反序列化 + 异常降级

Phase 2: Agent 接入
  - _stream_total_agent_agent 加 message_history 参数
  - 循环后 capture new_messages() + save
  - get_total_agent 加 ReinjectSystemPrompt

Phase 3: 简化
  - build_total_agent_user_prompt 去 conversation_history
  - _inject_chat_history 评估是否可删

Phase 4: 验证
  - smoke test: 多轮对话，确认 tool result 跨轮可见
  - token 监控: 确认历史不爆炸
  - 降级测试: 损坏 history → 空历史启动
```
