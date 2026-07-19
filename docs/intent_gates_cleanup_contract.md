# 意图层门禁清理 Contract

> **状态：✅ 已实现 (commit 3d79ed6)**
> 阶段 1（accept_learning_plan 门禁清退）和阶段 3（_message_is_vague_resource_request 语义修正）已落地。

简化和清退 Total Agent 意图推断与工具执行流程中的冗余、误导性硬编码门禁。

---

## 0. 全量门禁清单

### 0.1 门禁函数（4 个 helper）

| 函数 | 位置 | 机制 | 职责 |
|---|---|---|---|
| `_confirmation_requested` | L420-425 | 关键词 `"确认/采纳/就按/accept/confirm"` | 判断用户是否确认 |
| `_has_pending_recommendation` | L428-442 | 检查 `state["recommendation_result"]` | 判断是否有待确认推荐 |
| `_message_has_any` | L445-447 | 关键词 `in` 匹配 | 通用关键词检查器 |
| `_message_is_vague_resource_request` | L450-477 | 模糊词 `"随便/任意/来一个"` 且无具体词 | 判断资源请求是否模糊 |

### 0.2 调用点（7 处）

| # | 位置 | 函数 | 门禁 | 角色 | 问题 |
|---|---|---|---|---|---|
| A1 | L1881 | `infer_user_intent` | `_confirmation_requested` + `_has_pending_recommendation` | 意图分类：确认词→accept | 关键词不匹配则跳过 |
| A2 | L1885 | `infer_user_intent` | `_confirmation_requested` | 意图分类：确认词但无pending→continue | 同上 |
| B | L1891 | `infer_user_intent` | `_message_has_any` (反馈) | 意图分类：反馈词→feedback | OK，语义明确 |
| C | L1895 | `infer_user_intent` | `_message_has_any` (跳过) | 意图分类：跳过词→skip | OK，语义明确 |
| D | L1899-1909 | `infer_user_intent` | `_message_has_any` (策略/推荐/资源) | 意图分类：多组关键词 | 关键词覆盖不全 |
| E | L1914 | `infer_user_intent` | `_message_has_any` (疑问) | 意图分类：疑问词→answer | OK，语义明确 |
| F | L2070 | `accept_learning_plan` | `_confirmation_requested` | **禁止accept** | 🔴 和 LLM 决策冲突 |
| G | L1908-1909 | `infer_user_intent` | `_message_is_vague_resource_request` | 判断资源请求是否模糊 | 模糊但语义明确时误导 |

### 0.3 问题分级

| 级别 | 调用点 | 问题描述 |
|---|---|---|
| 🔴 必须清退 | F | `_confirmation_requested` 在 `accept_learning_plan` 中做二次拦截。LLM 已决定调用 accept 工具，代码却用关键词推翻。直接导致"确认→再确认"死循环 |
| 🟡 必须修正 | A1, A2 | `_confirmation_requested` 的关键词列表过窄。"计划三更适合我"/"选这个"/"就要第2个" 等自然语言选择不匹配 |
| 🟡 必须修正 | D | `_message_has_any` 推荐词列表不含"计划"、"候选"等 Agent 自然对话里常用的词 |
| 🟢 可保留 | B, C, E | 反馈/跳过/疑问的关键词匹配语义明确，误判率低 |
| 🟢 可保留 | G | `_message_is_vague_resource_request` 逻辑合理：模糊请求+有active plan→合理推断为继续学习 |

---

## 阶段 1：清退 F —— `accept_learning_plan` 中的确认词门禁

### 1.0 新增常量

无。

### 1.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_tools.py` | 删 | 移除 `tool_accept_learning_plan` 中的 `_confirmation_requested` 调用 |

### 1.2 函数级收口

**修改 `tool_accept_learning_plan`** (L2070)

