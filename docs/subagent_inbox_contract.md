# 总 Agent → 子 Agent 收口 Contract

将总 Agent 中三个旁路收口为对子 Agent 的正确调用。

---

## ⚠️ 误伤保护条款（实施前必读）

以下 6 项是 f5da32f 提交中建立的行为，施工中**不得删除、不得降级、不得改变计算口径**。

| # | 保护项 | 当前位置 | 施工要求 |
|---|--------|---------|---------|
| 1 | `learning_records[]` append + 增量 signals/overall_score/term_familiarity | `agent_tools.py` L2668-L2735 | 注册为 Agent tool，行为等价 |
| 2 | weak/strong points → personal_syllabus suggestion + `maybe_apply` 门禁 | `agent_tools.py` L2873-L2920 | 注册为 Agent tool，触发条件不变 |
| 3 | `record_learning_feedback` 四个参数 `score` / `weak_points` / `knowledge_mastery` / `feedback_note` | `agent_runtime.py` L241-265 | **不删除、不重命名** |
| 4 | `answer_records[]` 追加到 profile | `quiz_attempts.py` L121-L131 | 注册为 Agent tool，原调用点改为委托 |
| 5 | `merge_profile_update(existing, new)` 从 existing 起步合并 | `storage.py` L55 | **不动** |
| 6 | `resource_usage[]` 写入 | `blueprint/user_api.py` L400-433 | **不动**。前端直接触发，不在本次收口范围 |

---

## 当前状态全景

```
总 Agent (agent_tools.py)
  │
  ├─ tool_run_learning_recommendation
  │     → prt.run_recommendation_route_from_payload()  ← 直调确定性函数
  │     ❌ 未调 run_personal_recommendation_agent()
  │
  ├─ tool_record_learning_feedback → _record_step_status
  │     ├─ prt.update_learning_plan_step_status()      ← 正确，不动
  │     ├─ sgt.submit_learning_tree_changes()          ← 旁路，应调 student_agent
  │     └─ save_personal_profile()                      ← 旁路，应调 profile_agent
  │
  └─ tool_note_profile_observation
        → merge_profile_update + save_personal_profile  ← 旁路，应调 profile_agent
        ❌ 未调 run_learning_profile_agent()
```

```
不动的工具（设计正确）:
  tool_accept_learning_plan          → prt.accept_recommendation_path     ✅ DB 写入
  tool_get_next_learning_task        → prt.get_active_learning_plan       ✅ DB 读取
  tool_generate_current_step_resource → generative_task                   ✅ agent.run_sync()
  tool_list_my_resources             → generative_task.load_manifest      ✅ 文件读取
  tool_skip_current_step             → _record_step_status(SKIPPED)       ✅ 同上
  tool_abandon_learning_plan         → prt.abandon_learning_plan          ✅ DB 更新
```

---

## 阶段 1：profile_agent 收口

核心思路：f5da32f 验证了 8 个正确的 profile 操作函数。将它们注册为 profile_agent 的 `@agent.tool`。`apply_*` 先确定性写事实，再调 `run_learning_profile_agent(state)`。Agent 按固定闭环执行：load → compute → assemble → merge → save。

```
总 Agent / quiz_attempts
  │
  ▼
apply_*()                          ← service 层，纯参数包装
  │ 组装 state
  ▼
run_learning_profile_agent(state)  ← agent.run_sync()
  │
  ├─ load_existing_profile
  ├─ read_personal_syllabus
  ├─ init_personal_syllabus
  ├─ append_syllabus_suggestion
  ├─ maybe_apply_syllabus_progress
  ├─ ensure_term_table
  ├─ merge_profile_update
  └─ save_personal_profile
  │
  ▼
返回给调用方
```

### 1.0 新增常量

```python
# agent_contracts.py
TOOL_CALL_PROFILE_AGENT = "call_profile_agent"
# 替换 TOOL_NOTE_PROFILE_OBSERVATION = "note_profile_observation"
```

