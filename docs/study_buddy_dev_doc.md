# 学伴 Agent 关闭报告

本文档记录当前学伴 Agent 的关闭状态。学伴在总 Agent 之外运行，维护独立学习记录树、标签式记忆和消息历史；它可以在学习事件后生成一条主动消息，也可以通过独立接口陪学生对话。若旧计划文档和本文档重复，以本文档为当前实现事实。

## 当前状态

学伴 Agent 的核心链路已经落地：

```text
active learning plan + study graph features
  -> build_buddy_tree
  -> load buddy memory tags
  -> load recent buddy messages
  -> study_buddy_agent
  -> persist tree / memory / messages
  -> return reply or buddy_message
```

学伴的定位是陪聊和轻量提醒，不承担答疑、辅导、内容生成或学习决策。它不修改 Total Agent 的 plan，不写学习画像，不写学习成长树，只读取当前学习计划和学习树特征来构造自己的上下文。

“比当前学生稍微多学了一点的学霸”是学伴的人设方向，但当前实现不是给学伴维护一棵独立的“学霸知识树”。当前学伴树是学伴看学生时使用的学习地图：它让小觉知道学生正在走哪条主线、已经有哪些旁支基础、哪些点可以轻轻提醒，而不是声明小觉真实掌握了这些知识。这个边界能避免学伴越界成答疑老师或替学生做决策。

## 文件范围

核心实现：

- `tasks/study_buddy_task.py`
  - task 门户，提供主动触发、事件通知、独立对话和消息读取。
- `tasks/study_buddy/buddy_agent.py`
  - pydantic-ai Agent 组装、学伴系统提示词、上下文拼接、主动消息和独立对话。
- `tasks/study_buddy/tree.py`
  - 从 active plan 和 study graph features 构建三层学伴学习记录树。
- `tasks/study_buddy/tree_store.py`
  - `tree.json` 原子读写。
- `tasks/study_buddy/memory.py`
  - `buddy_memory.jsonl` 标签式记忆增删查和上限裁剪。
- `tasks/study_buddy/messages.py`
  - `buddy_messages.jsonl` 对话/主动消息历史读写。
- `tasks/study_buddy/contracts.py`
  - schema version、区域名、文件名、数量上限和 Agent 名称常量。
- `blueprint/study_buddy_api.py`
  - `/api/study_buddy/*` HTTP 接口。

联动实现：

- `tasks/total_agent/agent_runtime.py`
  - 总 Agent 结果阶段最多触发一条学伴事件消息；事件为空时使用学习记录树变化 fallback。
- `tasks/total_agent/agent_tools.py`
  - 资源生成成功后可即时通知学伴 `resource_ready`，并避免同一轮重复发送。
- `blueprint/admin_api.py`
  - 管理员学生进度接口可返回 `buddy_tree`，供前端与学习成长树并列展示。

## 对外入口

HTTP 入口：

```text
POST /api/study_buddy/chat
GET|POST /api/study_buddy/messages
POST /api/study_buddy/proactive
```

task 入口：

```python
buddy_chat(user_id, syllabus_id, message, plan=None, study_graph_features=None)
trigger_study_buddy(user_id, syllabus_id, plan=None, study_graph_features=None)
notify_study_buddy_event(user_id, syllabus_id, event_type, payload=None, plan=None, study_graph_features=None)
list_buddy_messages(user_id, syllabus_id, limit=30)
```

`/api/study_buddy/chat` 会读取 active learning plan 和 study graph features，调用 `buddy_chat` 后返回 `reply`、`messages` 和 `memory_tags_written`。`/api/study_buddy/proactive` 是调试用主动触发入口，返回 `buddy_message` 和最新消息列表。`/api/study_buddy/messages` 只读消息历史。

## 学伴树

学伴树 schema version 为 `study_buddy.tree.v1`，持久化到：

```text
study_buddy/user_{user_id}/syllabus_{syllabus_id}/tree.json
```

树分三层：

- `trunk`：来自 active plan 的 steps，保留 `step_id`、`node_id`、`title`、`outcomes`、`status`、`order_index`。
- `learned`：来自 study graph features 的 mastered/learned/practiced topics，且不和 trunk 重复。
- `explore`：来自 weak/stale/recently_grown topics，且不和 trunk 或 learned 重复。

三层语义对应“小觉稍微走在前面一点”的效果：

- `trunk` 让小觉看到当前 active step 和后续 pending step，因此它能自然提醒“下一步大概会接到哪里”。
- `learned` 不是小觉自己的已掌握清单，而是学生已经具备、可被小觉拿来鼓励或串联的基础。
- `explore` 不是正式推荐结果，而是小觉可以轻轻点一下的相邻薄弱点、过期点或最近生长点。

学伴树只服务学伴上下文和展示，不反写学习成长树。`proactive_buddy_message` 每次会保存最新树；只有 trunk 状态发生 `pending -> active` 或 `active -> completed` 等变化时才生成树变化主动消息。

当前不建议把学伴树改成独立进度树。若后续想强化“学霸已经提前多学一点”的感觉，更合适的增量是新增一个只读 `ahead` / `preview` 区域，从未采纳候选路径、syllabus 后继节点或课程级共性 mastered 节点中抽取 1-3 个轻量预览点；它仍应只用于语气和提醒，不反写 plan、profile 或 study graph。

## 状态机

学伴有三套轻量状态：

