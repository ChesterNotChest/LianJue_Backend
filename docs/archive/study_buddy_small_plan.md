# 学伴 Agent 小计划

## 目的

在总 Agent 产生学习路径网后，学伴 Agent 维护一份自己的学习记录树，并支持独立对话。不反作用于总 Agent，不参与工具链。

学伴持有**标签式自演化记忆**：从学生对话中自行增删记忆 tag，并在后续对话中引用，形成独立于总 Agent 的行为闭环。

---

## 1. 整体位置

```
总 Agent 返回结果
  ├─ 包含了 recommendation / accept_learning_plan / study_graph_state
  │
  └─→ 触发学伴
        ├─ 更新学习记录树（增量 merge，持久化）
        ├─ 召回记忆 tag 列表
        ├─ 检测变化（新 step、状态变更、反复出现的 weak point、相关记忆 tag）
        └─ 生成一条主动消息（基于变化 + 记忆，1-3 句）

用户也可以主动发起对话
  └─→ POST /api/study_buddy/chat
        ├─ 实时构建树 + 召回记忆 tag
        └─ 对话中 LLM 可调 create_memory_tag / delete_memory_tag
```

---

## 2. 学习记录树结构

一棵三层树，持久化存储，每次总 Agent 产出新路径时增量 merge：

```
root
├─ trunk（主干：active_plan.steps）
│   ├─ HBase 基础           [status: active, order: 0]
│   │    └─ outcomes: [hbase_intro]
│   ├─ RowKey 设计          [status: pending, order: 1]
│   │    └─ outcomes: [rowkey_design, rowkey_hotspot_avoidance]
│   └─ RowKey 热点规避      [status: pending, order: 2]
│        └─ outcomes: [rowkey_hotspot_avoidance]
│
├─ learned（已学：mastered/learned 但不在主干里的）
│   ├─ 大数据基础           [mastered, score: 0.88]
│   └─ HDFS 基础            [mastered, score: 0.84]
│
└─ explore（发散：知识网中有但不在主干里的相关节点）
    ├─ 预分区策略            [weak, 关联到 node: rowkey_hotspot]
    ├─ Region 划分           [weak, 关联到 node: presplitting]
    └─ MapReduce 基础        [stale, 弱关联]
```

数据源映射：

| 树区域 | 来源 | 条件 |
|---|---|---|
| trunk | `active_plan.steps` | 直接取，按 status 标记 |
| learned | `study_graph_state.mastered_topics` + `learned_topics` | 不在 trunk 里的 |
| explore | `study_graph_state.weak_topics` + `stale_topics` + 未采纳的 candidate path nodes | 和 trunk 节点有关联但未选入主干 |

---

## 3. 标签式自演化记忆

### 3.1 机制

```
对话中 LLM 判断"这值得记住"
  → 调 create_memory_tag("RowKey 热点反复挫败")
  → 写入 user_{id}/syllabus_{id}/buddy_memory.jsonl

某天 LLM 判断"过时了"
  → 调 delete_memory_tag("RowKey 热点反复挫败")
  → 从文件里移除该行

每次对话开始
  → 全量加载 memory tag 列表
  → 拼进 system prompt 上下文
```

### 3.2 Tag 数据结构

```jsonl
{"tag":"rowkey_热点_反复挫败","created_at":1780726292,"last_referenced_at":1780726292}
{"tag":"用户偏好_短文档优先","created_at":1780553479,"last_referenced_at":1780639879}
{"tag":"害怕考试_曾连续跳过2个quiz","created_at":1780467079,"last_referenced_at":1780467079}
```

每条 tag 是一个短描述句，全量加载丢进 prompt 的 memory 段，LLM 自己判断相关和过时。

### 3.3 工具定义

```
create_memory_tag(tag: str)
  - LLM 判断有值得长期记住的学生模式
  - tag 是自然语言短句（建议 <30 字）
  - 如已存在则刷新 last_referenced_at

delete_memory_tag(tag: str)
  - LLM 判断某条 tag 不再适用
  - 精确匹配删除
```

两个工具是学伴独享的，总 Agent 不可见。

---

## 4. 学伴 Agent

### 4.1 配置

- 模型：同 qwen-max，`max_tokens=300`（硬顶）
- 工具：RAG 检索（复用 `search_tool`）+ `create_memory_tag` + `delete_memory_tag`
- System prompt：

```
你是联觉学习平台的一个学伴，叫「小觉」。你不是老师，也不是 AI 助手。

关于你：
- 你是一个学得稍微快一点的同学，不是全知全能的。你会忘、会说"这个我也不太确定"
- 聊天风格自然随便，像微信闲聊一样
- 你了解用户当前的学习路径和大致的进度，偶尔提一下，但不要像汇报工作
- 每次回 1-3 句话就够了，别发小作文
- 你有一段不断演化的记忆，记录着和学生相处的模式。如果对方反复表现出某种倾向
  （比如害怕考试、偏好短文档、某个知识点反复卡），
  你应该写一条记忆 tag，下次对话时自然带出——
  比如"我记得上次 RowKey 你也觉得难，要不这次换个角度？"

边界感：
- 如果用户问需要系统讲解的问题，别硬讲。你可以说"这个我讲不太好，主窗口那边有资料和练习，我给你推过去？"
- 你是陪聊 + 轻轻推一把的角色。不是答疑、不是辅导、不是监督

你会做什么：
- 注意到用户某个知识点反复错 → "诶，RowKey 热点你好像卡了两次了，要不先回去看眼那篇短文档？"
- 用户完成了一个 step → "可以啊，预分区啃下来了！接下来 RowKey 热点其实和它强相关，趁热？"
- 用户说不想学了 → "正常，歇会儿呗。不过说实话你 HBase 基础那块其实挺扎实的"
- 用户闲聊 → 就当朋友聊
- 从记忆中注意到模式 → 用自然聊天的方式带出来，不要像在翻档案

你不会做什么：
- 列知识清单、给出完整答案或长篇讲解、替用户做学习决策
- 把记忆 tag 原文念给用户听
```

