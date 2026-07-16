# Total Agent → 子 Agent 写通路带宽扩容 Contract

收口 Total Agent 向下游模块写入结构化学习信号的能力增强。核心目标：
让 Agent 观察到的用户学习行为（掌握度、薄弱点、反馈）以结构化形式送达
Profile Agent 和 Study Graph Agent，而不是丢失在 LLM 的自然语言生成里。

---

## 0. 背景：当前写通路带宽缺口

| 通路 | 当前带宽 | 缺口 |
|---|---|---|
| Total Agent → Profile | **不存在** | Agent 观察到用户风格变化、能力提升，无法写入画像 |
| Total Agent → Study Graph | **1 bit**（completed/not） | 无法传入 score, weak_points, feedback_note |
| Total Agent → Resource List | **函数存在但无工具** | `find_personal_resources` 未注册，LLM 无法调 |

## 0.1 结构化信号格式

Profile Agent 和 Study Graph Agent 都需要"知识-掌握"结构。统一为一个可复用格式：

```python
# 知识掌握条目
KNOWLEDGE_MASTERY_SCHEMA = {
    "knowledge": str,       # 知识点名称，如 "RowKey 设计"
    "mastery_label": str,   # "mastered" | "learning" | "weak" | "unknown"
    "score": float,         # 0.0 - 1.0，置信度评分
    "evidence": str,        # Agent 判断依据简述
}
```

Profile Agent 用它更新 `weak_points` / `bottleneck_topics`。
Study Graph Agent 用它更新节点 mastery score 和薄弱标记。

---

## 阶段 1：`record_learning_feedback` 参数化

### 1.0 新增常量

```python
# agent_contracts.py

# 知识掌握条目 schema（文档用，不影响运行时）
# {knowledge: str, mastery_label: str, score: float, evidence: str}
```

### 1.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 改 | `record_learning_feedback` 工具加参数 |
| `tasks/total_agent/agent_tools.py` | 改 | `tool_record_learning_feedback` / `_record_step_status` 穿透新字段到 study graph |
| `tasks/study_graph_task.py` | 改 | `build_study_graph_changes_from_resource_event` 接收新字段 |

### 1.2 函数级收口

**修改 `record_learning_feedback` 工具注册**（agent_runtime.py L223-225）

```
变更前:
  def record_learning_feedback(ctx: RunContext[TotalAgentDeps]) -> dict:
      return _remember_terminal(ctx, TOOL_RECORD_LEARNING_FEEDBACK,
          tool_record_learning_feedback(ctx.deps.state))

变更后:
  def record_learning_feedback(
      ctx: RunContext[TotalAgentDeps],
      score: float = None,
      weak_points: list[str] = None,
      knowledge_mastery: list[dict] = None,
      feedback_note: str = "",
  ) -> dict:
      payload = ctx.deps.state.setdefault("payload", {})
      if score is not None:
          payload["score"] = float(score)
      if weak_points:
          payload["weak_points"] = list(weak_points)
      if knowledge_mastery:
          # 结构: [{"knowledge": "xxx", "mastery_label": "weak", "score": 0.3, "evidence": "..."}]
          payload["knowledge_mastery"] = list(knowledge_mastery)
      if feedback_note:
          payload["feedback_note"] = str(feedback_note)
      return _remember_terminal(ctx, TOOL_RECORD_LEARNING_FEEDBACK,
          tool_record_learning_feedback(ctx.deps.state))
```

**修改 `tool_record_learning_feedback`**（agent_tools.py L2633）

```
变更: 透传 payload 中的新字段到 _record_step_status
  (当前已透传，但 payload 里没有这些字段——加上参数后 LLM 可填)
```

**修改 `_record_step_status` / `_append_learning_event`**（agent_tools.py L2519-2536）

```
变更:
  event_entry["payload"].update({
      "score": payload.get("score"),                    # ← 新
      "weak_points": payload.get("weak_points"),        # ← 新
      "knowledge_mastery": payload.get("knowledge_mastery"),  # ← 新
      "feedback_note": payload.get("feedback_note"),    # ← 新
  })
```

**修改 `build_study_graph_changes_from_resource_event`**（study_graph_task.py）