```
变更前:
  if not _confirmation_requested(payload):
      return _tool_result(..., accepted=False,
          reason="user confirmation or auto_accept=true is required")

变更后:
  删除此段。LLM 调用 accept 工具本身就是最可靠的确认信号。
  保留 auto_accept 标志（用于测试/API 直接调用）：
    candidate_index = payload.get("candidate_index")
    if not candidate_index and not payload.get("auto_accept"):
        # 如果 LLM 没传 candidate_index 且未设置 auto_accept，
        # 使用第一个候选（默认路径）
        pass

数据流:
  LLM 看到用户消息 → 推断意图 → 决定调用 accept_learning_plan(candidate_index=N)
  → 工具收到参数 → 直接执行 accept → 不再二次校验关键词
```

### 1.3 测试用例

```
TC1.1: 用户说 "计划三更适合我" → LLM 调 accept(candidate_index=2) → 成功确认
TC1.2: 用户说 "就这个" → LLM 调 accept() → 使用默认候选 → 成功确认
TC1.3: 用户说 "有哪些路径" → LLM 调 run_learning_recommendation → 不调 accept → 正常
TC1.4: auto_accept=true 的 API 调用 → 绕过确认门禁 → 直接 accept（保持兼容）
```

---

## 阶段 2：修正 A1/A2/D —— 扩展 `infer_user_intent` 的关键词覆盖

### 2.0 新增常量

```python
# 确认/选择类关键词：用户表达选择意愿的自然语言
_CONFIRMATION_MARKERS = (
    "采纳", "确认", "就按", "按这条", "开始这条", "接受",
    "accept", "confirm",
    "选", "就这个", "就要", "要这个", "这个吧", "这个好",  # ← 新增
    "选第", "第几个", "路径", "计划",                         # ← 新增
    "go with", "pick", "choose", "let's do",                # ← 新增
)

# 推荐/路径类关键词：用户想获取或重新查看推荐
_RECOMMENDATION_MARKERS = (
    "推荐", "路径", "学什么", "怎么学", "规划",
    "recommend", "path", "route",
    "计划", "候选", "方案", "选项",     # ← 新增：Agent 自然语言常用词
    "重新生成", "重产", "再来",         # ← 新增：用户想要新推荐
)
```

### 2.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_tools.py` | 改 | 扩展 `_confirmation_requested` 的关键词；扩展 `infer_user_intent` 中推荐词列表 |

### 2.2 函数级收口

**扩展 `_confirmation_requested`** (L420-425)

```
变更:
  markers 从 8 个中文词 → 扩展到 ~20 个，覆盖自然选择语言
  新增: "选", "就要", "要这个", "这个吧", "选第", "第几个", "路径", "计划"
```

**扩展 `infer_user_intent` 中推荐词列表** (L1903)

```
变更:
  markers 增加 "计划", "候选", "方案", "选项", "重新生成", "重产"
  原因: Agent 生成推荐后会用 "推荐学习计划" 带回用户，用户回复"选计划三"时，
        "计划" 不在原关键词列表，导致意图误判为 generate 而非 accept 或 recommend
```

### 2.3 测试用例

```
TC2.1: "计划三更适合我" → _confirmation_requested 返回 False（不含确认词，含选词但无序号格式）
        → 但 infer_user_intent 的推荐词匹配 "计划" → 走 recommend 路径
        → LLM 看到 recommend intent + candidates → 自己决定调 accept
TC2.2: "选第3个" → _confirmation_requested 返回 True（"选第" 命中）
TC2.3: "就这个吧" → _confirmation_requested 返回 True（"就这个" 命中）
TC2.4: "重新生成推荐" → 命中推荐词 → LLM 调 run_learning_recommendation
```

---

## 阶段 3：评估 —— `infer_user_intent` 是否需要改为 LLM 驱动

### 3.0 背景

阶段 1+2 是修门禁，但 `infer_user_intent` 内部本质上是一个 if-else 级联：
```
消息 → 关键词匹配 → 硬编码分类 → 意图字符串
```

当前 `total_agent`（PydanticAI Agent）调用 `infer_user_intent` 工具时，工具返回的 `intent` 只是作为提示——LLM 可以覆盖它。但当这个提示是错误的时候（如阶段 2 的案例），LLM 需要额外 effort 来推翻它。

