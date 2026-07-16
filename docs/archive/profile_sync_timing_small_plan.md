# Profile Sync 时序修复 — Small Plan

## 问题

`build_learning_profile` 里先 save profile 再 sync weeks。

```
save profile (week_items=全0) → sync (写 personal syllabus ✅)
                                  ↑
                          前端读的是前面存的旧 profile
```

前端只读 profile JSON，不读 personal syllabus。两套数据脱节。

## 方案

**调换顺序：sync weeks → 合并进 state['profile'] → 再 save。**

```
_build_weeks_from_personal(state)   ← 改名后
  1. sync_knowledge_to_weeks → 更新 personal syllabus
  2. 重读 personal syllabus → rebuild week_signals
  3. 合并进 state['profile']['knowledge_mastery']
  (不存盘)

_tool_save_or_update_profile(state)  ← 之后才存
```

## 改动

单文件 `service.py`：

1. `_sync_weeks_after_save` 改名为 `_merge_weeks_into_profile`，去掉最后的 save
2. 三个调用点：`_merge_weeks_into_profile(state)` 移到 `_tool_save_or_update_profile(state)` **之前**

调用处变为：
```python
_merge_weeks_into_profile(state)      # 先同步 week 数据到 state['profile']
_tool_save_or_update_profile(state)   # 再存盘（此时 week_items 已更新）
```

## 风险

无。`_merge_weeks_into_profile` 失败时静默降级，state['profile'] 保持原样，不影响原有存储流程。
