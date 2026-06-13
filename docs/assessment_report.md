# Profile Agent 工具链去冗余评估

## 现状

profile agent（pydantic-ai agent）注册了 9 个 `sequential=True` 工具。pydantic-ai 每步工具调用后都要将结果交回 agent 模型做"下一步调什么"的决策，9 步工具链至少产生 8 次 agent roundtrip。其中 `compute_features` / `assemble_profile` 内部还各自调了 LiteLLM completion 做语义计算。

```
agent 决策 → 调 tool → agent 决策 → 调 tool → ... × 9
  (部分 tool 内部有 LiteLLM completion)
```

## 分类

| 工具 | 性质 | 可移除？ |
|------|------|:---:|
| `load_existing_profile_context` | 读磁盘文件 | ❌ |
| `load_history_context` | 读历史数据 | ❌ |
| `load_personal_syllabus_context` | 读/初始化个人大纲 | ❌ |
| `read_personal_syllabus` | 读个人大纲详情 | ❌ |
| `init_personal_syllabus` | 初始化（已是 load_personal 的子步骤） | ❌ |
| `normalize_events` | 清洗学习/答题记录 | ❌ |
| `compute_features` | 计算画像特征维度 | ✅ |
| `assemble_profile` | 拼装完整画像结构 | ✅ |
| `save_or_update_profile` | 写磁盘文件 | ❌ |

**7/9 是确定性操作，不依赖 pydantic-ai agent 决策，也不依赖 LiteLLM completion。**

## 建议

### 阶段一：总 agent payload 传入后，profile agent 尚未阅读前

总 agent 已将 `dialogue_text`、`learning_records`、`answer_records` 等通过 `build_learning_profile` 传入。
profile agent 尚未启动 pydantic-ai 工具链。此时 `build_learning_profile` 直接执行——不经过 profile agent。

```
load_existing_profile_context
ensure_personal_syllabus          ← 含 init 逻辑
load_personal_syllabus_context
normalize_events
```

### 阶段二：profile agent 工具链

profile agent 启动，仅保留 2 个 pydantic-ai 工具。

```
compute_features
assemble_profile
```

### 阶段三：工具输出返还给 total agent 前

profile agent 的 pydantic-ai 调用已返回，`state['profile']` 就绪。
在结果返还给 total agent 之前，`build_learning_profile` 直接执行收口——不经过 profile agent。

```
merge_weeks_into_profile          ← sync + 重建 week_signals
save_or_update_profile            ← 统一落盘
```

### 删除

```
load_history_context              ← 空操作
read_personal_syllabus            ← 与 load_personal_syllabus_context 重复
init_personal_syllabus            ← 与 ensure_personal_syllabus 重复
```

## 收益

| 维度 | 前 | 后 |
|------|----|----|
| agent roundtrip | 8-9 次 | 2 次 |
| profile agent 耗时 | 30-90s | 10-20s |
| 失败模式 | agent "忘记" 调某个工具 | 确定性阶段不依赖 agent 决策 |
| 可调试性 | 黑箱 tool trace | 确定性阶段有明确日志 |

## 整合后工具集（5 个步骤）

### 阶段一：总 agent → 预处理（profile agent 尚未阅读）

| # | 步骤 | 输入 | 输出 |
|---|------|------|------|
| P1 | `load_existing_profile_context` | `state['user_id']`, `state['syllabus_id']` | `state['existing_profile_path']`, `state['existing_profile']` |
| P2 | `ensure_personal_syllabus` | `state['user_id']`, `state['syllabus_id']` | personal syllabus JSON 在磁盘创建（若缺失），`UserSyllabus.personal_syllabus_path` 设值 |
| P3 | `load_personal_syllabus_context` | `state['user_id']`, `state['syllabus_id']` | `state['loaded_personal_syllabuses']` = `[(sid, personal_json, syllabus_json), ...]` |
| P4 | `normalize_events` | `state['learning_records']`, `state['answer_records']`, `state['resource_usage']`, `state['dialogue_texts']` | `state['normalized_events']` = `{all_events, learning_events, answer_events, resource_events, all_texts, question_texts}` |

### 阶段二：profile agent 工具

| # | 工具 | 输入 | 输出 |
|---|------|------|------|
| A1 | `compute_features` | `state`（含 P1-P4 全部数据） | `state['feature_bundle']`, `state['profile']`（初步） |
| A2 | `assemble_profile` | `state['feature_bundle']`, `state['profile']` | `state['profile']`（完整画像 dict） |

