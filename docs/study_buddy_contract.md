# Study Buddy contract

> **状态：✅ 已实现**
> 学伴树已升级到 v2（trunk/learned/explore 三层 + mastery + buddy_notes），主动消息与独立对话均已闭环。详见 `study_buddy_dev_doc.md`。

本文档收口"学伴 Agent"的实现。它在总 Agent 之外维护独立学习记录树和标签式自演化记忆，支持主动消息推送和独立对话。

## 阶段 1：学习记录树构建与持久化

### 0. 常量定义

```python
# tasks/study_buddy/contracts.py

BUDDY_TREE_SCHEMA_VERSION = "study_buddy.tree.v1"
BUDDY_MEMORY_SCHEMA_VERSION = "study_buddy.memory.v1"

# 树区域标识
BUDDY_REGION_TRUNK = "trunk"       # 主干：active_plan.steps
BUDDY_REGION_LEARNED = "learned"   # 已学：mastered/learned 但不在主干
BUDDY_REGION_EXPLORE = "explore"   # 发散：weak/stale 相关节点

# 节点状态（复用 learning_plan 的 step status）
BUDDY_STEP_STATUS_ACTIVE = "active"
BUDDY_STEP_STATUS_PENDING = "pending"
BUDDY_STEP_STATUS_COMPLETED = "completed"

# 记忆文件路径模板
BUDDY_MEMORY_FILENAME = "buddy_memory.jsonl"
```

### 1. 影响的文件范围

新增：
- `tasks/study_buddy/__init__.py` — 模块入口
- `tasks/study_buddy/contracts.py` — 常量 + 数据结构定义
- `tasks/study_buddy/tree.py` — 树构建逻辑
- `tasks/study_buddy/tree_store.py` — 树持久化（json 读写）

修改：无

### 2. 函数级收口的完整数据流

```text
build_buddy_tree(user_id, syllabus_id, plan, study_graph_state)
  ├─ trunk: active_plan.steps → [{step_id, title, outcomes, status, order_index}]
  ├─ learned: study_graph_state.mastered_topics + learned_topics ∩ ¬trunk
  │            → [{title, signal, score, association: trunk_node}]
  └─ explore: study_graph_state.weak_topics + stale_topics
              → [{title, signal, association: trunk_or_learned_node}]

save_buddy_tree(user_id, syllabus_id, tree) → <backend_root>/study_buddy/user_{uid}/syllabus_{sid}/tree.json
load_buddy_tree(user_id, syllabus_id) → tree dict | None
```

### 3. 精确到输入输出的函数级收口

#### `build_buddy_tree(user_id, syllabus_id, plan, study_graph_state) -> dict`

输入：
```python
user_id: int
syllabus_id: int
plan: dict  # 来自 get_active_learning_plan() 或 accept_recommendation_path 的 plan
study_graph_state: dict  # 来自 get_learning_tree_features()
```

输出：
```json
{
  "schema_version": "study_buddy.tree.v1",
  "user_id": 161, "syllabus_id": 29,
  "updated_at": 1781276205,
  "regions": {
    "trunk": [
      {
        "step_id": "step_1", "node_id": "hbase_intro",
        "title": "HBase 基础", "outcomes": ["hbase_intro"],
        "status": "active", "order_index": 0
      }
    ],
    "learned": [
      {
        "title": "大数据基础", "signal": "mastered", "score": 0.88,
        "associated_trunk": ["hbase_intro"]
      }
    ],
    "explore": [
      {
        "title": "RowKey 热点", "signal": "weak",
        "associated_trunk": ["rowkey_design"]
      }
    ]
  }
}
```

内部逻辑：
1. `trunk`：直接从 `plan.steps` 取，按 `order_index` 排序
2. `learned`：遍历 `study_graph_state.mastered_topics` 和 `study_graph_state` 中 signal 为 `mastered` 或 `learned` 的节点。排除已在 trunk 中的（按 title 模糊匹配）。为每个节点计算与 trunk 的关联：如果节点的 title 或 parent_title 与某 trunk 节点的 title 或 outcomes 匹配，记为关联
3. `explore`：遍历 `weak_topics` 和 `stale_topics`。同样排除 trunk 中已有的。关联逻辑同上