### 1.1 影响的文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/total_agent/agent_contracts.py` | 改 | 常量重命名 |
| `tasks/total_agent/agent_runtime.py` | 改 | 工具注册 `note_profile_observation` → `call_profile_agent` |
| `tasks/total_agent/agent_tools.py` | **删** | `_ensure_syllabus_term_table` 整体、`tool_note_profile_observation` 函数体、`_record_step_status` 中 L2668-L2735 |
| `tasks/total_agent/agent_tools.py` | 改 | `_record_step_status` 改为委托 `apply_learning_event`；新增 `tool_call_profile_agent` |
| `tasks/quiz_attempts.py` | 改 | answer_records 直写段替换为委托 `apply_answer_records` |
| `tasks/learning_profile/agent_runtime.py` | **加** | 新注册 8 个 `@agent.tool`，保留已有 `compute_features` / `assemble_profile` |
| `tasks/learning_profile/agent_runtime.py` | **改** | Agent system prompt 更新为固定闭环引导 |

### 1.2a Agent system prompt 更新

```
当前:
  "Context loading, event normalization, and profile persistence "
  "are handled before and after you run. "
  "Call compute_features then assemble_profile."

更新为:
  "你是学习画像 Agent。收到事件后按固定闭环执行：
   1. load_existing_profile — 读取已有画像
   2. read_personal_syllabus（需要时 init）
   3. 基于 event 字段写入事实要素
   4. ensure_term_table — 确保术语表可用
   5. compute_features → assemble_profile — 全量计算派生字段
   6. merge_profile_update — 从已有画像起步合并
   7. save_personal_profile — 原子落账
   不要跳过任何步骤。"
```

| `tasks/learning_profile/service.py` | **加** | `apply_learning_event()` + `apply_profile_observation()` + `apply_answer_records()` + `_ensure_syllabus_term_table` 迁入 |

### 1.2 新增 Agent 工具

将 f5da32f 验证过的 8 个函数注册为 profile_agent 的 `@agent.tool`：

| 工具名 | 来源 | 作用 |
|--------|------|------|
| `load_existing_profile` | `storage.py` | 读取已有画像 JSON |
| `read_personal_syllabus` | `personal_syllabus.py` | 读周次大纲 |
| `init_personal_syllabus` | `personal_syllabus.py` | 初始化周次大纲 |
| `append_syllabus_suggestion` | `personal_syllabus.py` | 追加周次掌握度建议 |
| `maybe_apply_syllabus_progress` | `personal_syllabus.py` | 门禁检查推进周次 |
| `ensure_term_table` | 从 `agent_tools.py` 迁入 | LLM 提取学科术语表 + 子串匹配算 term_familiarity |
| `compute_features` | `agent_tools.py` 已有 | 从 normalized events 全量计算 feature_bundle |
| `assemble_profile` | `agent_tools.py` 已有 | 从 feature_bundle 组装完整 profile dict |
| `merge_profile_update` | `storage.py` | 从 existing 起步逐 key 合并 |
| `save_personal_profile` | `storage.py` | 原子写（tmp → rename） |

### 1.3 apply_* 入口

每个 `apply_*` 分两步——确定性写事实，然后 best-effort 调 Agent 算派生字段：

```
apply_learning_event:
  ① 确定性写事实:
     load_existing_profile → append learning_record → save_personal_profile
  ② run_learning_profile_agent(state):
     → compute_features → assemble_profile → merge → save
     （best-effort，失败不回滚①）
```

```python
def apply_learning_event(user_id: int, syllabus_id: int, event: dict) -> dict:
    # ① 确定性写事实——完整搬运 f5da32f 计算口径
    existing, _ = load_existing_profile(user_id, syllabus_id)
    if not existing:
        existing = {}

    # 1a. 追加 learning_record
    record = _build_learning_record(event)
    existing.setdefault("learning_records", []).append(record)

    # 1b. 增量计算 signals（active_days_7d, avg_duration_minutes）
    _compute_signals(existing)

    # 1c. 增量计算 overall_score = mean(learning_record_scores)
    _compute_overall_score(existing)

    # 1d. 增量计算 term_familiarity（术语表 + 子串匹配）
    _compute_term_familiarity(existing, syllabus_id)

    save_result = save_personal_profile(user_id, syllabus_id, existing)

    # ② best-effort 调 Agent 算派生字段
    try:
        state = _build_profile_state(user_id, syllabus_id, "learning_feedback", event)
        agent_result = run_learning_profile_agent(state)
        agent_error = ""
    except Exception as exc:
        agent_result = None
        agent_error = str(exc)

    return {
        "success": bool(save_result),
        "profile_path": save_result.get("profile_path") if save_result else None,
        "profile_agent_ran": agent_result is not None,
        "profile_agent_error": agent_error,
    }
```