### 阶段三：工具输出 → 收口（返还 total agent 前）

| # | 步骤 | 输入 | 输出 |
|---|------|------|------|
| Q1 | `merge_weeks_into_profile` | `state['profile']`, `state['user_id']`, `state['syllabus_id']` | `state['profile']['knowledge_mastery']` 含同步后的 week_items |
| Q2 | `save_or_update_profile` | `state['profile']`, `state['profile_path']` | `state['profile_saved']=True`，profile JSON 落盘 |

### 删除

| 工具 | 原因 |
|------|------|
| `load_history_context` | 空操作 |
| `read_personal_syllabus` | 与 P3 重复 |
| `init_personal_syllabus` | 与 P2 重复 |

## 完整数据流

```
总 agent 传 payload → build_learning_profile(user_id, sid, events)
  │
  │  ═══ 阶段一：profile agent 尚未阅读 ═══
  │
  ├─[P1] load_existing_profile_context(state)
  │       └─ 读 profiles/<sid>-<uid>.json → state['existing_profile']
  │
  ├─[P2] ensure_personal_syllabus(state)
  │       └─ personal syllabus 不存在? → init → 拷贝 syllabus → 写盘
  │       └─ 重读 UserSyllabus → personal_syllabus_path 正确捕获
  │
  ├─ build profile_scope（此时路径已正确）
  │
  ├─[P3] load_personal_syllabus_context(state)
  │       └─ 读 personal syllabus + syllabus JSON
  │       └─ state['loaded_personal_syllabuses'] = [(sid, personal, syllabus)]
  │
  ├─[P4] normalize_events(state)
  │       └─ learning_records → learning_events（含 knowledge_points）
  │       └─ answer_records → answer_events（含 correct/score）
  │       └─ resource_usage → resource_events（含 action/duration）
  │       └─ dialogue_text → question_texts
  │       └─ state['normalized_events'] 就绪
  │
  │  ═══ 阶段二：profile agent 工具链 ═══
  │
  ├─ run_learning_profile_agent(state)
  │     │
  │     ├─[A1] compute_features(state)
  │     │       └─ compute_learning_profile_bundle()
  │     │            ├─ build_answer_mastery → by_knowledge_point
  │     │            ├─ build_week_signals → week_items（此时全 none）
  │     │            ├─ infer_learning_style / practice_ability / ...
  │     │            └─ state['feature_bundle'], state['profile'] 产出
  │     │
  │     └─[A2] assemble_profile(state)
  │             └─ 整理 profile 结构 → state['profile'] 完整
  │
  │  ═══ 阶段三：返还 total agent 前 ═══
  │
  ├─[Q1] merge_weeks_into_profile(state)
  │       └─ sync_knowledge_to_weeks(uid, sid)
  │            ├─ 读 by_knowledge_point
  │            ├─ LiteLLM 语义对齐 + 规则 fallback → week_scores
  │            └─ 写 personal syllabus 的 competance
  │       └─ 重读 personal syllabus → build_week_signals
  │       └─ 合并进 state['profile']['knowledge_mastery']
  │            ├─ week_items → 非零 score
  │            ├─ overall_score → 含 syllabus 分量
  │            └─ mastered_weeks → 非空
  │
  └─[Q2] save_or_update_profile(state)
          └─ profile JSON 落盘（含正确 week 数据）
          └─ state['profile_saved'] = True

return state['profile'] → total agent
```

## 风险

- `compute_features` / `assemble_profile` 内部依赖 `state` 中 P1-P4 数据。阶段一已确保就位。
- `compute_learning_profile_bundle` 已在 `agent_tools.py` 中实现——`_tool_compute_features` + `_tool_assemble_profile` 就是薄封装。
- profile agent 的 `output_validator` 需调整为只检查 `state['profile']` 是否存在（不再检查 `profile_saved`）。

## 实施建议

1. `service.py::build_learning_profile` 中，阶段一加 P1-P4，阶段三加 Q1-Q2
2. `agent_runtime.py` 中只留 A1-A2 工具注册
3. `agent_tools.py` 中删除 `load_history_context` / `read_personal_syllabus` / `init_personal_syllabus`
4. 分步提交测试验证