#### `save_buddy_tree(user_id, syllabus_id, tree) -> str`

输出树文件路径。内部逻辑：`os.makedirs(dir, exist_ok=True)` + `json.dump` 原子写入。

#### `load_buddy_tree(user_id, syllabus_id) -> dict | None`

从文件读取，不存在返回 None。

### 4. 测试

```text
test_build_buddy_tree_from_fixture
  - 用 e2e_cases_amend 的 deep_student_state fixture 构建树
  - 断言 trunk/learned/explore 三区域非空
  - 断言 trunk 节点按 order_index 排序
  - 断言 learned 中不含 trunk_title 已在 trunk 中的节点

test_save_and_load_buddy_tree_roundtrip
  - 构建 → save → load → 断言字段一致

test_build_buddy_tree_empty_plan
  - plan 为空时 trunk 为空列表，不崩溃
```

## 阶段 2：标签式自演化记忆

### 0. 常量定义

```python
BUDDY_MEMORY_MAX_TAGS = 30  # 单用户最大记忆数
BUDDY_MEMORY_TAG_MAX_CHARS = 60  # 单条 tag 最大字符
```

### 1. 影响的文件范围

新增：
- `tasks/study_buddy/memory.py` — tag 的增删查

### 2. 函数级收口的完整数据流

```text
create_memory_tag(user_id, syllabus_id, tag: str)
  → 读取 buddy_memory.jsonl
  → 如已存在相同 tag 文本 → 刷新 last_referenced_at
  → 如不存在 → append 新行（created_at + last_referenced_at）
  → 如超过 MAX_TAGS → 删最旧

delete_memory_tag(user_id, syllabus_id, tag: str)
  → 读取 buddy_memory.jsonl
  → 精确匹配删除该行

load_memory_tags(user_id, syllabus_id) → list[dict]
  → 全量读取，按 last_referenced_at desc 排序
```

### 3. 精确到输入输出的函数级收口

#### `create_memory_tag(user_id, syllabus_id, tag: str) -> dict`

输入：
```python
user_id: int, syllabus_id: int
tag: str  # 自然语言短句，如 "RowKey 热点反复挫败"
```

输出：
```json
{"success": true, "tag": "RowKey 热点反复挫败", "action": "created", "total_tags": 3}
```

内部逻辑：
```text
1. tag = tag.strip()[:BUDDY_MEMORY_TAG_MAX_CHARS]
2. 读取 buddy_memory.jsonl（每行一条 JSON）
3. 遍历现有 tag，如文本完全相同 → 更新 last_referenced_at = now_ts，写回，返回 {action: "updated"}
4. 如不存在 → append {tag, created_at: now_ts, last_referenced_at: now_ts}
5. 如果总 tag 数 > MAX_TAGS → 删最旧（created_at 最小）的
6. 原子写回 buddy_memory.jsonl
```

#### `delete_memory_tag(user_id, syllabus_id, tag: str) -> dict`

```json
{"success": true, "tag": "...", "action": "deleted", "total_tags": 2}
```

内部逻辑：精确文本匹配，删该行，写回。不存在则返回 `{action: "not_found"}`。

#### `load_memory_tags(user_id, syllabus_id) -> list[dict]`

```json
[{"tag":"...", "created_at": ..., "last_referenced_at": ...}, ...]
```

### 4. 测试

```text
test_memory_tag_create_list_delete
  - create 3 tags → load 返回 3
  - create 已存在的 tag → 刷新 last_referenced_at，不新增
  - delete 1 tag → load 返回 2
  - delete 不存在的 tag → 不报错

test_memory_max_tags_pruning
  - create 35 tags → load ≤ 30，最旧的被删

test_memory_survives_roundtrip
  - create tags → 新 session → load 读到相同数据
```

## 阶段 3：学伴 Agent 组装

### 0. 常量定义

```python
BUDDY_AGENT_NAME = "study_buddy_agent"
BUDDY_AGENT_MAX_TOKENS = 300
BUDDY_SYSTEM_PROMPT = "..."  # 来自 small_plan.md §4.1
```

