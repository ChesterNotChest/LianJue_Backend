# Total Agent message_history 接入 Contract

收口 PydanticAI 原生 `message_history` 能力接入。让 LLM 跨轮感知完整对话历史——
含 tool_call + tool_result ——消除当前纯文本记忆导致的决策割裂、重复查询和意图确认。

---

## 0. 现状与问题

### 0.1 当前数据流

```
每轮 SSE 连接:
  _inject_chat_history(payload)     → payload.context.conversation_history = [纯文本]
  state = {}                         → 全新空状态
  agent.iter(user_prompt, deps)      → LLM 只看到系统提示词 + 文本历史 + 当前消息
  流式循环                           → text / tool_start / tool_end 事件
  _persist_agent_chat_turn           → ChatTurn 表存文本
  state 丢弃                         → tool result 全部丢失
```

### 0.2 问题

PydanticAI 框架**原生支持** `message_history` 参数，`agent.iter()` 可以直接接收上轮的
`list[ModelMessage]`（含 tool_call + tool_result），让 LLM 在下一轮直接"看到"之前的工具输出。
但当前代码**没有用这个能力**——`agent.iter(user_prompt, deps=deps)` 不传 `message_history`。

后果：
- LLM 知道"我调过 run_learning_recommendation"（对话历史里有 tool_call），
  但**不知道返回了什么**（tool_result 在已丢弃的 state 里）
- 下轮只能重新调工具 → 浪费 token + 决策割裂
- 用户确认过的选择（如"选路径3"）只存在于文本中，LLM 需要从自然语言推断

### 0.3 PydanticAI API 确认

```python
# 当前
agent.iter(user_prompt, deps=deps)

# 目标
agent.iter(user_prompt, message_history=history, deps=deps)

# 轮后捕获
new_msgs = run.result.new_messages()   # list[ModelMessage] — 本轮增量
history.extend(new_msgs)               # 累积
```

**序列化：** PydanticAI 提供内置的 `ModelMessagesTypeAdapter`（一个
`TypeAdapter[list[ModelMessage]]`）专用于 JSON round-trip，比手动
`model_dump(mode='json')` + `model_validate()` 更稳——

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter

# 序列化
data = ModelMessagesTypeAdapter.dump_json(messages).decode()

# 反序列化
messages = ModelMessagesTypeAdapter.validate_json(json_data)
```

框架升级时 `TypeAdapter` 自动兼容子类变化，无需手动维护反序列化逻辑。

### 0.4 图执行模型（风险验证）

PydanticAI V2 使用图节点模型执行 agent：

```
UserPromptNode → ModelRequestNode → CallToolsNode → ModelRequestNode → ... → End
     ↑                 ↑                  ↑
     │                 │                  └─ 执行工具，产出 FunctionToolCallEvent / FunctionToolResultEvent
     │                 └─ 发送 LLM 请求，产出 PartStartEvent / PartDeltaEvent
     └─ 负责注入 message_history。传入的 history 由图节点标准处理，不是 hack
```

关键结论：
- `message_history` 由 `UserPromptNode` 标准注入，不改变下游节点行为
- `ModelRequestNode` 和 `CallToolsNode` 的 stream 事件类型、顺序是**图节点契约**
- `run.result` 在 `End` 节点到达后填充，`new_messages()` 在流结束后完整可用

---

## 阶段 1：存储层 —— message_history 持久化

### 1.0 新增常量

```python
# tasks/total_agent/agent_contracts.py

# message_history 最大保留轮数（每轮含 user request + model response 及其 tool 消息）
MESSAGE_HISTORY_MAX_TURNS = 20
```

### 1.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `schemas/agent_runtime_state.py` | 改 | `ChatSession` 新增 `message_history_json MEDIUMTEXT` 列 |
| `tasks/total_agent/agent_runtime.py` | 新增函数 | `_save_message_history()` / `_load_message_history()` |
| `tasks/total_agent/agent_contracts.py` | 改 | 新增 `MESSAGE_HISTORY_MAX_TURNS` 常量 |

### 1.2 函数收口

**`_save_message_history(user_id, syllabus_id, session_id, messages)`**

```
输入:
  user_id: int
  syllabus_id: int
  session_id: str
  messages: list[ModelMessage] — 要持久化的消息列表

