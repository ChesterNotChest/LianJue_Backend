# Profile Agent 确定性重构 — Implementation Contract

## Phase 0: 新增常量

无。不新增 env var 或常量——纯重构。

## Phase 1: 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/learning_profile/service.py` | 修改 | `build_learning_profile` 内增阶段一、阶段三调用 |
| `tasks/learning_profile/agent_runtime.py` | 修改 | 移除 4 个冗余 tool 注册，精简 `output_validator` |
| `tasks/learning_profile/agent_tools.py` | 修改 | 删除 3 个函数 + 4 个已迁移函数，仅保留 `_tool_compute_features` / `_tool_assemble_profile` |

**命名规则**：`_tool_` 前缀仅用于注册在 pydantic-ai agent 上的工具。确定性函数去掉该前缀，移至 `service.py`（或保留在 `agent_tools.py` 中去掉前缀）。

## Phase 2: 函数级完整数据流

```
总 agent 传 payload → build_learning_profile(user_id, sid, events)
  │
  │  ═══ 阶段一：工作区就位（确定性） ═══
  │
  ├─[P1] _load_existing_profile_context(state)
  ├─[P2] _ensure_personal_syllabus(state)
  ├─[P3] _load_personal_syllabus_context(state)
  ├─[P4] _normalize_events(state)
  │
  │  ═══ 阶段二：profile agent pydantic-ai 工具链 ═══
  │
  ├─ run_learning_profile_agent(state)
  │     ├─[A1] compute_features(state)
  │     └─[A2] assemble_profile(state)
  │
  │  ═══ 阶段三：显示能力闭合（确定性） ═══
  │
  ├─[Q1] _merge_weeks_into_profile(state)
  └─[Q2] _save_or_update_profile(state)

return state['profile'] → total agent
```

## Phase 3: 函数级收口

### 3.0 命名规范——`_tool_` 前缀收敛

重构后，`_tool_` 前缀**仅用于注册在 pydantic-ai agent 上的工具**。确定性函数去掉前缀，归入 `service.py`：

| 当前名 | 新名 | 位置 |
|--------|------|------|
| `_tool_load_existing_profile_context` | `_load_existing_profile_context` | `service.py` |
| `_tool_ensure_personal_syllabus` | `_ensure_personal_syllabus` | `service.py`（已有） |
| `_tool_load_personal_syllabus_context` | `_load_personal_syllabus_context` | `service.py` |
| `_tool_normalize_events` | `_normalize_events` | `service.py` |
| `_merge_weeks_into_profile` | 不变（本无 `_tool_`） | `service.py`（已有） |
| `_tool_save_or_update_profile` | `_save_or_update_profile` | `service.py` |
| `_tool_compute_features` | 不变 | `agent_tools.py` |
| `_tool_assemble_profile` | 不变 | `agent_tools.py` |

`agent_tools.py` 最终仅保留 `_tool_compute_features` 和 `_tool_assemble_profile` 两个 agent tool 函数。

### 3.1 `service.py` — `build_learning_profile` 改动

**阶段一插入点**：`state` 构建后、`run_learning_profile_agent(state)` 前。

当前已有 `_tool_load_existing_profile_context(state)` 调用。补充 P2-P4：

```python
# 阶段一：工作区就位
if syllabus_id is not None:
    _tool_load_existing_profile_context(state)        # P1 已有
_tool_ensure_personal_syllabus(state)                  # P2 新增调用
_tool_load_personal_syllabus_context(state)            # P3 新增调用
_tool_normalize_events(state)                          # P4 新增调用
```

阶段一执行后，`state` 中以下字段就位：
- `existing_profile` / `existing_profile_path`
- personal syllabus 存在于磁盘，`UserSyllabus.personal_syllabus_path` 已设
- `loaded_personal_syllabuses` 含 `(sid, personal_json, syllabus_json)`
- `normalized_events` 含规范化事件数据

**阶段三插入点**：`run_learning_profile_agent(state)` 返回后、`return state['profile']` 前。当前已有 merge + save，保持不变。

### 3.2 `agent_runtime.py` — 精简 tool 注册

**删除 4 个 tool 注册**（从 `get_learning_profile_agent()` 中移除）：

| 删除 | 原因 |
|------|------|
| `load_history_context` | 空操作 |
| `load_personal_syllabus_context` | 移至阶段一 P3 |
| `read_personal_syllabus` | 与 P3 重复 |
| `init_personal_syllabus` | 与 P2 重复 |

**保留 2 个**：

```
compute_features
assemble_profile
```

**`output_validator` 调整**：去掉 `profile_saved` 检查，只检查 `state['profile']` 是否存在：

```python
# 前
if state.get('syllabus_id') is not None and not state.get('profile_saved'):
    raise ModelRetry('You must call save_or_update_profile...')

# 后：删除此条件。save 已移至阶段三确定性执行。
```

### 3.3 `agent_tools.py` — 删除冗余函数

删除 3 个函数定义及对应注册逻辑：

| 函数 | 行数估算 |
|------|----------|
| `_tool_load_history_context` | ~15 |
| `_tool_read_personal_syllabus_context` | ~15 |
| `_tool_init_personal_syllabus_context` | ~15 |

不修改任何保留函数的签名或逻辑。

## Phase 4: 测试用例

### 4.1 Agent tool 选择测试

**文件**：`tests/test_learning_profile_agent_choice.py`

**用例 1 — agent 仍能调用核心工具**：
- 运行 coverage，确认 `compute_features` 和 `assemble_profile` 被成功调用
- 验证移除了的 4 个工具不再出现在 agent 的 tool 列表中

### 4.2 画像构建集成测试

**文件**：`tests/test_profile_personal_syllabus_full_chain.py`

**用例 2 — 确定性阶段正常执行**：
- 调用 `build_learning_profile(uid, sid, ...)` 传入学习/答题记录
- 验证 `state['loaded_personal_syllabuses']` 不为空（P3 生效）
- 验证 `state['normalized_events']` 不为空（P4 生效）
- 验证返回的 profile 中 `week_items` 至少有一个 `score > 0`（阶段三生效）

### 4.3 Seed 回归

**用例 3 — medium 种子正常产出**：
- 运行 `demo_medium` seed
- 验证 `[ENSURE]` `[MERGE]` `[SYNC]` debug 输出完整
- 验证 `overall_score > 0.2`，`mastered_weeks` 非空