### 1. 影响的文件范围

新增：
- `tasks/study_buddy/buddy_agent.py` — Agent 组装、对话逻辑

### 2. 函数级收口的完整数据流

```text
build_buddy_agent() → pydantic_ai Agent
  ├─ model: build_openai_compatible_model(agent_name=BUDDY_AGENT_NAME)
  ├─ tools:
  │   ├─ create_memory_tag(tag: str)
  │   ├─ delete_memory_tag(tag: str)
  │   └─ search_learning_context(query: str)  # 复用 search_tool
  └─ system_prompt: BUDDY_SYSTEM_PROMPT

build_buddy_context(user_id, syllabus_id, plan, study_graph_state) → str
  → 构建树 + 加载 memory tags
  → 格式化为 system prompt 下挂的上下文段：
      "当前学习状态 ────────\n学科：{subject}\n学习进度：{trunk}\n已掌握：{learned}\n可以探索的：{explore}\n你的记忆 ────────\n{tags}"
```

### 3. 精确到输入输出的函数级收口

#### `build_buddy_agent() -> Agent`

内部逻辑：
```text
1. model = build_openai_compatible_model(agent_name="study buddy agent")
2. agent = Agent(model=model, system_prompt=BUDDY_SYSTEM_PROMPT, ...)
3. 注册工具：
   @agent.tool
   def create_memory_tag(ctx, tag: str) -> dict:
       return memory.create_memory_tag(ctx.deps.user_id, ctx.deps.syllabus_id, tag)

   @agent.tool
   def delete_memory_tag(ctx, tag: str) -> dict:
       return memory.delete_memory_tag(ctx.deps.user_id, ctx.deps.syllabus_id, tag)
4. return agent
```

#### `build_buddy_context(user_id, syllabus_id, plan, study_graph_state) -> str`

输入：用户 ID、大纲 ID、当前 plan dict、study graph features dict
输出：拼接好的上下文纯文本，附加到 system prompt 后面

内部逻辑：
```text
1. tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_state)
2. tags = load_memory_tags(user_id, syllabus_id)
3. trunk_lines = [f"{s['status']}: {s['title']}" for s in tree['regions']['trunk']]
4. learned_lines = [f"{n['signal']}({n.get('score',0):.0%}): {n['title']}" for n in tree['regions']['learned'][:8]]
5. explore_lines = [f"{n['signal']}: {n['title']}" for n in tree['regions']['explore'][:8]]
6. tag_lines = [t['tag'] for t in tags]
7. 用分隔符拼接 → 返回
```

### 4. 测试

```text
test_buddy_agent_builds_with_tools
  - build_buddy_agent() 返回 Agent，有 create_memory_tag / delete_memory_tag 工具

test_buddy_context_includes_tree_and_tags
  - create memory tags → build context → 文本含 tag 内容 + trunk 节点标题
```

## 阶段 4：主动消息 + 独立对话

### 0. 常量定义

```python
BUDDY_CHAT_MAX_REPLY_CHARS = 500  # max_tokens=300 的近似上限
```

### 1. 影响的文件范围

新增：
- `tasks/study_buddy/trigger.py` — 变化检测 + 主动消息生成
- `blueprint/study_buddy_api.py` — `/api/study_buddy/chat` 端点
- `tasks/study_buddy_task.py` — 门面

修改：
- `tasks/total_agent/agent_runtime.py` — 总 Agent 返回后调 trigger（~5 行）
- `app.py` — 注册蓝图

### 2. 函数级收口的完整数据流

```text
trigger_study_buddy(user_id, syllabus_id, plan, recommendation, study_graph_state)
  ├─ 加载旧树（如果存在）
  ├─ 构建新树
  ├─ 检测变化：
  │   ├─ trunk 中哪个 step 从 pending → active？
  │   ├─ 哪个 step 刚完成（→ completed）？
  │   └─ 有无反复出现的 weak point？
  ├─ 有变化 → 构建 prompt（变化摘要 + 树上下文 + memory tags）
  │         → agent.run_sync → buddy_message
  └─ 无变化 → buddy_message = ""

POST /api/study_buddy/chat
  {user_id, syllabus_id, message}
  ├─ 加载 active_plan + study_graph_state
  ├─ build_buddy_context(...) → 上下文
  ├─ agent.run_sync(user_message) → reply
  └─ 返回 {reply, memory_tags_written: [...]}
```