```python
def apply_profile_observation(user_id: int, syllabus_id: int, observation: dict) -> dict:
    # ① 确定性写事实——完整搬运 f5da32f 计算口径
    existing, _ = load_existing_profile(user_id, syllabus_id)
    if not existing:
        existing = {}

    # 1a. merge observation 到已有画像
    merged = merge_profile_update(existing, observation)

    # 1b. weak/strong points → personal_syllabus suggestion
    if observation.get("weak_points") or observation.get("strong_points"):
        _push_personal_syllabus_suggestions(user_id, syllabus_id, observation, merged)

    save_result = save_personal_profile(user_id, syllabus_id, merged)

    # ② best-effort 调 Agent 算派生字段
    try:
        state = _build_profile_state(user_id, syllabus_id, "profile_observation", observation)
        agent_result = run_learning_profile_agent(state)
        agent_error = ""
    except Exception as exc:
        agent_result = None
        agent_error = str(exc)

    return {
        "success": bool(save_result),
        "profile_path": save_result.get("profile_path") if save_result else None,
        "profile_agent_ran": agent_result is not None,
        "profile_agent_error": agent_error,
    }
```

`_push_personal_syllabus_suggestions` 内部逻辑（来自 agent_tools.py L2873-L2920）：
- weak_points → week 级 `append_suggestion("weak")`
- strong_points → week 级 `append_suggestion("mastered")`
- 触碰的周调 `maybe_apply_progress(ps, week)` → 门禁检查

这些也属于确定性阶段。Agent 失败不回滚已落账的 observation 和 suggestion。

```python
def apply_answer_records(user_id: int, syllabus_id: int, answer_records: list[dict]) -> dict:
    # ① 确定性写事实
    existing, _ = load_existing_profile(user_id, syllabus_id)
    if not existing:
        existing = {}
    existing.setdefault("answer_records", []).extend(answer_records)
    save_result = save_personal_profile(user_id, syllabus_id, existing)

    # ② best-effort 调 Agent
    try:
        state = _build_profile_state(user_id, syllabus_id, "quiz_attempt",
                                      {"answer_records": answer_records})
        agent_result = run_learning_profile_agent(state)
        agent_error = ""
    except Exception as exc:
        agent_result = None
        agent_error = str(exc)

    return {
        "success": bool(save_result),
        "profile_path": save_result.get("profile_path") if save_result else None,
        "profile_agent_ran": agent_result is not None,
        "profile_agent_error": agent_error,
    }
```

三个 `apply_*` 统一返回：
```python
{
    "success": bool,                # 确定性写事实是否成功
    "profile_path": str | None,     # 画像文件路径
    "profile_agent_ran": bool,      # Agent 是否成功执行
    "profile_agent_error": str,     # Agent 失败原因，成功为空
}
```

```python
def _build_profile_state(user_id: int, syllabus_id: int, event_type: str, event: dict) -> dict:
    # 1. 加载现有画像
    existing, existing_path = load_existing_profile(user_id, syllabus_id)
    if not existing:
        existing = {}

    # 2. 从现有画像提取事实字段（步骤①已写入，这里只读取，不重复注入）
    learning_records = existing.get('learning_records', [])
    answer_records = existing.get('answer_records', [])
    resource_usage = existing.get('resource_usage', [])

    # 4. 构建完整 state（同 build_learning_profile）
    user = get_user_by_id(user_id)
    user_syllabuses = _resolve_user_syllabuses(user_id, syllabus_id)
    profile_scope = _build_profile_scope(user_syllabuses)
    history_entries = collect_history_entries(user_id, syllabus_id)
    loaded_personal_syllabuses = load_personal_syllabus_rows(user_id, syllabus_id)

    return {
        'user_id': user_id,
        'syllabus_id': syllabus_id,
        'user': user,
        'user_syllabuses': user_syllabuses,
        'profile_scope': profile_scope,
        'existing_profile': existing,
        'existing_profile_path': existing_path,
        'existing_profile_loaded': True,
        'learning_records': learning_records,
        'answer_records': answer_records,
        'resource_usage': resource_usage,
        'history_entries': history_entries,
        'history_loaded': True,
        'loaded_personal_syllabuses': loaded_personal_syllabuses,
        'personal_syllabus_loaded': True,
        'dialogue_texts': [],
        'learning_goal': '',
        'now_ts': int(time()),
        'normalized_events': {},
        'feature_bundle': {},
        'profile': None,
        'profile_path': None,
        'profile_saved': False,
        'tool_trace': [],
        # 事件标识
        'event_type': event_type,
        'event': event,
    }
```