输出: None（副作用）

内部逻辑:
  1. from pydantic_ai.messages import ModelMessagesTypeAdapter
  2. data = ModelMessagesTypeAdapter.dump_json(messages).decode()
  3. 尝试 DB:
       UPDATE chat_session
       SET message_history_json = :data
       WHERE session_id = :session_id
  4. DB 失败 → file fallback:
       写入 history/{syllabus_id}_{user_id}_{session_id}_messages.json
  5. 异常静默捕获，不阻断主流程
```

**`_load_message_history(user_id, syllabus_id, session_id) → list[ModelMessage]`**

```
输入:
  user_id: int
  syllabus_id: int
  session_id: str

输出:
  list[ModelMessage] — 空列表表示无历史或加载失败

内部逻辑:
  1. 尝试 DB:
       SELECT message_history_json
       FROM chat_session
       WHERE session_id = :session_id
  2. DB 失败 → file fallback:
       读取 history/{syllabus_id}_{user_id}_{session_id}_messages.json
  3. from pydantic_ai.messages import ModelMessagesTypeAdapter
  4. messages = ModelMessagesTypeAdapter.validate_json(data)
  5. 截断: 如果 len(messages) > MESSAGE_HISTORY_MAX_TURNS * 2 + 1，
     保留尾部（system prompt 在首条，不截）
  6. 任何异常（文件不存在、JSON 损坏、validate_json 失败）→ 静默返回 []
```

### 1.3 测试用例

```
TC1.1: 首次对话 → _load_message_history 返回 []
TC1.2: save → load roundtrip，消息列表一致
TC1.3: 损坏 JSON → 返回 [] 不抛异常
TC1.4: DB 不可用 → file fallback 正常
TC1.5: 超 MAX_TURNS → load 时自动截断
TC1.6: 大消息（完整 graph 在历史中）→ save/load 正常完成
```

---

## 阶段 2：Agent 接入 message_history

### 2.0 无需新增常量

### 2.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 改 | `_stream_total_agent_agent`: 加 message_history 参数，轮后捕获 new_messages；`get_total_agent`: 加 ReinjectSystemPrompt；`run_total_agent_agent` 非流式同步适配 |

### 2.2 数据流收口

```
                    ┌──────────────────────────┐
                    │ POST /api/total_agent/run │
                    │ payload: {user_id,        │
                    │   syllabus_id, session_id,│
                    │   message, ...}           │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ _load_message_history()   │  ← 新增
                    │ → list[ModelMessage]      │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ agent.iter(               │
                    │   user_prompt,            │
                    │   message_history=...,    │  ← 新增参数
                    │   deps=deps               │
                    │ )                         │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ 流式循环（不变）           │
                    │ text / tool_call /        │
                    │ tool_start / tool_end /   │
                    │ tool_status / final       │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ run.result.new_messages() │  ← 新增
                    │ history.extend(new)       │
                    │ _save_message_history()   │
                    │ (失败静默，不阻断主流程)   │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ state 丢弃（不变）         │
                    │ ChatTurn 表存文本（不变）  │
                    │ message_history 持久化    │
                    └──────────────────────────┘
```

### 2.3 函数级收口

**修改 `get_total_agent()`**（行 105-133）

```
变更:
  1. 新增 import:
     from pydantic_ai.capabilities import ReinjectSystemPrompt

  2. Agent 创建后注册 capability:
     agent = Agent(
         model=build_total_agent_model(),
         deps_type=TotalAgentDeps,
         system_prompt=(...),
         name="total_agent",
         retries=2,
         defer_model_check=True,
     )
     agent.capability(ReinjectSystemPrompt())   # ← 新增

  原因: message_history 非空时 PydanticAI 不重新生成 system prompt。
        ReinjectSystemPrompt 确保 system prompt 始终存在。