| 状态对象 | 字段 | 取值 | 写入方 | 读取方 |
|---|---|---|---|---|
| 学伴 trunk step | `regions.trunk[].status` | `pending`、`active`、`completed`、`skipped` | 从 active learning plan 投影 | 学伴 Agent、前端/管理端展示 |
| 消息来源 | `messages[].from` / `source` | `user`、`buddy`、`proactive` / `chat`、`proactive`、`event` | `append_buddy_message` | 学伴上下文、前端消息列表 |
| 记忆 tag | `action` | `created`、`updated`、`deleted`、`not_found`、`empty` | `create_memory_tag`、`delete_memory_tag` | 学伴 Agent、测试/调试 |

学伴树变化检测：

```text
load old tree
build new tree from active plan + study graph features
save new tree
compare trunk status
  pending -> active     => proactive message candidate
  active -> completed   => proactive message candidate
  no tracked transition => no tree message
```

消息状态机：

```text
chat:
  user message -> from=user, source=chat
  buddy reply  -> from=buddy, source=chat

tree proactive:
  buddy message -> from=proactive, source=proactive

event proactive:
  buddy message -> from=proactive, source=event, metadata.event_type=<event_type>
```

记忆 tag 状态机：

```text
create_memory_tag:
  empty tag       -> action=empty, success=false
  existing tag    -> action=updated, refresh last_referenced_at
  new tag         -> action=created, append and prune oldest if over limit

delete_memory_tag:
  empty tag       -> action=empty, success=false
  existing tag    -> action=deleted
  missing tag     -> action=not_found
```

边界：

- trunk step 状态是 Learning Plan 的只读投影；学伴不直接改 step status。
- `proactive` 消息是体验层消息，不改变 Total Agent 的主业务状态。
- 记忆 tag 是模型可调用工具的结果，不是用户可见的长期档案全文。

## 记忆和消息

记忆持久化到：

```text
study_buddy/user_{user_id}/syllabus_{syllabus_id}/buddy_memory.jsonl
```

每条记忆是一个 tag，包含 `tag`、`created_at`、`last_referenced_at`。学伴 Agent 拥有两个内部工具：

```text
create_memory_tag
delete_memory_tag
```

记忆规则：

- 空 tag 会被拒绝。
- 重复 tag 不新增，只刷新 `last_referenced_at`。
- 最多保留 30 条，超过后裁掉最旧 tag。
- 返回时按 `last_referenced_at` 倒序。

消息持久化到：

```text
study_buddy/user_{user_id}/syllabus_{syllabus_id}/buddy_messages.jsonl
```

消息最多保留 80 条。`from` 字段归一为 `user`、`buddy` 或 `proactive`；主动事件消息的 `metadata.event_type` 会记录事件类型。

## 总 Agent 联动

Total Agent 每轮最多给学伴写入一条主动消息：

- 资源生成工具成功时，`tool_generate_current_step_resource` 可立即发送 `resource_ready`。
- 最终结果阶段会按优先级从学习事件中选一条，例如 `plan_accepted`、`learning_feedback_recorded`、`step_skipped`、`recommendation_ready`、`question_answered`。
- 如果事件消息没有产出，才回退到 `trigger_study_buddy` 的树变化检测。

主动消息会被写入 `buddy_messages.jsonl`，并在 Total Agent 结果中以 `buddy_message` 和 `buddy_event` 返回。该消息是附加体验，不影响 Total Agent 的主结果、学习计划推进或资源生成状态。

## 边界

- 学伴不参与 Total Agent tool chain 的决策，不改变 intent。
- 学伴不生成正式学习资源，不写 resource manifest。
- 学伴不负责知识问答；需要系统讲解时应把学生引回主窗口资料、练习或答疑能力。
- 学伴读取 plan 和 study graph features，但不反写这两类数据。
- 学伴记忆是标签式轻量记忆，不是长期全文聊天档案；最近消息只作为短上下文输入。
- `POST /api/study_buddy/proactive` 当前用于调试或手动触发，正式产品流程优先走 Total Agent 事件联动。

## 测试覆盖

当前默认测试不调用真实 LLM，覆盖重点在纯函数、持久化和门户行为：

```text
tests/test_study_buddy.py
```

已覆盖：

- `build_buddy_tree` 构造 trunk / learned / explore。
- 空 plan、空 features 的稳定行为。
- `save_buddy_tree` / `load_buddy_tree` 往返。
- memory tag 创建、重复刷新、删除、排序和上限裁剪。
- buddy message 写入、读取和 source/from 归一。
- `buddy_chat` 持久化用户消息和学伴回复。
- `trigger_study_buddy` 持久化 proactive 消息。
- `notify_study_buddy_event` 持久化单条事件消息和 metadata。

Total Agent 侧覆盖：

- `test_total_agent_buddy_event_selector_prefers_single_highest_priority_event`
- `test_total_agent_final_result_notifies_only_one_buddy_event`
- `test_total_agent_resource_tool_notifies_buddy_immediately`

## 当前非阻塞项

- 学伴回复质量依赖真实模型，默认 CI 只验证结构和持久化，不验证生成文本质量。
- 学伴树的 `associated_trunk` 仍是轻量文本匹配，足够支撑当前展示和上下文，但不是严格图谱推理。
- 消息历史和记忆当前以文件系统持久化，尚未迁移到数据库。
