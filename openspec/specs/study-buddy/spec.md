# Study Buddy

学伴 Agent 模块。在 Total Agent 之外独立运行，维护独立的学习记录树、标签式记忆和消息历史。提供主动消息和独立对话。

## 定位与边界

- **陪聊和轻量提醒**，不承担答疑、辅导、内容生成或学习决策
- **不修改** Total Agent 的 plan、学习画像、学习成长树
- **只读取** 当前学习计划和学习树特征来构造自己的上下文
- 人设：比当前学生稍微多学了一点的学霸（"小觉"）

## API Endpoints

### POST /api/study_buddy/chat
与学伴进行独立对话。
- **Input**: `{user_id, syllabus_id, message: str}`
- **Output**: `{reply, messages: [...], memory_tags_written: [...]}`

### GET /api/study_buddy/messages
获取学伴消息历史。
- **Query**: `?user_id=N&syllabus_id=N&limit=30`
- **Output**: `{messages: [{role, content, source, created_at}]}`

### POST /api/study_buddy/messages
同 GET，支持 POST 方式。

### POST /api/study_buddy/proactive
手动触发学伴的主动消息（调试端点）。
- **Input**: `{user_id, syllabus_id}`
- **Output**: `{buddy_message, messages: [...]}`

## Data Flow

```
active learning plan + study graph features
  → build_buddy_tree (3 layers)
  → load buddy memory tags
  → load recent buddy messages
  → study_buddy_agent (pydantic-ai)
  → persist tree / memory / messages
  → return reply or buddy_message
```

## Buddy Tree (3 Layers)

```
tree.json: study_buddy/user_{user_id}/syllabus_{syllabus_id}/tree.json

trunk:  来自 active plan 的 steps
        {step_id, node_id, title, outcomes, status, order_index}

learned: 来自 study graph features 的 mastered/learned/practiced topics
         不重复 trunk

explore: 来自 weak/stale/recently_grown topics
         不重复 trunk 或 learned
```

### Trunk Step Status
```
pending → active → completed | skipped
```

只有 `pending→active` 或 `active→completed` 变化时，才生成树变化主动消息。

## Memory & Messages

```
buddy_memory.jsonl   — 最多 30 条标签式记忆 (tag CRUD)
buddy_messages.jsonl — 最多 80 条消息历史
```

消息来源标签：
- `source: chat | proactive`
- `role: user | buddy`

记忆标签动作：
- `created | updated | deleted | not_found | empty`

## Total Agent 联动

每轮最多一条主动消息。事件优先级：
1. 事件消息：`resource_ready` / `plan_accepted` / `learning_feedback_recorded` / `step_skipped` / `plan_abandoned`
2. Fallback：树变化检测（trunk 状态变化）

| 事件类型 | payload 字段 |
|---------|-------------|
| `plan_accepted` | `next_task_title`, `total_steps` |
| `learning_feedback_recorded` | `updated_step_title` |
| `resource_ready` | `resource_type` |
| `step_skipped` | (none) |
| `plan_abandoned` | (none) |

## Known Issues

- 事件 payload 极薄（0-2 字段），学伴缺乏上下文来生成有意义的主动消息
- 消息历史和记忆以文件系统持久化（未迁移到数据库）
- 学伴树的 `associated_trunk` 是轻量文本匹配，不是严格图谱推理

## Integration

- 读取 Learning Plan（trunk 层）
- 读取 Study Graph Features（learned/explore 层）
- 被 Total Agent 触发（事件通知 + 树变化检测）
- 被 Admin API 读取（学生进度接口返回 buddy_tree）
