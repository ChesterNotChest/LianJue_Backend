# tool_end status 设计：漏斗分析

## 当前状态

`tool_end` 事件不带 `status` 字段，前端从 `result.success` 推断：
- `success=true` → `"succeeded"`
- `success=false` → `"failed"`（一刀切）

## 全部 error_code 漏斗

从 `agent_tools.py` 全量扫描 18 个 error_code，按语义分三类：

### 第一层：真正的执行失败 → 应显示 "失败"
后端返回 `success: false`，前端应显式标记 `failed`。

| error_code | 来源工具 | 触发场景 |
|---|---|---|
| `missing_user_id` | 多个 | 请求参数缺 user_id |
| `missing_recommendation_result` | accept | 未注入推荐结果 |
| `tool_failed` | `_tool_result` 默认 | 工具执行异常（通用） |
| `accept_learning_plan_failed` | accept | 后端 accept 逻辑失败 |
| `context_failed` | load_context | 上下文加载失败 |
| `resource_generation_failed` | generate_resource | 全部资源任务失败 |
| `resource_generation_exception` | generate_resource | 生成过程抛异常 |
| `invalid_generation_result` | generate_resource | 返回数据结构非法 |
| `resource_task_failed` | generate_resource | 单个资源任务失败 |
| `missing_answer_text` | answer_question | 回答内容为空 |

### 第二层：状态驱动的空结果 → 应显示 "跳过"
后端返回 `success: false`，但**不是错误**，是当前状态没有可执行的内容。语义上等同于 `skipped`。

| error_code | 来源工具 | 触发场景 |
|---|---|---|
| `no_active_plan` | get_next_task / record_feedback / abandon | 用户没有活跃学习计划 |
| `no_next_task` | get_next_task | 计划所有步骤已完成 |
| `no_target_step` | record_feedback | 没有可更新的步骤 |
| `no_resource_tasks` | generate_resource | 无资源任务可执行 |

### 第三层：守卫拒绝 → 应显示 "拒绝" 或归入 "跳过"
后端主动拒绝执行，不是错误。当前 ENUM 无 `rejected`，可归入 `skipped`。

| error_code | 来源 | 触发场景 |
|---|---|---|
| `active_plan_exists` | service.py guard | 已有活跃计划，禁止生成新推荐 |
| `stale_snapshot` | snapshot.py guard | 前端持有过期快照，拒绝 accept |

### 第四层：降级警告 → 目前 success 仍为 true
这些不返回 `success: false`，只追加 warnings，不影响 status。

| warning_code | 来源 |
|---|---|
| `PROFILE_WARNING_NOT_FOUND` | load_context |
| `PROFILE_WARNING_READ_FAILED` | load_context |

## 结论

**不需要新增 ENUM 值。** 前端现有的 `succeeded | failed | skipped` 够用。

需要的是：后端在 `tool_end` 事件中，根据 `error_code` 语义给出 `status`：

```
success=true                    → "succeeded"
success=false, no_active_plan   → "skipped"
success=false, no_next_task     → "skipped"
success=false, no_target_step   → "skipped"
success=false, no_resource_tasks→ "skipped"
success=false, active_plan_exists→ "skipped"
success=false, stale_snapshot   → "skipped"
success=false, 其余             → "failed"
```

映射规则很简单：**白名单制**——特定 error_code 映射 `skipped`，其余 `failed`。

不需要扩展前端 `ToolStatus`，不需要新增后端 ENUM。现有的 5 个值（pending/running/succeeded/failed/skipped）完全覆盖。