```

**修改 `_stream_total_agent_agent(payload)`**（行 1055-1186）

```
变更点 1 — 加载历史（state 初始化前）:

  uid = _positive_int(payload.get('user_id'))
  sid = _positive_int(payload.get('syllabus_id'))
  session_id = _resolve_session_id(payload)
  message_history = _load_message_history(uid, sid, session_id)  # ← 新增

变更点 2 — 传入 message_history（原: agent.iter(user_prompt, deps=deps)）:

  async with agent.iter(
      user_prompt,
      message_history=message_history,  # ← 新增
      deps=deps,
  ) as run:

变更点 3 — 轮后捕获（AFTER_LOOP_MARKER 之后，final 之前）:

  if run is not None and hasattr(run, 'result'):
      try:
          new_msgs = run.result.new_messages()
          message_history.extend(new_msgs)
          _save_message_history(uid, sid, session_id, message_history)
      except Exception:
          pass  # 历史保存失败不阻断主流程

注意: new_messages() 返回本轮新增的全部 ModelMessage——
      含 user prompt、text response、tool_call、tool_result。
      框架已自动组装，无需手动构造。
```

**同步修改 `run_total_agent_agent(payload, stream=False)`**（行 1189-1213）

```
非流式路径同样接入:

  message_history = _load_message_history(uid, sid, session_id)
  result = agent.run_sync(
      user_prompt,
      message_history=message_history,   # ← 新增
      deps=deps,
  )
  new_msgs = result.new_messages()
  message_history.extend(new_msgs)
  _save_message_history(uid, sid, session_id, message_history)
```

### 2.4 测试用例

```
TC2.1: 空历史 → agent 正常启动（PydanticAI 自动生成 system prompt）
TC2.2: 有历史 → agent 正常启动（ReinjectSystemPrompt 保证 system prompt 存在）
TC2.3: 第二轮对话 → LLM 在轮2能引用轮1 tool 返回的 candidates 列表
TC2.4: 轮后 new_messages() 非空 → save 成功
TC2.5: save 抛异常 → 不阻断 final 事件发送
TC2.6: load 返回 [] → agent 以空历史启动（降级）
TC2.7: 流式和非流式路径行为一致
TC2.8: 对话历史中的 tool_result 被正确序列化/反序列化（PydanticAI roundtrip）
```

---

## 阶段 3：简化冗余代码

### 3.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 改 | `build_total_agent_user_prompt` 移除 `context.conversation_history`；`_inject_chat_history` 精简 |

### 3.2 函数级收口

**`build_total_agent_user_prompt(state)`** — 移除对话历史注入

```
原因: LLM 从 message_history 获取完整对话 → 不需要 user_prompt 中再带纯文本历史

变更:
  context 字段精简为仅保留前端交互所需字段:
    "context": {
        "current_resource_id": ...,
        "recent_resource_ids": [...],
    }

  移除:
    "context": payload.get("context") or {}  → 不再整包传入
```

**`_inject_chat_history(payload)`** — 评估精简

```
分析:
  - 原职责一: 把 ChatTurn 文本写入 payload.context.conversation_history
    → 不再需要，LLM 从 message_history 获取
  - 原职责二: _ensure_session_created → 仍需要（session 管理）
  - 原职责三: merge frontend_history + disk_history → 前端面板用 ChatTurn API，
    不依赖此路径

结论:
  _inject_chat_history 精简为 _ensure_session_created(payload)，
  移除文本历史的加载和注入逻辑。
```

### 3.3 测试用例

```
TC3.1: build_total_agent_user_prompt 输出不含 conversation_history
TC3.2: _ensure_session_created 逻辑不受影响
TC3.3: 前端历史面板仍正常显示
```

---

## 阶段 4：附属优化 —— 瘦身 run_learning_recommendation 返回

> 注：此阶段**不阻塞** message_history 接入。接入完成后即可收益。
> 瘦身是为了减少 token 浪费，可按需延后。

### 4.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_tools.py` | 改 | `tool_run_learning_recommendation` 返回瘦身版 |