### 3.1 评估结论

**暂不改。** 理由：

1. message_history 接入后，LLM 能跨轮感知上下文——它的语义理解能力远强于关键词匹配。`infer_user_intent` 的返回应该降级为"提示/建议"，LLM 有最终判断权。

2. 改为 LLM 驱动需要额外的 LLM 调用（embedding 或 completion）→ 延迟和 token 成本增加。关键词匹配的 speed/zero-token 优势有保留价值。

3. 阶段 1+2 修正后，关键词覆盖足够宽，误判率大幅下降。剩下的边缘 case 交给 LLM 覆盖——这正是 PydanticAI Agent 擅长的。

4. 观察周期：message_history 上线后，观察 LLM 在跨轮对话中的意图推断质量。如果 LLM 频繁推翻 `infer_user_intent` 的建议，再启动 LLM 驱动改造。

### 3.2 当前不改，但留设计方向

```
未来方案:
  infer_user_intent 简化为:
    1. 检查 explicit_intent（payload 传入） → 直接使用
    2. 检查 auto_accept → accept
    3. 其余: 返回 intent=""  confidence=0.5
       → 让 LLM 完全自主判断意图

  或者:
    4. 改为 LLM function call，输入 message + context → 输出 intent + confidence
```

---

## 阶段 4：注入 pending_recommendation —— 修复 active_plan ≠ pending 的语义混淆

### 4.0 问题诊断

**Agent 自诊断的三个问题，根因是同一个语义混淆：**

```
active_plan            → 已被 accept 的、正在执行的学习计划（空是正常的）
pending_recommendation  → 已生成但未 accept 的推荐（含 candidates）← 从未被注入上下文
```

当前 `load_total_context` 返回：

```python
total_context = {
    "active_plan": {},          # ← 空的，因为还没 accept。带误导性：被解读为"无事可做"
    "next_task": {},            # ← 空的，因为依赖 active_plan
    "current_resource_id": "",
    # ← 缺失: "pending_recommendation": {candidates, best_path, snapshot_id, ...}
}
```

Agent 理解到的："三个字段都空 → 没有待确认的推荐计划 → 重生成"。

**真相：** 最新 proposed snapshot 在磁盘/DB 上躺着。`list_recommendation_snapshots(user_id, syllabus_id)` 能查到。但 `load_total_context` 不查它，`accept_learning_plan` 也不 fallback 到它。

**缺口在两个位置：**

| 函数 | 当前位置 | 缺口 | 后果 |
|---|---|---|---|
| `load_total_context` | 只返回 active_plan, profile, study_graph | 不注入 pending_recommendation | Agent 看不到候选列表 |
| `accept_learning_plan` | 只从 `state["recommendation_result"]` 取数据 | 不从 snapshot 回退读取 | 跨轮 state 丢失后无法 accept |

### 4.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_tools.py` | 改 | `tool_load_total_context` 返回增加 `pending_recommendation`；`tool_accept_learning_plan` 增加 snapshot 回退 |
| `tasks/personal_recommendation/snapshot.py` | 不变 | 已有 `list_recommendation_snapshots` 和 `get_recommendation_snapshot` |

### 4.2 函数级收口

**修改 `tool_load_total_context`** (L1836-1852)

```
新增逻辑（在 active_plan 加载之后，total_context 组装之前）:

  # ── 注入待确认推荐 ──
  pending_recommendation = {}
  try:
      from tasks.personal_recommendation_task import list_recommendation_snapshots
      result = list_recommendation_snapshots(user_id, syllabus_id, limit=1)
      snapshots = result.get("snapshots") if isinstance(result, dict) else []
      if snapshots and snapshots[0].get("status") == "proposed":
          snap = snapshots[0]
          pending_recommendation = {
              "recommendation_id": snap.get("recommendation_id"),
              "candidate_count": snap.get("candidate_count", 0),
              "best_path_titles": snap.get("best_path_titles", []),
              "status": "proposed",
          }
  except Exception:
      pass  # 查询失败不影响其他上下文加载

  total_context = {
      ...
      "pending_recommendation": pending_recommendation,   # ← 新增字段
      ...
  }
```