```
变更:
  接收新字段:
  - score: float = None        → 调整 mastery 变化幅度
  - weak_points: list[str]     → 标记薄弱知识点
  - knowledge_mastery: list[dict] → 结构化掌握度，直接映射到 study graph 节点
  - feedback_note: str         → 辅助日志/审计

  逻辑:
  if knowledge_mastery:
      for item in knowledge_mastery:
          找到 study graph 中匹配 item["knowledge"] 的节点
          → 更新 mastery_score = item["score"]
          → 更新 mastery_label = item["mastery_label"]
  elif weak_points:
      for point in weak_points:
          找到匹配节点 → 标记为 weak
```

### 1.3 数据流

```
LLM 观察: "用户对 RowKey 设计理解很深(0.9)，但隐私保护混淆了(0.3)"

→ record_learning_feedback(
    score=0.75,
    knowledge_mastery=[
      {"knowledge": "RowKey 设计", "mastery_label": "mastered", "score": 0.9,
       "evidence": "用户能准确解释 Salt 和 Hash 的区别"},
      {"knowledge": "隐私保护", "mastery_label": "weak", "score": 0.3,
       "evidence": "用户将匿名化和加密混淆"},
    ],
    feedback_note="整体理解力强，隐私保护需补充"
  )

→ _append_learning_event → manifest event 含完整 knowledge_mastery
→ build_study_graph_changes_from_resource_event → 更新两个知识树节点
```

### 1.4 测试用例

```
TC1.1: record_learning_feedback(score=0.8, weak_points=["隐私保护"])
       → event payload 含 score 和 weak_points
TC1.2: record_learning_feedback(knowledge_mastery=[{...}])
       → event payload 含结构化掌握度
       → study graph 节点 mastery_score 被更新
TC1.3: record_learning_feedback() 无参调用 → 兼容当前行为（仅标记 completed）
TC1.4: knowledge_mastery 中 knowledge 不匹配任何节点 → 静默跳过，不崩溃
TC1.5: 旧 study graph（无 knowledge_mastery 逻辑）→ 降级正常运行
```

---

## 阶段 2：新增 `note_profile_observation` 工具

### 2.0 新增常量

```python
# agent_contracts.py

TOOL_NOTE_PROFILE_OBSERVATION = "note_profile_observation"
```

### 2.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 新增 | 注册 `note_profile_observation` 工具 |
| `tasks/total_agent/agent_tools.py` | 新增 | `tool_note_profile_observation` 函数 |
| `tasks/learning_profile/storage.py` | 改 | 已有 `merge_profile_update`，确保被 Task 层暴露 |

### 2.2 函数级收口

**新增 `tool_note_profile_observation`**（agent_tools.py）

```
输入（LLM 参数）:
  learning_style: str = ""         — 观察到的学习风格
  comprehension_level: str = ""    — 理解力水平变化
  weak_points: list[str] = None    — 新增薄弱知识点
  strong_points: list[str] = None  — 强项知识点
  note: str = ""                   — 自由文本备注

内部逻辑:
  1. 组装 observation dict
  2. 调用 profile_storage.merge_profile_update(user_id, syllabus_id, observation)
  3. 返回写入结果

返回:
  {
    "success": bool,
    "updated_fields": [...],    — 被更新的画像字段列表
    "note_id": str,             — 观察记录 ID
  }
```

**注册为 Agent 工具**（agent_runtime.py）

```python
@agent.tool
def note_profile_observation(
    ctx: RunContext[TotalAgentDeps],
    learning_style: str = "",
    comprehension_level: str = "",
    weak_points: list[str] = None,
    strong_points: list[str] = None,
    note: str = "",
) -> dict:
    """记录你对用户学习特征的观察。非必调——仅在注意到值得记录的变化时使用。
    这些观察会合并到用户画像中，影响后续推荐的质量。"""
    return tool_note_profile_observation(
        ctx.deps.state,
        learning_style=learning_style,
        comprehension_level=comprehension_level,
        weak_points=weak_points or [],
        strong_points=strong_points or [],
        note=note,
    )
```

### 2.3 数据流

