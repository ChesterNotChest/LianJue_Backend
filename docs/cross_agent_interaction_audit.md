# 总 Agent ↔ 子 Agent 交互带宽审计

全量评估 Total Agent 与所有下游模块的交互通路。每个通路评估三维度：
**上行带宽**（总 Agent 能传什么）、**下行带宽**（子 Agent 返回什么）、**跨轮持久性**。

---

## 1. Recommendation Agent（推荐路径）

### 1.1 通路

```
total_agent: run_learning_recommendation
  → tool_run_learning_recommendation (agent_tools.py:1953)
    → prt.run_recommendation_route_from_payload(payload)
    → prt.ensure_recommendation_snapshot(...)
```

### 1.2 上行（总 Agent → 推荐 Agent）

写入: `payload["goals"]`, `payload["L_max"]`, `payload["K"]`, `payload["graph_name"]`

- `goals`: LLM 可从用户消息推断，或通过 `normalize_learning_goal_for_recommendation` 预处理
- 其他参数: payload 自动传递

**带宽评估：充足。** LLM 可通过 payload 传递学习目标。

### 1.3 下行（推荐 Agent → 总 Agent）

返回：完整 `recommendation` dict —— `graph.nodes`, `graph.edges`, `candidates`, `best_path`, `rag_overlay`, `planning_hints`

**带宽评估：数据充足但过重。** ~150KB（含完整 graph）→ message_history 接入后需瘦身。

### 1.4 跨轮持久性

- ✅ 完整结果持久化在 recommendation snapshot（磁盘/DB）
- ❌ 总 Agent 的 `state["recommendation_result"]` 跨轮丢失（code 层不 restore）
- ⚠️ `load_total_context` 不注入 pending recommendation（阶段 4 待修）

---

## 2. Profile Agent（用户画像）

### 2.1 通路

```
total_agent: load_total_context
  → tool_load_total_context (agent_tools.py:1767)
    → load_profile_summary(payload)
```

### 2.2 上行（总 Agent → 画像 Agent）

写入: 无。画像 Agent 是纯读取——`user_id` + `syllabus_id` 定位。

**带宽评估：N/A（只读）。**

### 2.3 下行（画像 Agent → 总 Agent）

返回：`profile_summary` ~5KB —— `learning_style`, `overall_score`, `practice_ability`, `bottleneck_topics`, `weak_points`, `resource_preference`

**带宽评估：充足。** 结构化的画像数据完整返回。

### 2.4 跨轮持久性

- ✅ 画像存在 profile 文件/DB
- ✅ `load_total_context` 每轮重加载 → 跨轮一致

---

## 3. Study Graph Agent（知识树）🔴

### 3.1 通路

**读路径：**
```
total_agent: load_total_context
  → tool_load_total_context
    → get_study_graph_features(user_id, syllabus_id)
```

**写路径：**
```
total_agent: record_learning_feedback  (无参!!)
  → tool_record_learning_feedback
    → _record_step_status(status=COMPLETED)
      → update_learning_plan_step_status(sync_study_graph=True)
        → build_study_graph_changes_from_resource_event({
            "user_id": int,
            "syllabus_id": int,
            "topic": str,           # ← step.get("title") 自动取
            "resource_type": "learning_plan_step",
            "status": "completed",  # ← 恒为 completed
          })
        → submit_learning_tree_changes(...)
```

### 3.2 上行（总 Agent → 知识树 Agent）

| 字段 | 当前值 | LLM 能控制？ |
|---|---|---|
| `user_id` | 自动 | 否 |
| `syllabus_id` | 自动 | 否 |
| `topic` | step.get("title") 自动取 | 否 |
| `resource_type` | 硬编码 "learning_plan_step" | 否 |
| `status` | 硬编码 "completed" | 否 |

**带宽评估：🔴 1 bit（done/not done）。** LLM 无法传入：
- `score` — 用户表现评分
- `wrong_knowledge_items` — 薄弱知识点
- `student_feedback` — 质性反馈
- `confidence` — Agent 对评估的确信度

`record_learning_feedback` 工具无参——LLM 只能调，不能说。
和 `accept_learning_plan` 之前的问题完全一致。

### 3.3 下行（知识树 Agent → 总 Agent）

返回：`study_graph_state` ~8KB —— `mastered_node_ids`, `weak_node_ids`, `learning_node_ids`, `updated_at`

**带宽评估：充足。** 结构化的知识树状态完整返回。

### 3.4 跨轮持久性

- ✅ 知识树数据持久化在 study_graph 表
- ✅ `load_total_context` 每轮重加载 → 跨轮一致
- ❌ 写路径只传递了 binary "completed" → 丰富的学习信号丢失

---

## 4. Resource Generation Agent（资源生成）

### 4.1 通路

```
total_agent: generate_current_step_resource
  → tool_generate_current_step_resource (agent_tools.py:2467)
    → build_current_step_resource_strategy(state)
    → _build_resource_request(state, next_task, resource_strategy)
    → process_resource_generation_request(state, execution_payload)
      → generate_resources_from_request(request_payload)
```

### 4.2 上行（总 Agent → 资源 Agent）

LLM 可通过 `resource_types` 参数传入（agent_runtime.py 已支持）：
```python
def generate_current_step_resource(ctx, resource_types: list[str] = None):
```