**修改 `tool_accept_learning_plan`** (L2082-2090)

```
变更前:
  recommendation = _safe_dict(
      state.get("recommendation_result")
      or payload.get("recommendation_result")
  )
  if not recommendation:
      return error "missing_recommendation_result"

变更后:
  recommendation = _safe_dict(
      state.get("recommendation_result")
      or payload.get("recommendation_result")
  )
  # ── fallback: 从 snapshot 回退读取 ──
  if not recommendation:
      try:
          sid = syllabus_id
          rec_id = _safe_text(payload.get("recommendation_id"))
          if not rec_id:
              # 查最新 proposed snapshot
              result = prt.list_recommendation_snapshots(user_id, sid, limit=1)
              snapshots = result.get("snapshots") if isinstance(result, dict) else []
              if snapshots and snapshots[0].get("status") == "proposed":
                  rec_id = snapshots[0].get("recommendation_id")
          if rec_id:
              detail = prt.get_recommendation_snapshot(str(rec_id))
              if detail.get("success"):
                  recommendation = prt._recommendation_result_from_snapshot(
                      detail.get("snapshot")
                  )
      except Exception:
          pass
  if not recommendation:
      return error "missing_recommendation_result"

注意: candidate_index 来源不变（LLM 参数 → payload["candidate_index"]）。
      snapshot 只解决 "state 空了拿不到 recommendation" 的问题。
```

### 4.3 数据流变更

```
当前（Agent 盲区）:
  load_total_context:
    → active_plan: {}     ← Agent 看到空 → "没事可做"
    → next_task: {}
    → (无 pending_recommendation)

修复后:
  load_total_context:
    → active_plan: {}
    → pending_recommendation: {          ← 新增
        "recommendation_id": "rec_xxx",
        "candidate_count": 4,
        "best_path_titles": ["第1章...", "第2章..."],
        "status": "proposed",
      }
    → Agent 看到: "有4个候选待确认，最佳路径是关于第1章的"

  accept_learning_plan:
    → state["recommendation_result"] 空
    → 查 snapshot → 找到 → 用 snapshot 里的 recommendation
    → accept(candidate_index=2) → 成功
```

### 4.4 测试用例

```
TC4.1: 轮1 run_learning_recommendation → 生成4候选 → snapshot=proposed
       → load_total_context 返回 pending_recommendation 含 candidate_count=4
TC4.2: 轮2 Agent 看到 pending_recommendation → 知道有待确认推荐 → 不再重生成
TC4.3: 用户说 "选第3个" → accept_learning_plan:
       state["recommendation_result"] 空 → fallback 查 snapshot → 成功 accept
TC4.4: 无 proposed snapshot → load_total_context 返回 pending_recommendation={}
       → Agent 正常调 run_learning_recommendation 生成新推荐
TC4.5: snapshot 查询抛异常 → load_total_context 和 accept_learning_plan 均不崩溃
TC4.6: candidate_index=2 正确传递到 accept_recommendation_path
```

---

## 阶段 5：架构重整 —— `infer_user_intent` 降级为 `note_intent`

### 5.0 背景

当前 `infer_user_intent` 是一个硬编码关键词级联的函数，被注册为 PydanticAI 工具，
在 `TOTAL_AGENT_TOOL_ORDER` 的每个 intent 中都是必调项。它做了三件不该做的事：

1. **用关键词替 LLM 做语义判断**——`_message_has_any` 的 50+ 关键词永远覆盖不全自然语言
2. **产出 `intent` 字符串 → 成为后续工具的门禁**——`generate_current_step_resource`
   和 `answer_learning_question` 用 `state["intent"]` 做 `ModelRetry` 拦截