### 4.2 函数级收口

**新增 `_lean_recommendation_result(recommendation: dict) → dict`**

```
输入: recommendation — run_recommendation_route_from_payload 的完整返回
输出: 仅含 Agent 决策所需字段的摘要

提取:
  - candidates: [{rank, path, skills, cost, selected}]  ← 只取摘要，不取 path_nodes
  - best_path: {path, titles}
  - recommendation_id, snapshot_status, has_best_path

丢弃:
  - graph.nodes, graph.edges       ← 完整图留给 /api/recommendations/{id} 前端渲染
  - path_nodes                     ← 每个候选的详细节点信息
  - rag_overlay, planning_hints    ← 内部计算中间产物
  - debug                          ← 调试信息
```

**修改 `tool_run_learning_recommendation` 返回**

```
变更前:
  recommendation=recommendation,   ← 全量 ~150KB

变更后:
  recommendation_summary=_lean_recommendation_result(recommendation),  ← ~2KB

注意: state["recommendation_result"] 仍存全量，供后续工具内部使用。
      瘦身仅影响 tool_result → message_history 这条路径。
```

### 4.3 测试用例

```
TC4.1: 瘦身后 tool_result 不含 graph.nodes 和 graph.edges
TC4.2: state["recommendation_result"] 仍为全量（内部工具可用）
TC4.3: candidates 摘要数量与原始一致
```

---

## 阶段 5：验证

### 5.1 构建验证

```
TC5.1: npm run build 零错误（前端不变）
TC5.2: 现有 test_personal_recommendation_api.py 全过
TC5.3: 现有 test_plan_lifecycle.py 全过
```

### 5.2 功能验证

```
TC5.4: 首轮对话 → Agent 正常启动，tool 调用正常
TC5.5: 轮1生成推荐(candidates: 路径1/2/3) → 轮2用户说"选路径3"
       → Agent 能直接看到 candidates 列表，无需重调 run_learning_recommendation
TC5.6: 轮1接受路径 → 轮2用户问"下一步学什么"
       → Agent 能看到 accept_learning_plan 结果，直接调 get_next_learning_task
TC5.7: 轮1放弃计划 → 轮2用户要求新推荐
       → Agent 能看到 abandon 结果，确认无活跃计划，调 run_learning_recommendation
TC5.8: 多轮对话(5+轮) → token 消耗不因历史累积而爆炸
TC5.9: 损坏 message_history → 空历史降级启动，不影响对话
TC5.10: 历史 session 首次升级（ChatSession 无 message_history_json）→ 空历史正常启动
```

---

## 附录 A：不变清单

- ✅ SSE 事件格式（text_start/delta, tool_call/start/end/status, final）
- ✅ 前端全部组件（AgentStore, SubagentCard, ToolCallTimeline, AgentChatPanel）
- ✅ 后端 tool 函数内部逻辑（除阶段 4 可选瘦身）
- ✅ `state` 生命周期——仍每轮重建，工具函数使用
- ✅ `ChatTurn` 表——继续存文本消息供前端历史面板
- ✅ Snapshot / LearningPlan 持久化体系
- ✅ `_remember_terminal` / `_persist_agent_chat_turn`
- ✅ Agent 工具参数 schema（`candidate_index` 等）

## 附录 B：逐模块勾连风险评估

以下按数据流方向，追溯 `message_history` 接入与每个模块的连接点。

### B.1 模块全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                    total_agent_api.py                           │
│  POST /total_agent/agent_run                                    │
│  → total_agent_task.run_total_agent_agent(data, stream=True)   │
│  → async for event in async_gen:                               │
│      yield "data: {json}\n\n"                                   │
│    finally: _persist_stream_text_before_close(...)              │
│      yield "event: close\n\n"                                   │
└──────────────┬──────────────────────────────────────────────────┘
               │ 调用