其他字段由系统组装：`title`, `outcomes`, `knowledge_items`, `question`, `profile_summary.weak_points`

**带宽评估：充足。** LLM 可指定资源类型，系统自动注入学习上下文。

### 4.3 下行（资源 Agent → 总 Agent）

返回：`generation_result` —— `resources` (列表), `resource_tasks`, `tool_status_events` ~10KB

**带宽评估：充足。**

### 4.4 跨轮持久性

- ✅ 资源存 resource 表
- ❌ `state["resource_generation_result"]` 跨轮丢失

---

## 5. Knowledge Search（知识检索）

### 5.1 通路

```
total_agent: retrieve_learning_evidence
  → tool_retrieve_learning_evidence (agent_tools.py:1174)
    → emit_status_pair → search_tool.search(query)
```

### 5.2 上行（总 Agent → 搜索）

`query` 从 payload 自动构建。

**带宽评估：一般。** LLM 不能直接指定搜索词——query 从消息和上下文自动构建。

### 5.3 下行（搜索 → 总 Agent）

返回：`results` (max 5), `reasoning_paths`, `matched_sources` ~5KB

**带宽评估：充足。**

### 5.4 跨轮持久性

- ❌ 搜索结果不持久化

---

## 6. Study Buddy（学伴通知）

### 6.1 通路

```
total_agent: _build_agent_final_result
  → _select_buddy_event(terminal_tool, *terminals)
    → notify_study_buddy_event(user_id, syllabus_id, event_type, payload, plan)
```

### 6.2 上行（总 Agent → 学伴）

事件类型由 terminal tool 决定：

| terminal_tool | event_type | payload 字段数 |
|---|---|---|
| `accept_learning_plan` | `plan_accepted` | 2 (`next_task_title`, `total_steps`) |
| `record_learning_feedback` | `learning_feedback_recorded` | 1 (`updated_step_title`) |
| `generate_current_step_resource` | `resource_ready` | 1 (`resource_type`) |
| `skip_current_step` | `step_skipped` | 0 |
| `abandon_learning_plan` | `plan_abandoned` | 0 |

**带宽评估：🟡 极薄。** 每个事件仅 0-2 个字段。学伴收到的是"发生了什么类型的事件"，
但几乎没有上下文——比如 `resource_ready` 只有 `resource_type`，没有 title/topic/summary。

### 6.3 下行（学伴 → 总 Agent）

无。学伴是单向通知。

### 6.4 跨轮持久性

- ✅ 学伴消息存 message 表

---

## 7. Course Learning Tree（班级知识树）

### 7.1 通路

```
total_agent: get_course_learning_tree_summary
  → tool_get_course_learning_tree_summary (agent_tools.py:1705)
    → study_graph_task.get_course_learning_tree_summary(payload)
```

### 7.2 上行

`payload` 自动传递。

**带宽评估：一般。** LLM 无直接参数。

### 7.3 下行

返回：`tree_summary` ~5KB —— class-wide nodes, mastery distribution

**带宽评估：充足。**

### 7.4 跨轮持久性

- ❌ 结果不持久化

---

## 8. 汇总矩阵

| 子 Agent | 方向 | 关键函数 | 带宽等级 | 核心问题 |
|---|---|---|---|---|
| Recommendation | 读/写 | `run_learning_recommendation`, `accept_learning_plan` | 🟢 充足 | 下行太重(150KB)；跨轮丢失 |
| Profile | 只读 | `load_profile_summary` | 🟢 充足 | 无 |
| Study Graph | 读/写 | `get_study_graph_features`, `record_learning_feedback` | 🔴 写: 1 bit | LLM 无法传 score/wrong_items/feedback |
| Resource Gen | 写 | `generate_current_step_resource` | 🟢 充足 | LLM 可传 resource_types |
| Knowledge Search | 只读 | `search_tool.search` | 🟡 一般 | LLM 不能直接给查询词 |
| Study Buddy | 写 | `_select_buddy_event` | 🟡 薄 | 每事件 0-2 字段 |
| Course Tree | 只读 | `get_course_learning_tree_summary` | 🟡 一般 | LLM 无直接参数 |

## 9. 修复优先级

| 优先级 | 模块 | 问题 | 修复方向 | 关联 contract 阶段 |
|---|---|---|---|---|
| P0 | Study Graph (写) | 1 bit 带宽 | `record_learning_feedback` 加参数：`score`, `weak_points`, `feedback_note` | 新增阶段 |
| P1 | Recommendation (读) | 下行太重 | `run_learning_recommendation` 瘦身返回（去掉 graph，只留 candidates 摘要） | message_history 合同阶段 4 |
| P1 | Recommendation (读) | 跨轮丢失 | `load_total_context` 注入 `pending_recommendation` | intent_gates 合同阶段 4 |
| P2 | Study Buddy | 事件太薄 | 事件 payload 增加 title/topic/summary 字段 | 新增阶段 |
| P3 | Knowledge Search | LLM 无查询参数 | `retrieve_learning_evidence` 加 `query` 参数 | 可选 |
| P3 | Course Tree | LLM 无参数 | 低优先级——很少用 | 可选 |