3. **成了工具顺序的必选项**——每个 intent 的工具列表都以它开头，Agent 无法跳过

改为 `note_intent`：LLM **可选**调用以记录自己对用户意图的理解，纯备忘，不做门禁。

### 5.1 `state["intent"]` 的完整依赖链

在改之前，需要追踪所有消费 `state["intent"]` 的地方：

| 位置 | 文件 | 行号 | 用途 | 改为 `note_intent` 后 |
|---|---|---|---|---|
| `infer_user_intent` 工具 | agent_runtime.py | L164-165 | 调用关键词级联 | **删除工具注册** |
| `generate` intent guard | agent_runtime.py | L212-214 | `ModelRetry` 拦截 | **删除** — LLM 自行判断 |
| `answer` intent guard | agent_runtime.py | L233-234 | `ModelRetry` 拦截 | **删除** — LLM 自行判断 |
| `build_total_agent_user_prompt` | agent_runtime.py | L264 | 注入 `intent_hint` | 保留 `intent_hint`（来自 payload） |
| `build_total_agent_user_prompt` | agent_runtime.py | L267 | 注入 `tool_order_by_intent` | 保留（提示层，非门禁） |
| `_build_agent_final_result` | agent_runtime.py | L273 | 读取 intent 用于 final | 改为从 terminal tool 推断 |
| `_build_agent_final_result` | agent_runtime.py | L282 | 读取 `intent_result` | 删除此字段 |
| 选择 suggested_next_action | agent_runtime.py | L377-381 | if/elif intent 链 | 改为从 terminal_tool 推断（已有 fallback） |
| `tool_infer_user_intent` | agent_tools.py | L1868-1950 | 整个函数 | **删除** |
| `_confirmation_requested` | agent_tools.py | L420-425 | 被 infer 调用 | **删除** — 仅剩 accept 里的调用点在阶段 1 已清退 |
| `_message_has_any` | agent_tools.py | L445-447 | 被 infer 调用 | 保留——资源生成和 Q&A 仍用它做内容分类 |
| `_message_is_vague_resource_request` | agent_tools.py | L450-477 | 被 infer 调用 | 保留——资源生成策略仍在用 |
| `TOTAL_AGENT_TOOL_ORDER` 各 intent | agent_contracts.py | L159-210 | 工具顺序建议 | 移除每条的 `TOOL_INFER_USER_INTENT` |
| `run_total_agent` (旧路径 L2650+) | agent_runtime.py | — | deterministic 分支 | **不改**——旧路径独立 |

### 5.2 新增 `note_intent` 工具

```python
# agent_runtime.py — 注册为 Agent 工具

@agent.tool
def note_intent(
    ctx: RunContext[TotalAgentDeps],
    intent: str = "",
    detail: str = "",
) -> dict:
    """记下你对当前用户意图的理解。不是必调——仅在需要备忘时使用。

    Args:
        intent: 你推断的用户意图标签。建议用以下之一，但可自定义：
                "recommend_learning_path" — 用户想要推荐路径
                "accept_recommendation"   — 用户想确认某条候选路径
                "generate_resource"       — 用户想要学习资源
                "record_feedback"         — 用户在学习反馈
                "skip_current_step"       — 用户想跳过当前步骤
                "abandon_plan"            — 用户想放弃当前计划
                "answer_question"         — 用户问了一个学习问题
                "clarify_goal"            — 用户的目标需要澄清
        detail: 补充细节。例如 "用户想选第3个候选（计划三），需要确认具体步骤数"
    Returns:
        dict with intent, detail, noted=True
    """
    result = {"intent": str(intent or ""), "detail": str(detail or ""), "noted": True}
    # 存入 state 供本轮的后续工具参考（如 _build_agent_final_result 推断 suggested_next_action）
    ctx.deps.state["noted_intent"] = result
    return result
```