```
Agent 观察: "用户偏好实操，对理论讲解不耐烦，理解力在中高级，隐私保护薄弱"

→ note_profile_observation(
    learning_style="practical",
    comprehension_level="intermediate_high",
    weak_points=["隐私保护"],
    strong_points=["RowKey 设计", "HBase 架构"],
    note="用户主动跳过理论章节，直接要练习"
  )

→ merge_profile_update(existing_profile, observation)
  → profile_summary.learning_style 调整权重
  → profile_summary.bottleneck_topics 追加
  → profile_summary.practice_ability 更新
```

### 2.4 测试用例

```
TC2.1: note_profile_observation(weak_points=["隐私保护"])
       → profile 文件/DB 中 bottleneck_topics 含 "隐私保护"
TC2.2: note_profile_observation(learning_style="practical")
       → profile 的 learning_style 更新
TC2.3: 空调用 → success=True, updated_fields=[]（不报错）
TC2.4: 两次调用同一字段 → merge 而非覆盖
TC2.5: 新字段不影响 profile 其他字段 → 只增不减
```

---

## 阶段 3：注册 `list_my_resources` 工具

### 3.0 无需新增常量

### 3.1 影响的文件范围

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/total_agent/agent_runtime.py` | 新增 | 注册 `list_my_resources` 工具 |
| `tasks/total_agent/agent_tools.py` | 改 | 已有 `find_personal_resources`，包装为工具函数 |

### 3.2 函数级收口

**新增 `tool_list_my_resources`**（agent_tools.py）

```
基于现有 find_personal_resources，增加参数：

输入（LLM 参数）:
  resource_type: str = ""       — 过滤类型: "documents"|"quiz"|"mindmap"|"coding_practice"|"ppt"
  knowledge_item: str = ""      — 过滤知识点关键词
  include_feedback: bool = False — 是否包含用户反馈（如有）

内部逻辑:
  1. 从 payload 或 generative_list API 获取用户资源
  2. 按 resource_type / knowledge_item 过滤
  3. 若 include_feedback，附加资源的使用反馈（如 quiz 得分）
  4. 返回精简列表（每项 title + type + created_at）

返回:
  {
    "success": bool,
    "resources": [
      {"resource_id": str, "resource_type": str, "title": str,
       "topic": str, "created_at": int, "feedback": dict|None},
    ],
    "count": int,
  }
```

**注册为 Agent 工具**（agent_runtime.py）

```python
@agent.tool
def list_my_resources(
    ctx: RunContext[TotalAgentDeps],
    resource_type: str = "",
    knowledge_item: str = "",
    include_feedback: bool = False,
) -> dict:
    """查看已生成的个人学习资源。可过滤类型和知识点。"""
    return tool_list_my_resources(
        ctx.deps.state,
        resource_type=resource_type,
        knowledge_item=knowledge_item,
        include_feedback=bool(include_feedback),
    )
```

### 3.3 测试用例

```
TC3.1: list_my_resources(resource_type="quiz") → 仅返回 quiz 类型
TC3.2: list_my_resources(knowledge_item="RowKey") → 返回包含 RowKey 的资源
TC3.3: list_my_resources(include_feedback=True) → 返回含反馈数据的资源
TC3.4: 无资源 → 返回空列表 success=true
```

---

## 阶段 4：验证

### 4.1 构建验证

```
TC4.1: npm run build 零错误
TC4.2: Python 语法无错误
TC4.3: 现有 test_personal_recommendation_api.py + test_plan_lifecycle.py 全过
```

### 4.2 功能验证

```
TC4.4: Agent 调用 record_learning_feedback(knowledge_mastery=[...])
       → study graph 节点 mastery 被更新
TC4.5: Agent 调用 note_profile_observation(weak_points=[...])
       → profile bottleneck_topics 被更新
TC4.6: Agent 调用 list_my_resources(resource_type="documents")
       → 返回文档列表
TC4.7: 三个新工具在 message_history 中跨轮可见
TC4.8: 无参调用完全兼容现有行为
```

---

## 附录：不变清单

- ✅ 现有 `record_learning_feedback` 无参调用行为不变（只标记 completed）
- ✅ `find_personal_resources` 原有逻辑不变（新工具只是包装）
- ✅ `merge_profile_update` 合并逻辑保留（只增不减）
- ✅ 前端不变——工具参数变化对前端透明
- ✅ 旧 agent 路径（`run_total_agent`）不变