关键：`learning_records` / `answer_records` / `resource_usage` 从 `existing` 提取而非 API 传参——这是上次发现 `compute_features` 一直算空的根因。

### 1.4 调用方收口

**总 Agent（agent_tools.py）：**

`_record_step_status` L2668-L2735 删除，替换为：
```python
from tasks.learning_profile.service import apply_learning_event
apply_learning_event(user_id, syllabus_id, {
    "step_title": step_title, "score": score_val,
    "knowledge_mastery": km_items,
    "started_at": _utc_timestamp(), "duration_minutes": 20,
})
```

`tool_note_profile_observation` 替换为：
```python
def tool_call_profile_agent(state, learning_style="", comprehension_level="",
                            weak_points=None, strong_points=None, note="") -> dict:
    from tasks.learning_profile.service import apply_profile_observation
    return apply_profile_observation(user_id, syllabus_id, {
        "learning_style": learning_style, "comprehension_level": comprehension_level,
        "weak_points": weak_points, "strong_points": strong_points, "note": note,
    })
```

`_ensure_syllabus_term_table` 迁出至 `learning_profile/service.py`。

**quiz_attempts.py：**

L121-L131 删除，替换为：
```python
if answer_records:
    try:
        from tasks.learning_profile.service import apply_answer_records
        apply_answer_records(int(user_id), int(syllabus_id), answer_records)
    except Exception:
        pass
```

### 1.5 测试用例

```
P1.1: apply_learning_event → Agent 处理
  Given: user_id=1, syllabus_id=8, event={step_title:"RowKey设计", score:0.8}
  Then:  run_learning_profile_agent 被调用
         profile.learning_records 新增 1 条
         profile.signals.active_days_7d >= 1

P1.2: Agent 失败不回滚事实写入
  Given: ① 确定性写入已完成
         run_learning_profile_agent 抛异常
  Then:  profile.learning_records 已追加新记录（①已落账）
         返回 profile_agent_ran=False
         主流程不受影响

P1.3: apply_profile_observation 合并 + 周次推进
  Given: week 3 content 包含 "递归"
  When:  observation={weak_points: ["递归"]}
  Then:  week 3 suggestion 新增 {suggested_competance: "weak"}

P1.4: apply_answer_records 委托
  Given: answer_records=[{question:"...", correct:true}]
  Then:  profile.answer_records 追加新记录

P1.5: 触发完整性
  Given: 生成资源 → 记录反馈 → 提交答题 → 阅读文档
  Then:  profile 包含 learning_records + answer_records + resource_usage
```

---

## 阶段 2：student_agent 收口

### 2.0 新增常量

无。

### 2.1 影响的文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/total_agent/agent_tools.py` | **删** | `_record_step_status` L2628-L2666 手搓段 |
| `tasks/total_agent/agent_tools.py` | **加** | `_map_knowledge_mastery_to_detected_topics` + 委托调用 |

### 2.2 函数收口

#### 2.2.1 `_map_knowledge_mastery_to_detected_topics(items) → list[dict]`

```
knowledge_mastery[i].knowledge       → detected_topics[i].title
knowledge_mastery[i].score           → detected_topics[i].confidence (clamp [0,1])
knowledge_mastery[i].mastery_label   → detected_topics[i].signal
  "mastered"                           "mastered"
  "weak"                               "struggled"
  "learning"/其他                       "learned"
```