**关键设计：**
- `noted_intent["intent"]` 是 LLM 自己填的字符串，可自由写——不是 enum，不被任何工具用 `!= INTENT_XXX` 校验
- `noted_intent["detail"]` 是自然语言备注——LLM 可以在 message_history 跨轮中看到自己上次的理解
- 不调用也完全正常——`state["noted_intent"]` 为空，后续逻辑不依赖它

### 5.3 去掉 `generate` 和 `answer` 的 intent 门禁

**删除 `generate_current_step_resource` 中的 intent 守卫**（agent_runtime.py L212-214）：
```
变更前:
  if ctx.deps.state.get("intent") != INTENT_GENERATE_CURRENT_STEP_RESOURCE:
      raise ModelRetry(...)

变更后:
  删除。LLM 调用此工具本身就是它判断应该生成的信号。
  保留 ModelRetry 仅用于流程约束（如：必须先 retrieve_evidence 再 answer）。
```

**删除 `answer_learning_question` 中的 intent 守卫**（agent_runtime.py L233-234）：
```
变更前:
  if ctx.deps.state.get("intent") != INTENT_ANSWER_LEARNING_QUESTION:
      raise ModelRetry(...)

变更后:
  删除。保留其下面的 TOOL_RETRIEVE_LEARNING_EVIDENCE 前置检查——
  那个是流程纪律，不是语义门禁。
```

### 5.4 系统提示词更新

```python
# 当前:
"Always start by understanding their current learning context (load_total_context, infer_user_intent). "

# 改为:
"Always start by understanding their current learning context (load_total_context). "
"You may optionally call note_intent to record your understanding of the user's goal — "
"this helps you stay on track across turns but is not required."
```

### 5.5 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 删+改+新增 | 删除 `infer_user_intent` 工具注册；删除两个 intent 门禁；新增 `note_intent` 工具；更新 system prompt |
| `tasks/total_agent/agent_tools.py` | 删 | 删除 `tool_infer_user_intent` 函数（保留其 helper：`_message_has_any`, `_message_is_vague_resource_request`） |
| `tasks/total_agent/agent_contracts.py` | 改 | `TOTAL_AGENT_TOOL_ORDER` 每个 intent 列表移除 `TOOL_INFER_USER_INTENT`；移除 `TOOL_INFER_USER_INTENT` 常量可保留但标记 deprecated |

### 5.6 数据流变更

```
当前:
  Agent 启动
  → tool_order 强制: [load_total_context, infer_user_intent, ...]
  → infer_user_intent: 关键词级联 → state["intent"] = "xxx"
  → 后续工具检查 state["intent"]: 不匹配则 ModelRetry
  → LLM 的语义推理被门禁覆盖

改为:
  Agent 启动
  → tool_order 建议: [load_total_context, ...]
  → LLM 调 load_total_context → 有了上下文
  → LLM 可选择调 note_intent(intent="accept_recommendation", detail="用户想选计划三")
    → 本轮备忘: state["noted_intent"]
    → 跨轮记忆: message_history 自动保留
  → LLM 直接调 accept_learning_plan(candidate_index=2)
  → 无门禁拦截 —— LLM 的最终判断即最终行动
```

### 5.7 `_build_agent_final_result` 适配

原读取 `state["intent"]` 的地方改为从终端工具推断：

```
变更前:
  intent = str(state.get("intent") or ...)
  if intent == INTENT_RECOMMEND_LEARNING_PATH or terminal_tool == TOOL_RUN_LEARNING_RECOMMENDATION:
      suggested = ...

变更后:
  以 terminal_tool 为主:
  if terminal_tool == TOOL_RUN_LEARNING_RECOMMENDATION:
      suggested = ...
  elif terminal_tool == TOOL_ACCEPT_LEARNING_PLAN:
      suggested = ...
  ...
  仅当 terminal_tool 为空时才 fallback 到 state["noted_intent"]:
  noted = state.get("noted_intent", {})
  if noted.get("intent") == "accept_recommendation":
      suggested = ACTION_WAIT_USER_ACCEPTANCE
```

