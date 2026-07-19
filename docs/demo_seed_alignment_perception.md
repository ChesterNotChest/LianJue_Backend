# Demo Seed 与三份 Contract 的对齐感知

Demo seed 是 5 阶段全量预注入流水线，绕过了 Agent 工具直接写存储层。
三份 contract 是 Agent 工具的通路改造。两者共享同一个存储层，需要确认格式兼容、
数据等价、以及是否存在互补的验证机会。

---

## 1. 对照矩阵

### 1.1 Profile 写入

| 维度 | Demo Seed（当前） | Contract 改造后 |
|---|---|---|
| 调用方式 | `lpt.get_or_build_learning_profile()` 直接写 | `note_profile_observation()` Agent 工具增量写 |
| 写入数据 | `dialogue_text`, `learning_records`, `answer_records`, `resource_usage` 全套 | `learning_style`, `comprehension_level`, `weak_points`, `strong_points`, `note` |
| 存储层 | Profile 文件/DB — `merge_profile_update` | 同一个 `merge_profile_update` |
| 时序 | 一次性全量注入 | 每轮对话增量追加 |

**兼容性：✅ 完全兼容。** 两条路径调用同一个 `merge_profile_update`。全量注入建立基线，
增量更新追加变化。格式不一致但语义等价——seed 的 `learning_records[].score` 对应
`note_profile_observation` 的 `comprehension_level` 推论。

### 1.2 Study Graph 写入

| 维度 | Demo Seed（当前） | Contract 改造后 |
|---|---|---|
| 调用方式 | `sgt.submit_learning_tree_changes()` 手动构造 changes | `record_learning_feedback(knowledge_mastery=[...])` Agent 工具增量写 |
| 写入数据 | `[{op:"upsert_knowledge_node", knowledge:{title,summary}, mastery:{signal}, confidence}]` | `[{knowledge, mastery_label, score, evidence}]` → `build_study_graph_changes_from_resource_event` |
| 存储层 | Study Graph 树 | 同一个树 |
| 数据粒度 | 每个节点一条 `_study_change()` | 每个知识点一个 `knowledge_mastery` 条目 |

**兼容性：✅ 语义等价但格式不同。** 关键映射：

```
seed._study_change()          ←→   knowledge_mastery
-----------------------------------------------
signal: "mastered"            ←→   mastery_label: "mastered", score: 0.85+
signal: "learned"             ←→   mastery_label: "learning", score: 0.5-0.85
signal: "struggled"           ←→   mastery_label: "weak", score: 0.15-0.5
signal: "practiced"           ←→   mastery_label: "learning", score: 0.5-0.7
summary                       ←→   evidence
confidence                    ←→   score (置信度 vs 掌握度，不同维度)
```

**需要通过阶段 1 实现时确认：`build_study_graph_changes_from_resource_event` 能否正确
解析 `knowledge_mastery` 格式并映射到 study graph 节点更新。**

### 1.3 Recommendation / Snapshot

| 维度 | Demo Seed（当前） | Contract 改造后 |
|---|---|---|
| 调用方式 | `run_personal_recommendation_agent()` 直接调用 | 不变 |
| Snapshot | `save_recommendation_snapshot(proposed)` — 不 auto-accept | 不变 |
| message_history 影响 | 无——seed 不走 Agent SSE | 运行时 Agent 走 message_history 跨轮感知 |

**兼容性：✅ 完全独立。** Demo seed 不经过 Agent，message_history 对它无影响。

### 1.4 Resource 生成

| 维度 | Demo Seed（当前） | Contract 改造后 |
|---|---|---|
| 调用方式 | `generate_resources_from_request()` 直接调用 | `generate_current_step_resource(resource_types=[...])` Agent 工具 |
| `list_my_resources` | 不存在——seed 用不到 | 新增——Agent 运行时查已有资源 |

**兼容性：✅ 独立。** Seed 是写，`list_my_resources` 是读。不冲突。

---

## 2. 数据等价性分析

### 2.1 五个 Demo Level 的信号密度

| Level | Profile Records | Study Graph Nodes | 等效的 `knowledge_mastery` 条目数 |
|---|---|---|---|
| LOW | 4 records | 2 nodes | ~2 条 |
| LOW_MEDIUM | 4 records | 3 nodes | ~3 条 |
| MEDIUM | 5 records | 5 nodes | ~5 条 |
| MEDIUM_HIGH | 4 records | 3 nodes | ~3 条 |
| HIGH | 8 records + 8 answers | 9 nodes | ~9 条 |

等效条数 = 每个 level 的 study graph batch 里 changes 数量。
这些在 Agent 运行时对应的就是 `record_learning_feedback(knowledge_mastery=[N条])`。

### 2.2 映射验证点

改造后，如果拿 demo seed 的数据喂给 Agent：
- Profile 的 `weak_points` 应该和 `_study_change(signal="struggled")` 的知识点一致
- Study Graph 的 `mastery_score` 应该反映 seed 数据的掌握度分布

这两项可以作为回归测试——seed 创建后，Agent 的 `load_total_context` 应该返回一致的
profile 和 study graph。

---

## 3. 潜在的验证机会

### 3.1 新增：`note_profile_observation` 端到端验证

不修改 demo seed 本身，新增一个独立的验证 case：

```
TC: note_profile_observation 写入 → load_total_context 读回
  1. demo seed 创建 HIGH 学生 → profile 已含 bottleneck_topics=["高阶方法","易错点"]
  2. Agent 调 note_profile_observation(weak_points=["高阶综合应用"], note="跨章节策略选择薄弱")
  3. 再次 load_total_context → bottleneck_topics 增加 "高阶综合应用"
  4. 原 bottleneck_topics 不受影响（merge 而非覆盖）
```

### 3.2 新增：`record_learning_feedback` 知识穿透验证

```
TC: record_learning_feedback 写入 → study graph 节点更新
  1. demo seed 创建 MEDIUM 学生 → study graph 含 "当前模块"(signal=struggled)
  2. Agent 调 record_learning_feedback(
       knowledge_mastery=[{"knowledge":"当前模块","mastery_label":"mastered","score":0.88}])
  3. study graph 中 "当前模块" 节点 mastery_score 从 <0.5 变为 0.88
  4. mastery_label 从 "weak" 变为 "mastered"
```

### 3.3 现有 seed 不需要改

Demo seed 五阶段流水线继续走直接注入。三个 contract 的工具是**运行时增量**通路。
两者不冲突，共享同一套存储格式。

---

## 4. 风险点

| # | 风险 | 等级 | 说明 |
|---|---|---|---|
| R1 | `knowledge_mastery` 格式不被 `build_study_graph_changes_from_resource_event` 识别 | 🟡 中 | 阶段 1 实现时必须确认接收端格式兼容 |
| R2 | `knowledge` 字符串匹配不到 study graph 节点 | 🟡 中 | seed 用的是 `title` 精确匹配，Agent 填的可能是自然语言变体 |
| R3 | `note_profile_observation` 的 merge 逻辑与 seed 全量注入的 profile 格式不一致 | 🟢 低 | `merge_profile_update` 已存在，兼容 dict 合并 |
| R4 | 三份 contract 的 agent_write_bandwidth 改变 seed 依赖的函数签名 | 🟢 低 | `_record_step_status` 内部变化，seed 不调用它 |