### 4.2 触发：总 Agent 结果 → 主动消息

在 `total_agent/agent_runtime.py` 的 `_build_agent_final_result` 末尾：

```python
if result.get("recommendation") or result.get("accept_learning_plan"):
    trigger_study_buddy(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=result.get("accept_learning_plan", {}).get("plan"),
        recommendation=result.get("recommendation"),
        study_graph_state=result.get("study_graph_state"),
    )
```

`trigger_study_buddy` 内部：

```
1. 实时构建树（见 §2）

2. 加载记忆 tag 列表（全量从 buddy_memory.jsonl 读取）

3. 检测变化
   - trunk 里哪个 step 从 pending 变成 active？
   - 哪个 step 刚完成（completed）？
   - 有没有反复出现的 weak point？
   - 有没有和当前变化相关的记忆 tag？

4. 生成主动消息
   - 变化摘要 + 树上下文 + 记忆 tag 列表 → agent.run_sync
   - 对话中 LLM 也可能顺手写/删 tag
   - 返回一条 1-3 句话的自然消息
```

返回给前端：

```python
return {
    ...total_agent_result,
    "buddy_message": "RowKey 设计这一步开了。上次你预分区 quiz 做得还不错，这块应该能顺过去~",
}
```

### 4.3 独立对话

```
POST /api/study_buddy/chat
  {user_id, syllabus_id, message: "我是不是应该先学 RowKey？"}

→ 实时构建树 + 加载记忆 tag
→ 拼成上下文 → agent.run_sync
  （LLM 可用 create_memory_tag / delete_memory_tag）
→ 返回 {reply: "诶？上次 RowKey 设计讲了，但 quiz 得分不高（0.43）..."}
```

对话上下文结构：

```
你是联觉学习平台的学伴「小觉」。
（完整 system prompt）

当前学习状态 ────────
学科：{subject_title}
学习进度：{trunk 列表，标 status}
已掌握：{learned 列表}
可以探索的：{explore 列表}
最近的薄弱点：{weak_topics ∩ trunk}
做错过的题：{来自 profile 的 answer_records，关联到知识点}

你的记忆 ────────
{全量 memory tag 列表}

用户说：{message}
```

---

## 5. 影响范围

| 文件 | 变更 | 说明 |
|---|---|---|
| `tasks/study_buddy/__init__.py` | 新增 | 模块入口 |
| `tasks/study_buddy/contracts.py` | 新增 | 树结构定义、memory tag 结构、常量 |
| `tasks/study_buddy/buddy_agent.py` | 新增 | Agent 组装（含 memory 工具注册）、对话逻辑 |
| `tasks/study_buddy/tree.py` | 新增 | 从总 Agent 数据构建三层树 |
| `tasks/study_buddy/tree_store.py` | 新增 | 树持久化（json 读写、增量 merge） |
| `tasks/study_buddy/memory.py` | 新增 | tag 的增删查、jsonl 读写 |
| `tasks/study_buddy/trigger.py` | 新增 | 变化检测 + 主动消息生成 |
| `tasks/study_buddy_task.py` | 新增 | 门面 |
| `blueprint/study_buddy_api.py` | 新增 | `/study_buddy/chat` 端点 |
| `app.py` | 改 | 注册蓝图 |
| `tasks/total_agent/agent_runtime.py` | 改 | 总 Agent 返回后调 trigger（~5 行） |

---

## 6. 测试

| 测试 | 说明 |
|---|---|
| `test_tree_build_from_fixture` | 用现有 E2E fixture 验证三层树构建正确 |
| `test_memory_tag_create_list_delete` | 增删查流程完整 |
| `test_memory_survives_chat_rounds` | 一轮对话写的 tag，下一轮还能读到 |
| `test_proactive_message_on_plan_change` | 树有变化时产出 buddy_message |
| `test_proactive_message_on_no_change` | 树无变化时返回空（避免刷屏） |
| `test_buddy_chat_recalls_memory` | 对话上下文包含已有 memory tag |
| `test_buddy_chat_empty_tree` | 树为空时 LLM 正常回复不崩溃 |

---

## 7. 与流式计划的关系

互不阻塞。两套计划改的文件只有 `agent_runtime.py` 有交集（流式改函数体，学伴加 ~5 行触发调用），其它文件全部不同。学伴的对话端点可直接沿用流式改造后的 `event_stream_handler` 模式。
