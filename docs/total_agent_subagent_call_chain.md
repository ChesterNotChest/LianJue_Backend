# 总 Agent → 子 Agent 旁路评估

> **状态：✅ 已处理 (2026-07-16)**
> 评估的 3 个旁路（profile_observation、knowledge_mastery→study_graph、recommendation）已全部收口。详见 `subagent_inbox_contract.md`。

仅评估这 3 个应当调用子 Agent 但实际绕过的 tool。

---

## 1. tool_note_profile_observation → profile_agent

```
应当:  总Agent ──observation──► run_learning_profile_agent() ──► agent.run_sync()
                                                                   → normalize → compute → assemble → save

实际:  总Agent ──► merge_profile_update() ──► save_personal_profile()
                  └─► personal_syllabus.append/maybe_apply()
```

| 项目 | 说明 |
|------|------|
| 文件位置 | [agent_tools.py:2826-2937](tasks/total_agent/agent_tools.py#L2826) |
| 接收参数 | `learning_style`, `comprehension_level`, `weak_points`, `strong_points`, `note` |
| 实际做的事 | ① `merge_profile_update(existing, observation)` → dict merge ② `save_personal_profile()` → 写 JSON ③ 弱/强点推 `personal_syllabus` 周次建议 |
| 绕过的 Agent | `run_learning_profile_agent(state)` — 存在但从未被总 Agent 调用 |
| 绕过损失 | 不经过 `normalize_events` → `compute_features` → `assemble_profile` 完整管线，observations 仅做字段级 merge |

**评估：不改。**

理由：`run_learning_profile_agent` 是为"全量重建画像"设计的——它需要 history entries、dialogue texts 等完整上下文才能跑 `normalize_events` → `compute_features`。而 `tool_note_profile_observation` 是被总 Agent 在对话过程中**增量**调用的（每次学习交互后追加几个观察字段）。把增量 observation 强行塞进全量重建流程，要么报错（缺上下文），要么覆盖掉已有数据。

当前做法（merge + save）对增量 observation 是正确的。这个 tool 的本质就是"往画像里追加 note"，不是"重建画像"。

---

## 2. tool_record_learning_feedback → student_agent + profile_agent

```
应当:  总Agent ──knowledge_mastery──► run_student_agent()
                                    → rag_search → get_tree_context
                                    → build_changes (含 parent_candidate)
                                    → submit_changes → read_tree

       总Agent ──learning_record──► run_learning_profile_agent()
                                    → normalize → compute → assemble → save

实际:  总Agent ──► sgt.submit_learning_tree_changes()     ← 直写 DB，无 parent_candidate
       总Agent ──► save_personal_profile()                ← 直写 JSON，signals 手算
```

### 2a. knowledge_mastery → student_agent 旁路

| 项目 | 说明 |
|------|------|
| 文件位置 | [agent_tools.py:2628-2666](tasks/total_agent/agent_tools.py#L2628) |
| 输入 | `[{knowledge: "HDFS架构", mastery_label: "weak", score: 0.6, evidence: "..."}]` |
| 实际做的事 | hand-craft `upsert_knowledge_node` dict，直接调 `submit_learning_tree_changes()` |
| 绕过的 Agent | `run_student_agent(payload)` — 存在但从未被总 Agent 调用 |
| 绕过损失 | ① 没有 `parent_candidate` → 节点挂不上父节点，知识树全是散点 ② 没有 evidence 评分（question/event/rag 多源评分） ③ 没有 `rag_context` 融合 |

**评估：可以改，但风险中等。**

`run_student_agent(payload)` 接受 `detected_topics` 格式：
```python
detected_topics = [
    {"title": "HDFS架构", "confidence": 0.6, "signal": "struggled"}
]
```
`knowledge_mastery` 可以直接映射过去。Agent 内部会自动做 `rag_search` → `get_tree_context` → `build_changes`（含 `parent_candidate` 解析）→ `submit_changes`。

风险在于 `run_student_agent` 的完整管线比当前直写慢（多 2 次工具调用：RAG + tree context），且如果 RAG 不可用会怎样还不清楚。但当前旁路的**功能损失是真实的**——散点知识树是个问题。

**建议：先验证 `run_student_agent` 能正常跑通，再做切换。**

### 2b. learning_record → profile_agent 旁路

| 项目 | 说明 |
|------|------|
| 文件位置 | [agent_tools.py:2668-2735](tasks/total_agent/agent_tools.py#L2668) |
| 输入 | step + payload |
| 实际做的事 | hand-craft `learning_records[]` append，手算 `signals{active_days_7d, avg_duration_minutes}`，手算 `overall_score`，手算 `term_familiarity` |
| 绕过的 Agent | 同 ① — `run_learning_profile_agent()` |

**评估：不改。**理由同 ①。这里的数据已经是对的了（merge 修复后），增量计算信号值是工程上合理的做法。

---

## 3. tool_run_learning_recommendation → recommendation_agent

```
应当:  总Agent ──goals──► run_personal_recommendation_agent()
                        → agent.run_sync()
                        → 路径推荐 + 概念分解

实际:  总Agent ──► prt.run_recommendation_route_from_payload()
                  → run_recommendation_route()  ← 确定性 beam search，无 LLM
```

| 项目 | 说明 |
|------|------|
| 文件位置 | [agent_tools.py:1994](tasks/total_agent/agent_tools.py#L1994) |
| 实际调用 | `prt.run_recommendation_route_from_payload(payload)` |
| 实际做的事 | 确定性 beam search：遍历 study_graph 节点，基于 heuristic + RAG overlay 做路径评分排序 |
| 绕过的 Agent | `run_personal_recommendation_agent(state)` — 存在，但设计用途是**概念分解**（period concept decomposer），不是主推荐路径 |
| 绕过损失 | 无。确定性 beam search 比 LLM 更可靠、更快、可复现。LLM 做路径推荐反而有幻觉风险。 |

**评估：不改。且当前做法是正确的。**

`run_recommendation_route_from_payload` 不是一个"绕过"——它是设计如此。个人推荐 Agent 的真正用途是概念分解（把大概念拆成可学的小知识点），不是替代确定性路径推荐算法。工具名叫 `tool_run_learning_recommendation`，但它调用的推荐引擎就是确定性的，这没问题。

---

## 总结

```
┌─────────────────────────────────┬──────────┬──────────┬──────────────────────────────┐
│ Tool                            │ 应该调   │ 实际调   │ 结论                         │
├─────────────────────────────────┼──────────┼──────────┼──────────────────────────────┤
│ tool_note_profile_observation   │ profile  │ 直写JSON │ 不改：增量 merge 对，全量    │
│                                 │ _agent   │          │ 重建 pipeline 不适合增量场景  │
├─────────────────────────────────┼──────────┼──────────┼──────────────────────────────┤
│ tool_record_learning_feedback   │ student  │ 直写DB   │ 可改：功能损失真实            │
│ (knowledge_mastery → 学习树)    │ _agent   │ 无parent │ (散点树)，但需先验证 agent    │
├─────────────────────────────────┼──────────┼──────────┼──────────────────────────────┤
│ tool_record_learning_feedback   │ profile  │ 直写JSON │ 不改：同 ①                   │
│ (learning_record → 画像)        │ _agent   │          │                              │
├─────────────────────────────────┼──────────┼──────────┼──────────────────────────────┤
│ tool_run_learning_              │ recomme  │ 确定性   │ 不改：确定性算法对，          │
│ recommendation                  │ ndation  │ beam     │ LLM 做推荐反而有幻觉风险      │
│                                 │ _agent   │ search   │                              │
└─────────────────────────────────┴──────────┴──────────┴──────────────────────────────┘
```

**核心结论：3 个 tool 中，只有 `knowledge_mastery → student_agent` 这一个旁路值得修。另外两个保持现状即可。**

---

## 4. knowledge_mastery → student_agent 数据流详细感知

### 4a. 当前旁路的数据流（agent_tools.py L2628-L2666）

```
LLM 输出 knowledge_mastery:
  [{"knowledge": "HDFS架构", "mastery_label": "weak", "score": 0.6, "evidence": "用户说不理解NameNode"}]
    │
    ▼ 总Agent hand-craft 变换
mastery_changes = [{
    "op": "upsert_knowledge_node",
    "client_change_id": "total_agent:1:8:km:abc123:HDFS架构",
    "knowledge": {"title": "HDFS架构", "summary": "用户说不理解NameNode"},
    "mastery": {"signal": "struggled"},    ← "weak" → "struggled"
    "confidence": 0.6,
    // ⚠️ 无 parent_candidate
}]
    │
    ▼ 直接调用
sgt.submit_learning_tree_changes(1, 8, mastery_changes, source={"kind": "total_agent"})
    │
    ▼ MySQL
study_graph_node:  {node_id: "xxx", title: "HDFS架构", mastery_signal: "struggled"}
study_graph_edge:  (无新边创建, 因为 change 里没有 parent_candidate)
```

### 4b. 如果走 student_agent 的数据流

```
总Agent 将 knowledge_mastery 映射为 detected_topics:
  [{"title": "HDFS架构", "confidence": 0.6, "signal": "struggled"}]
    │
    ▼
run_student_agent({
    "user_id": 1, "syllabus_id": 8,
    "source_kind": "total_agent",
    "subject_title": "大数据概论",
    "detected_topics": [{"title": "HDFS架构", "confidence": 0.6, "signal": "struggled"}],
    "events": [],
    "rag_context": [],
    "parent_candidates": [],
    "personal_syllabus_context": {},
})
    │
    ▼ agent.run_sync() 启动, LLM 按 execution_rules 顺序调工具:
    │
    ├─① rag_search()
    │    → search_tool("HDFS架构", graph_name="RAG", top_k=3)
    │    → 返回 RAG 段落存入 state["rag_context"]
    │
    ├─② get_tree_context()
    │    → get_student_learning_tree_context(1, 8, "HDFS架构")
    │    → 从已有学习树中检索相关节点 ranked_candidates
    │    → 例: [{title: "大数据概论", node_id: "n1", score: 0.9},
    │           {title: "分布式存储", node_id: "n2", score: 0.7}]
    │
    ├─③ derive_payload()
    │    → 合并 rag_context + tree_context → enriched_payload
    │    → enriched_payload["rag_context"] = _normalize_rag_context_items(payload, rag_context)
    │    → enriched_payload["parent_candidates"] = _merge_parent_candidates(payload, tree_context)
    │         │
    │         │ _merge_parent_candidates 的逻辑:
    │         │ ① 先复制 payload 里已有的 parent_candidates (空)
    │         │ ② 从 detected_topics 提取 child_titles = ["HDFS架构"]
    │         │ ③ 对每个 child_title, 遍历 ranked_candidates (来自步骤②)
    │         │    找到树中已有的节点作为潜在父节点:
    │         │    parent_candidates = [
    │         │      {title: "分布式存储", child_title: "HDFS架构",
    │         │       existing_node_id: "n2", score: 0.7}
    │         │    ]
    │         │    ↑ 这意味着: HDFS架构 可能挂在 分布式存储 下面
    │
    ├─④ build_changes()
    │    → build_study_graph_changes_from_student_payload(enriched_payload)
    │         │
    │         │ ① _collect_candidate_titles → ["HDFS架构"]
    │         │ ② 对 "HDFS架构" 做 evidence 评分:
    │         │    _detect_topic_hit = 0.6  (来自 detected_topics.confidence)
    │         │    _question_hit = 0         (无 question)
    │         │    _event_hit = 0            (无 events)
    │         │    _personal_syllabus_hit = 0 (无 personal_syllabus)
    │         │    evidence_score = max(0.6, 0.25*0.6) = 0.6 ✓ (≥0.60 通过)
    │         │ ③ 查找 parent_candidate:
    │         │    遍历 parent_candidates, 找到 child_title == "HDFS架构" 的条目
    │         │    → {title: "分布式存储", child_title: "HDFS架构",
    │         │       existing_node_id: "n2"}
    │         │ ④ 产出 change:
    │         │    {
    │         │      "op": "upsert_knowledge_node",
    │         │      "knowledge": {"title": "HDFS架构", "summary": "...", "aliases": [...]},
    │         │      "parent_candidate": {             ← ✅ 有父节点候选
    │         │          "title": "分布式存储",
    │         │          "existing_node_id": "n2"
    │         │      },
    │         │      "mastery": {"signal": "struggled"},
    │         │      "confidence": 0.6,
    │         │    }
    │
    ├─⑤ submit_changes()
    │    → submit_learning_tree_changes(1, 8, changes, source={...})
    │    → MySQL:
    │      study_graph_node: {node_id: "yyy", title: "HDFS架构", mastery_signal: "struggled"}
    │      study_graph_edge: {parent_id: "n2", child_id: "yyy", relation: "parent_of"} ← ✅ 建立了父子边
    │
    └─⑥ read_tree() + read_features()
         → 返回完整树 + 特征摘要
```

### 4c. 差异对比

```
                    当前旁路                          student_agent
──────────────────────────────────────────────────────────────────────────────
 输入转换           hand-craft mastery_changes        detected_topics 映射
 RAG 查询           不做                              ✅ rag_search()
 树上下文           不读                              ✅ get_tree_context()
 evidence 评分      无 (直接 confidence=score)         ✅ 4 源加权评分
                    无阈值过滤                         <0.60 过滤, <0.80 需 touch
 parent_candidate   ❌ 缺失                           ✅ 从 ranked_candidates 解析
 最终边             只有节点, 无边                    节点 + parent_of 边
 调用次数           1 次 DB 写                        6 次 (RAG+tree+derive+build+submit+read)
```

### 4d. 当前旁路的实际后果

每次 `record_learning_feedback` 写入的知识节点都是**孤立节点**——它会有 `mastery_signal`，会在 study_graph_node 表里，但不会有任何 `parent_of` 边连到父节点。前端知识树展示时，这些节点要么不显示（如果前端按树结构遍历），要么显示为散点（没有父子层级）。

这就是为什么之前 simulation 跑出来的知识树"缺 parent-child 关系"——因为 total_agent 每次写入都跳过了 student_agent 的父节点解析步骤。