#### 2.2.2 `_record_step_status` 修改

L2628-L2666 整段删除，替换为：
```python
knowledge_mastery = _safe_list(payload.get("knowledge_mastery"))
if knowledge_mastery and syllabus_id:
    try:
        from tasks.study_graph.student_agent import run_student_agent
        detected_topics = _map_knowledge_mastery_to_detected_topics(knowledge_mastery)
        if detected_topics:
            run_student_agent({
                "user_id": int(user_id), "syllabus_id": int(syllabus_id),
                "source_kind": "total_agent",
                "detected_topics": detected_topics,
                "events": [], "rag_context": [], "parent_candidates": [],
                "timestamp": _utc_timestamp(),
            })
    except Exception:
        pass
```

#### 2.2.3 `record_learning_feedback` 参数保护

`agent_runtime.py` L241-265 的四个参数 **不删不重命名**。

### 2.3 测试用例

```
S1.1: 映射基本转换
  Given: [{knowledge:"HDFS", mastery_label:"weak", score:0.6}]
  Then:  [{title:"HDFS", confidence:0.6, signal:"struggled"}]

S1.2: Agent 调用成功 → 有 parent edge
  Given: detected_topics=[{title:"MapReduce", confidence:0.9, signal:"mastered"}]
  Then:  study_graph_node 新增, study_graph_edge 新增 parent_of

S1.3: 低置信度过滤
  Given: detected_topics=[{title:"冷门", confidence:0.4}]
  Then:  changes 长度=0（evidence_score < 0.60）

S1.4: 异常静默
  Given: run_student_agent 内部异常
  Then:  except → pass, 主流程不受影响
```

---

## 阶段 3：recommendation_agent 收口

### 3.0 新增常量

```python
TOOL_CALL_RECOMMENDATION_AGENT = "call_recommendation_agent"
# 替换 TOOL_RUN_LEARNING_RECOMMENDATION
```

### 3.1 影响的文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/total_agent/agent_contracts.py` | 改 | 常量重命名 |
| `tasks/total_agent/agent_runtime.py` | 改 | 工具注册重命名 |
| `tasks/total_agent/agent_tools.py` | 改 | `tool_run_learning_recommendation` → 委托 `run_personal_recommendation_agent` |

### 3.2 函数收口

```python
def tool_call_recommendation_agent(state):
    # try: run_personal_recommendation_agent(payload)
    # except / 返回空 → fallback: prt.run_recommendation_route_from_payload(payload)
    # ensure_recommendation_snapshot(...)
```

关键设计：Agent 调用失败或返回空 → fallback 到确定性路径。推荐是核心用户路径。

### 3.3 测试用例

```
R1.1: Agent 正常调用
R1.2: Agent 失败 → fallback 确定性路径，推荐正常返回
```

---

## 变更总览

```
阶段 1 (profile):
  agent_tools.py               删 ~130 行, 加 ~40 行
  quiz_attempts.py             删 ~10 行, 加 ~5 行
  learning_profile/agent_runtime.py  加 8 个 @agent.tool
  learning_profile/service.py  加 3 个 apply_* + _ensure_syllabus_term_table
  agent_contracts.py           改 1 常量
  agent_runtime.py             改 1 工具注册

阶段 2 (student):
  agent_tools.py               删 ~42 行, 加 ~25 行

阶段 3 (recommendation):
  agent_tools.py               改 ~30 行
  agent_contracts.py           改 1 常量
  agent_runtime.py             改 1 工具注册
```

```
收口后:

总 Agent
  ├─ call_recommendation_agent  → run_personal_recommendation_agent()  ✅ agent.run_sync()
  ├─ call_profile_agent         → apply_profile_observation()          ✅ agent.run_sync()
  ├─ record_learning_feedback   → apply_learning_event()              ✅ agent.run_sync()
  │                              → run_student_agent()                 ✅ agent.run_sync()
  ├─ accept_learning_plan       → 不动
  ├─ generate_resource          → 不动
  ├─ skip_current_step          → 不动
  └─ abandon_learning_plan      → 不动
```
  Then:  profile 包含 learning_records + answer_records + resource_usage
