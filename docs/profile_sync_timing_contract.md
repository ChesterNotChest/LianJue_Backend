# Profile Sync 时序修复 — Implementation Contract

## Phase 0: 问题定位

`build_learning_profile` 中：

```
_tool_save_or_update_profile(state)   ← profile JSON 落盘 (week_items 全 0)
_sync_weeks_after_save(state)         ← personal syllabus 更新 (已来不及)
```

前端读的是先存的 profile JSON，week 层数据全是 save 之前的旧值。

## Phase 1: 文件范围

| 文件 | 操作 |
|------|------|
| `tasks/learning_profile/service.py` | 修改 `_sync_weeks_after_save`，调整 3 处调用顺序 |

单文件，无其他改动。

## Phase 2: 函数级数据流

```
build_learning_profile
  │
  ├─ run_learning_profile_agent(state)
  │     └─ state['profile'] 产出 (week_items 仍是旧值)
  │
  ├─ if state['profile'] and not saved:
  │     _merge_weeks_into_profile(state)    ← 1. 同步 personal syllabus → 回填 state['profile']
  │     │     │
  │     │     ├─ sync_knowledge_to_weeks   → 更新 personal syllabus JSON
  │     │     ├─ 重读 personal syllabus
  │     │     ├─ build_week_signals        → 重建 week 数据
  │     │     └─ 合并进 state['profile']['knowledge_mastery']
  │     │
  │     _tool_save_or_update_profile(state) ← 2. profile JSON 落盘 (含最新 week 数据)
  │
  └─ return state['profile']
```

## Phase 3: 函数收口

### `_merge_weeks_into_profile(state: dict) -> None`

**输入：** `state` — profile agent 运行后的 state dict，需含 `state['profile']`, `state['user_id']`, `state['syllabus_id']`

**输出：** 无。直接修改 `state['profile']['knowledge_mastery']`。

**内部逻辑：**

1. 取 `uid = int(state['user_id'])`, `sid = int(state['syllabus_id'])`
2. 若 sid 为 None 或 `state['profile']` 不存在 → return
3. try:
   - `sync_knowledge_to_weeks(uid, sid)` → 更新 personal syllabus JSON
   - 若 synced_weeks == 0 → return
   - `read_profile_personal_syllabus(uid, sid)` → 读更新后的 personal syllabus
   - `build_week_signals(personal, syllabus_json)` → 重建 week 数据
   - 合并 `overall_score`, `overall_level`, `week_items`, `mastered_weeks`, `weak_weeks` 到 `state['profile']['knowledge_mastery']`
   - **不存盘** — 由后续 `_tool_save_or_update_profile` 统一存
4. except: pass（静默降级）

### 调用点修改（3 处）

每一处当前为：
```python
_tool_save_or_update_profile(state)
_sync_weeks_after_save(state)
```

改为：
```python
_merge_weeks_into_profile(state)
_tool_save_or_update_profile(state)
```

## Phase 4: 测试

### 用例 1 — 存盘前 profile 已更新
- 调用 `build_learning_profile(uid, sid, ...)` with seed data
- 读 persisted profile JSON
- 验证 `knowledge_mastery.week_items` 至少有一周 `competance != "none"`
- 验证 `overall_score > 0.25`

### 用例 2 — 降级不崩
- monkeypatch `sync_knowledge_to_weeks` 抛异常
- 调用 `build_learning_profile`
- 验证 profile 正常保存（week_items 保持旧值但不崩）