### 5.8 风险矩阵

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | LLM 不调 `note_intent` → `state["noted_intent"]` 为空 | 🟢 低 | `_build_agent_final_result` 已改以 `terminal_tool` 为主，不依赖 `noted_intent` |
| R2 | LLM 填了一个非标 intent → 旧代码找不到匹配 | 🟢 低 | `noted_intent["intent"]` 只在 fallback 路径兜底，不匹配时降级为空，不拦截 |
| R3 | 去掉 `generate`/`answer` 门禁后 LLM 错误调用 | 🟡 中 | 观察。系统提示词 + message_history 上下文足够 LLM 做正确判断。若误调用频繁可加回轻量 guard（但不依赖硬编码 intent 值） |
| R4 | `TOTAL_AGENT_TOOL_ORDER` 去掉 `infer_user_intent` 后 Agent 行为异常 | 🟢 低 | 工具顺序是建议层，LLM 不受约束。去掉后 LLM 有更大自主性 |
| R5 | 旧 `run_total_agent` 路径仍依赖 `infer_user_intent` | 🟢 无 | 不改旧路径。`run_total_agent` 独立于 PydanticAI agent |
| R6 | `note_intent` 的 `intent` 字符串和 `_build_agent_final_result` 的 fallback 匹配不一致 | 🟢 低 | fallback 用宽松匹配（`in` 而非 `==`），且仅 `terminal_tool` 为空时才用 |
| R7 | `_message_has_any` / `_message_is_vague_resource_request` 删除后资源生成逻辑受损 | 🟢 无 | 这两个 helper 保留。它们被 `build_resource_strategy` 和 Q&A 使用，与 intent 无关 |

### 5.9 测试用例

```
TC5.1: Agent 不调 note_intent → noted_intent 为空 → final_result 正常（走 terminal_tool 推断）
TC5.2: Agent 调 note_intent(intent="accept_recommendation", detail="用户想选计划三")
       → state["noted_intent"] = {...}
       → message_history 跨轮保留
TC5.3: 用户说 "计划三更适合我" → LLM 自己判断 intent → 调 accept(candidate_index=2) → 成功
       → 不再被关键词门禁拦截
TC5.4: 用户说 "生成PPT" → LLM 直接调 generate_current_step_resource(resource_types=["ppt"])
       → 不再被 intent guard 拦截
TC5.5: 用户说 "为什么HBase用RowKey" → LLM 调 retrieve_evidence → answer
       → retrieve_evidence 前置检查保留 → 不跳过
TC5.6: 旧 run_total_agent 路径 behavior 不变（infer_user_intent 保留在旧代码中）
TC5.7: 现有 test_personal_recommendation_api.py + test_plan_lifecycle.py 全过
TC5.8: `note_intent` 的 intent 字符串为自由格式 → fallback 匹配用 `in` 而非 `==` → 容错
```

---

## 阶段 6：验证

### 4.1 构建验证

```
TC4.1: npm run build 零错误
TC4.2: Python 语法无错误
TC4.3: 现有 test_personal_recommendation_api.py + test_plan_lifecycle.py 全过
```

### 4.2 功能验证

```
TC4.4: "计划三更适合我" → Agent 识别为 accept/recommend 意图，不再误判为 generate
TC4.5: "选第2个" → Agent 直接调 accept(candidate_index=1)，不再反问确认
TC4.6: "就这个" → Agent 调 accept() 使用默认候选，成功
TC4.7: "有哪些路径" → Agent 调 run_learning_recommendation，不调 accept
TC4.8: "确认→再确认" 死循环不再出现
```

---

## 附录：不变清单

- ✅ `_has_pending_recommendation` — 逻辑正确，保留
- ✅ `_message_is_vague_resource_request` — 逻辑合理，保留
- ✅ B/C/E 调用点（反馈/跳过/疑问门禁）— 关键词匹配准确，保留
- ✅ `auto_accept` 标志 — 保留，测试和 API 场景需要
- ✅ `infer_user_intent` 整体架构 — 暂不改 LLM 驱动，保留关键词级联作为快速提示层