### 3. 精确到输入输出的函数级收口

#### `trigger_study_buddy(user_id, syllabus_id, plan, recommendation, study_graph_state) -> str | None`

输入：
```python
user_id: int, syllabus_id: int
plan: dict  # 当前 active plan
recommendation: dict | None  # 推荐结果（可能为 None）
study_graph_state: dict  # 学习树特征
```

输出：`str | None` — 1-3 句中文主动消息，或 None（无变化）

内部逻辑：
```text
1. old_tree = load_buddy_tree(user_id, syllabus_id)
2. new_tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_state)
3. save_buddy_tree(new_tree)  # 总是保存最新树

4. 变化检测（对比 old_tree.trunk vs new_tree.trunk）：
   a. 新 active: old 中是 pending，new 中是 active → "xxx 这一步开了"
   b. 新 completed: old 中是 active，new 中是 completed → "xxx 完成了"
   c. weak point 重复: explore 区域有和上次一样标记为 weak 的主题
   d. 如果有变化相关 memory tag，加入提示

5. 如果无变化 → return None

6. 构建 prompt:
   "学生状态有变化：{变化摘要}。
    当前在学：{trunk 列表}
    最近薄弱点：{explore 中的 weak}
    你的记忆：{tags}
    请根据以上变化，以学伴「小觉」的身份自然地说 1-3 句话。
    不要汇报、不要像通知、不要念出记忆原文。"

7. agent.run_sync(prompt) → reply
8. return reply (trim to 500 chars)
```

#### `POST /api/study_buddy/chat`

输入：
```json
{"user_id": 161, "syllabus_id": 29, "message": "我是不是应该先学 RowKey？"}
```

输出：
```json
{
  "success": true,
  "reply": "诶，其实上次那篇 HBase 基础你 quiz 做得还行啊。RowKey 可以先看，不过它和 Region 划分挺相关的，要不等主窗口那边推给你？",
  "memory_tags_written": [],
  "error_code": "",
  "error_message": ""
}
```

内部逻辑：
```text
1. 校验 user_id
2. plan = get_active_learning_plan(user_id, syllabus_id)
3. study_graph_state = get_learning_tree_features(user_id, syllabus_id)
4. context = build_buddy_context(user_id, syllabus_id, plan, study_graph_state)
5. agent = build_buddy_agent()
6. result = agent.run_sync(f"{BUDDY_SYSTEM_PROMPT}\n{context}\n\n用户说：{message}")
7. 提取 reply 文本
8. 检查对话中是否有 create/delete memory tag 的 tool call，记录到 memory_tags_written
9. 返回 {reply, memory_tags_written}
```

### 4. 测试

```text
test_proactive_message_on_plan_change
  - 旧树 trunk[0] pending, 新树 trunk[0] active → 产出非空 buddy_message

test_proactive_message_on_no_change
  - 新旧树完全相同时 → 返回 None

test_proactive_message_on_weak_point_repeat
  - explore 中同一 weak title 连续两次出现 → 消息提及

test_buddy_chat_recalls_memory
  - 先 create memory tag → chat 时上下文含该 tag

test_buddy_chat_empty_tree
  - 无 plan 且无 study graph → 对话不崩溃

test_buddy_chat_writes_memory
  - 对话中说"我老记不住 RowKey" → LLM 调 create_memory_tag → 返回含该 action

test_buddy_chat_deletes_memory
  - 对话中说"那个已经会了，不用再记" → LLM 调 delete_memory_tag → 返回含该 action
```

## 最终验收标准

- 总 Agent 推荐/步骤变更后，前端 SSE 流末尾多一个 `buddy_message` 字段
- 前端左下角学伴面板可独立发送消息并收到 1-3 句自然回复
- 学伴记忆在对话间持久保留
- 学伴不参与总 Agent 工具链，不修改 plan/study graph