┌──────────────▼──────────────────────────────────────────────────┐
│                 total_agent_task.py (facade)                    │
│  run_total_agent_agent → agent_runtime.run_total_agent_agent   │
│  (纯透传，无逻辑)                                               │
└──────────────┬──────────────────────────────────────────────────┘
               │ 调用
┌──────────────▼──────────────────────────────────────────────────┐
│                 agent_runtime.py  ◄── 改动集中在这里            │
│                                                                 │
│  _stream_total_agent_agent(payload):                            │
│    message_history = _load_message_history(...)     ← 新增      │
│    agent.iter(prompt, message_history=..., deps)   ← 改         │
│    流式循环 (不变)                                               │
│    new_msgs = run.result.new_messages()            ← 新增      │
│    _save_message_history(...)                      ← 新增      │
│    yield STREAM_EVENT_FINAL                         ← 不变      │
│                                                                 │
│  run_total_agent_agent(payload, stream=False):                  │
│    agent.run_sync(prompt, message_history=..., deps) ← 改      │
│    _save_message_history(...)                       ← 新增      │
│                                                                 │
│  build_total_agent_user_prompt(state)               ← 简化     │
│  _inject_chat_history(payload)                      ← 简化     │
│  get_total_agent() + ReinjectSystemPrompt           ← 改       │
└─────────────────────────────────────────────────────────────────┘
```

### B.2 逐模块追溯

#### 1. `blueprint/total_agent_api.py` — SSE 端点

**勾连方式：** 调用 `run_total_agent_agent(payload, stream=True)` → 返回 async generator → 逐 event 序列化为 `data: {json}\n\n` → `finally` 块调 `_persist_stream_text_before_close`。

**message_history 影响：**
- ❌ 不改变任何 yield 的 event 格式。7 种事件类型不变。
- ❌ 不改变 `_persist_stream_text_before_close` 的调用时机（仍在 finally 中）。
- ✅ `new_messages()` 捕获发生在 `_stream_total_agent_agent` 内部（STREAM_EVENT_FINAL 之前），早于 SSE wrapper 的 finally。
- ✅ 两个 SSE 端点（`total_agent_run_api` 和 `total_agent_agent_run_api`）结构一致，同时覆盖。

**风险：无。** SSE 层完全透明。

---

#### 2. `tasks/total_agent_task.py` — 门面

**勾连方式：** 纯 import + re-export，无逻辑。

**风险：无。** 参数透传。

---

#### 3. `tasks/total_agent/agent_runtime.py` — 核心运行时（改动集中处）

##### 3a. `get_total_agent()` — Agent 实例创建

**勾连方式：** 创建 `Agent` 对象，注册 `@agent.tool`，返回。

**message_history 影响：**
- 新增 `agent.capability(ReinjectSystemPrompt())`。
- `ReinjectSystemPrompt` 来自 `pydantic_ai.capabilities`，需确认当前 `pydantic-ai-slim` 版本包含此模块。

**风险：低。** 需验证 `pydantic_ai.capabilities` 是否存在。若不存在，可降级为在 `message_history` 前手动 prepend system prompt 的 `ModelRequest`。

##### 3b. `_stream_total_agent_agent(payload)` — 流式执行

**勾连方式：** 初始化 `state` → `agent.iter()` → 逐 node 流式 yield → 最终 `_build_agent_final_result`。

**message_history 影响：**

| 位置 | 当前 | 变更后 | 风险 |
|---|---|---|---|
| state 初始化前 | — | `message_history = _load_message_history(...)` | 低：纯读取，失败降级空列表 |
| `agent.iter()` | `(prompt, deps=deps)` | `(prompt, message_history=history, deps=deps)` | 中：PydanticAI 行为变化点 |
| 流式循环 | `async for node in run` | 不变 | 无 |
| AFTER_LOOP_MARKER 后 | — | `new_msgs = run.result.new_messages()` + `save` | 低：try-except 包裹 |

**关键验证点：**
- `agent.iter()` 传 `message_history` 后，`node.stream()` 行为是否不变？
  → PydanticAI 文档确认：stream 不受 message_history 影响，仅初始上下文不同。
- `run.result` 在 `async with` 块退出后是否仍可访问？
  → 当前代码已依赖此行为（行 1178: `run.result.output`）。`new_messages()` 同理。
- `new_messages()` 返回的消息是否包含 `user_prompt` 对应的 `ModelRequest`？
  → 是。`new_messages()` 包含本轮全部增量：user prompt + model response + tool calls + tool results。

**风险：中。** 集中在 `agent.iter()` 行为变化。需 smoke test 验证 stream 顺序和 event 格式不变。

##### 3c. `run_total_agent_agent(payload, stream=False)` — 同步执行

**勾连方式：** `agent.run_sync(prompt, message_history=history, deps=deps)`。

**风险：低。** 与流式路径共享 `_load_message_history` / `_save_message_history`，逻辑一致。

##### 3d. `build_total_agent_user_prompt(state)` — 用户提示构建

**勾连方式：** 从 `payload` 提取字段，构建 JSON prompt 字符串。

**message_history 影响：**
- 移除 `context.conversation_history` 注入。LLM 不再需要文本历史。
- 保留 `context.current_resource_id` 等前端交互字段。

**风险：低。** `conversation_history` 移除后，LLM 从 message_history 获取对话。若 message_history 为空（首轮），LLM 仅依赖 system prompt + 当前消息，行为与当前一致。

##### 3e. `_inject_chat_history(payload)` — 历史注入

**勾连方式：** 被 `run_total_agent_agent(payload)` 调用（行 1192），也直接用于 `run_total_agent`（行 990）。加载 ChatTurn 数据写入 `payload.context.conversation_history`。

**message_history 影响：**
- `message_history` 替代了其对话历史注入职责。
- 但 `_ensure_session_created` 仍在内部被调用 → 保留。
- 该函数还被 `run_total_agent`（旧 agent，非 PydanticAI）使用 → 不能删除，只能精简。

**风险：低。** 精简范围限定在 `conversation_history` 注入逻辑。旧 agent 路径不受影响。

---

#### 4. `tasks/total_agent/agent_tools.py` — 工具函数

**勾连方式：** 全部 tool 函数通过 `_tool_result()` 返回 dict。部分 terminal tool 通过 `_remember_terminal()` 写入 `state["terminal_tool_result"]`。

**message_history 影响：**
- ❌ 工具函数内部逻辑不变。它们仍操作 `state`。
- ❌ `_remember_terminal` 不变。`state["terminal_tool_result"]` 仍用于 `_persist_agent_chat_turn`。
- ✅ tool result 通过 PydanticAI 框架自动进入 `message_history`（作为 `FunctionToolResultEvent` → `ModelRequest` with `ToolReturnPart`）。无需手动注入。

**风险：无。** 工具层完全透明。PydanticAI 框架自动处理 tool result 到消息的转换。

---

#### 5. `tasks/total_agent/agent_contracts.py` — 常量定义

**勾连方式：** 定义 `STREAM_EVENT_*`、`TOOL_*`、`INTENT_*` 常量。

**message_history 影响：**
- 新增 `MESSAGE_HISTORY_MAX_TURNS = 20`。
- 现有常量不变。

**风险：无。**

---

#### 6. `schemas/agent_runtime_state.py` — 数据库 Schema

**勾连方式：** `ChatSession` 表存 session 元数据，`ChatTurn` 表存文本消息。

**message_history 影响：**
- `ChatSession` 新增 `message_history_json = Column(Text)` 列。
- `ChatTurn` 不变——继续存文本消息供前端面板。

**风险：低。** 新增列，不影响现有查询。需 migration。

---

#### 7. 前端全部模块 — SSE 消费端

**勾连方式：** `useSSEStream.ts` → `EventSource` 读取 SSE → `agentStore.dispatch(event)` → 组件渲染。

**message_history 影响：**
- ❌ 不改变任何 SSE event 的 type/data 结构。
- ❌ 不新增 event type。
- ❌ `tool_end` 的 `result` 字段内容不变（瘦身是可选的附属优化）。
- ✅ 前端对 `message_history` 完全无感知。

**风险：无。** 前端零改动。

---

#### 8. `tasks/study_buddy_task.py` / `_select_buddy_event` — 学伴通知

**勾连方式：** `_build_agent_final_result` 内调用 `_select_buddy_event`，传入各 terminal tool 结果（`accept_terminal`, `recommendation_terminal` 等）。这些结果来自 `state`，不从 `message_history` 读取。

**message_history 影响：**
- ❌ 不改变 `state` 内容。`_select_buddy_event` 的输入不变。
- ❌ `notify_study_buddy_event` 仍在 `_persist_final_agent_turn` 中调用，逻辑不变。

**风险：无。**

---

#### 9. `persist_streamed_agent_reply` — SSE 文本持久化

**勾连方式：** `total_agent_api.py` 的 finally 块调用，把流式文本写入 ChatTurn 表。

**message_history 影响：**
- ❌ 不改变其调用方式或参数。
- ✅ `new_messages()` 保存的是 PydanticAI ModelMessage 二元组，与此函数的 ChatTurn 记录是两套独立存储，互不依赖。

**风险：无。**

---

### B.3 风险矩阵（按模块汇总）

| # | 模块 | 勾连方式 | 改动 | 风险等级 | 关键验证点 |
|---|---|---|---|---|---|
| 1 | `total_agent_api.py` | SSE 端点 | 无 | 🟢 无 | 不变 |
| 2 | `total_agent_task.py` | 门面 | 无 | 🟢 无 | 不变 |
| 3a | `agent_runtime:get_total_agent` | Agent 创建 | 加 capability | 🟡 低 | `pydantic_ai.capabilities` 存在性 |
| 3b | `agent_runtime:_stream` | 流式循环 | 加 history 参数 | 🟢 低 | `UserPromptNode` 标准注入，节点契约不变 |
| 3c | `agent_runtime:run_sync` | 同步路径 | 加 history 参数 | 🟢 低 | 与流式一致 |
| 3d | `agent_runtime:build_prompt` | 提示构建 | 移除文本历史 | 🟢 低 | 首轮空 history 行为不变 |
| 3e | `agent_runtime:_inject_history` | 历史注入 | 精简 | 🟢 低 | 旧 agent 路径不受影响 |
| 4 | `agent_tools.py` | 工具函数 | 无 | 🟢 无 | PydanticAI 自动转换 tool result |
| 5 | `agent_contracts.py` | 常量 | 新增 1 个 | 🟢 无 | — |
| 6 | `agent_runtime_state.py` | DB Schema | 新增 1 列 | 🟢 低 | migration |
| 7 | 前端全部 | SSE 消费 | 无 | 🟢 无 | 零改动 |
| 8 | `study_buddy_task` | 学伴通知 | 无 | 🟢 无 | state 不变 |
| 9 | `persist_streamed_agent_reply` | 文本持久化 | 无 | 🟢 无 | ChatTurn 不变 |

### B.4 已消解的中等风险点

**原风险评估：`agent.iter()` 传 `message_history` 后的流式行为不可控。**

经调研确认，此风险不成立。PydanticAI V2 使用图节点模型——

```
UserPromptNode  →  ModelRequestNode  →  CallToolsNode  →  ModelRequestNode  →  ...  →  End
```

- `UserPromptNode` **专职负责**注入 `message_history`，是图节点的标准职责
- `ModelRequestNode` / `CallToolsNode` 的 stream 事件（`PartStartEvent`, `PartDeltaEvent`, `FunctionToolCallEvent`, `FunctionToolResultEvent`）是**图节点契约**，不因传入额外历史而变
- `run.result` 在 `End` 节点到达后填充，与是否传入 `message_history` 无关
- `new_messages()` 在流结束后完整可用（框架文档确认）

**结论：降级为低风险。** `message_history` 是框架一等公民，不是 hack。流式行为完全由节点契约保证。
