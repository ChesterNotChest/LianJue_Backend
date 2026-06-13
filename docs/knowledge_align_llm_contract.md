# Knowledge Point ↔ Node Outcome LLM Alignment — Implementation Contract

## Phase 0: 新增常量与环境变量

| 常量 | 值 | 位置 | 说明 |
|------|----|------|------|
| `KNOWLEDGE_ALIGN_LLM_ENABLED` | `"1"` | env var | 默认开启；设为 `"0"` 回退规则三层 |
| `_ALIGN_CACHE` | `{}` | `perception.py` 模块级 | 进程级 LRU，key=输入哈希，value=enriched dict |

---

## Phase 1: 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/personal_recommendation/perception.py` | 修改 | 新增 `_llm_align_knowledge()`，修改 `generate_state()` |

**单文件改动，不修改任何其他模块。**

---

## Phase 2: 函数级完整数据流

```
run_recommendation_route()                          [service.py:653]
  │
  ├─ profile = build_recommendation_profile(uid)     # 加载画像
  │     └─ by_knowledge_point: {"HDFS 基础": 0.86, "ETL": 1.0, ...}
  │
  ├─ learning_tree = load_recommendation_learning_tree(sid)
  │     └─ {"node_1": {title: "分布式文件系统及主流技术HDFS", outcomes: [...]}, ...}
  │
  └─ generate_state(profile, recommendation_graph_tree, study_graph_state)  [perception.py:138]
        │
        ├─ knowledge = _normalize_knowledge_levels(profile)
        │     └─ {"HDFS 基础": 0.86, "ETL": 1.0, ...}
        │
        ├─ knowledge = _llm_align_knowledge(knowledge, learning_tree)   ← NEW
        │     │
        │     │  cache check → miss?
        │     │    │
        │     │    ├─ 构建 prompt:
        │     │    │   tags:  "HDFS 基础:0.86\nETL过程:1.0\n..."
        │     │    │   nodes: "node_1: title=分布式文件系统..., outcomes=[...]\n..."
        │     │    │
        │     │    ├─ litellm.completion(model=config["text"])
        │     │    │   返回: {"matches": {"分布式文件系统...": {"tag": "HDFS 基础"}}}
        │     │    │
        │     │    └─ 解析 JSON → enrich knowledge:
        │     │         knowledge["分布式文件系统及主流技术HDFS"] = 0.86  ← 原来没这条!
        │     │         knowledge["数据抽取、转换、装载的过程"] = 1.0
        │     │
        │     └─ cache[hash] = knowledge
        │
        ├─ for nid, node in learning_tree:
        │     _node_outcomes_known(node, knowledge)    # 现在能命中 enriched entries
        │       └─ knowledge.get("分布式文件系统及主流技术HDFS") → 0.86 > 0 → True ✅
        │
        └─ return state, start_nodes   # start_nodes 不再包含已掌握节点
```

---

## Phase 3: 函数级收口

### 3.1 `_llm_align_knowledge(knowledge, learning_tree) -> dict`

**输入：**
- `knowledge: Dict[str, float]` — key 为知识点短标签（`"HDFS 基础"`），value 为掌握度分数
- `learning_tree: Dict[str, Dict]` — key 为 node_id，value 为 `{title: str, outcomes: list[str], ...}`

**输出：**
- `Dict[str, float]` — 原 knowledge dict 的浅拷贝 + 追加的 entries，key 为 node outcome/title 字符串，value 为匹配到的 knowledge_point 分数

**内部逻辑：**

1. 若 `os.getenv("KNOWLEDGE_ALIGN_LLM_ENABLED") == "0"`，直接返回原 `knowledge`（不做 LLM 调用）

2. 若 `knowledge` 为空或 `learning_tree` 为空，返回原 `knowledge`

3. 计算缓存 key：`hash = (frozenset(knowledge.keys()), frozenset(node["title"] for node in learning_tree.values() if node.get("title")))`

4. 若 `_ALIGN_CACHE.get(hash)` 存在，返回缓存值

5. 构建 prompt：
   ```
   system: "You are matching knowledge point tags to course node descriptions.
            For each node description, find the best matching knowledge tag.
            Return ONLY valid JSON. No explanation."
   user:   "Knowledge tags:
            - HDFS 基础: 0.86
            - ETL过程: 1.0
            ...

            Node descriptions:
            - node_1: title="分布式文件系统及主流技术HDFS"
            - node_2: title="ETL过程", outcomes=["数据抽取、转换、装载"]
            ...

            Return JSON: {"matches": {"node title or outcome": {"tag": "best matching knowledge tag"}}}
            Only include entries where you are confident of a match."
   ```

6. 调用 `litellm.completion()`：
   - `model = OPENAI_COMPAT_MODEL_CONFIGS["text"]["model_name"]`
   - `api_base = OPENAI_COMPAT_MODEL_CONFIGS["text"]["api_base"]`
   - `api_key = OPENAI_COMPAT_MODEL_CONFIGS["text"]["api_key"]`
   - `temperature = 0`
   - `messages = [{role: "system", content: ...}, {role: "user", content: ...}]`

7. 解析响应 JSON → `matches: dict`

8. Enrich：
   ```python
   enriched = dict(knowledge)
   for matched_text, info in matches.items():
       tag = info.get("tag") if isinstance(info, dict) else info
       if tag in knowledge:
           enriched[matched_text] = knowledge[tag]
   ```

9. `_ALIGN_CACHE[hash] = enriched`，返回 `enriched`

10. 若 LLM 调用失败或 JSON 解析失败 → 返回原 `knowledge`（静默降级，不影响推荐流程）

### 3.2 `generate_state(user_profile, learning_tree, study_graph_state=None) -> tuple`

**修改点：** 在 `knowledge = _normalize_knowledge_levels(user_profile)` 之后插入一行：

```python
knowledge = _llm_align_knowledge(knowledge, learning_tree)
```

其余逻辑不变。`_node_outcomes_known` 仍用 `knowledge.get(outcome)`，但现在 knowledge 里已有 enriched entries，会命中。

---

## Phase 4: 测试用例

### 4.1 单元测试：LLM 对齐正确性

**文件：** `tests/test_personal_recommendation_learning_plan.py`（或新建 `tests/test_knowledge_align.py`）

**用例 1 — 基本匹配：**
- 输入 knowledge: `{"HDFS 基础": 0.86, "ETL过程": 1.0, "HBase 基础": 0.0}`
- 输入 learning_tree: `{"n1": {title: "分布式文件系统及主流技术HDFS"}, "n2": {title: "数据抽取、转换、装载的过程"}}`
- 调用 `_llm_align_knowledge(knowledge, learning_tree)`
- 验证 enriched dict 中包含：
  - `"分布式文件系统及主流技术HDFS": 0.86`
  - `"数据抽取、转换、装载的过程": 1.0`
- 验证原始 keys 不变

**用例 2 — 无匹配节点不追加：**
- 输入 knowledge: `{"HDFS 基础": 0.86}`
- 输入 learning_tree: `{"n1": {title: "课程导论"}}`
- 验证 enriched dict 中不包含 `"课程导论"`（LLM 应该判定不匹配）

**用例 3 — LLM 关闭时回退：**
- `monkeypatch.setenv("KNOWLEDGE_ALIGN_LLM_ENABLED", "0")`
- 调用 `_llm_align_knowledge(knowledge, learning_tree)`
- 验证返回的就是原 `knowledge`（无 LLM 调用）

**用例 4 — LLM 失败时静默降级：**
- 用无效 model_name 构造 config
- 验证不抛异常，返回原 knowledge

### 4.2 集成测试：generate_state 使用 enriched knowledge

**用例 5 — start_nodes 排除已掌握节点：**
- 构建 profile with `by_knowledge_point: {"HDFS 基础": 0.9, "ETL": 0.9}`
- 构建 learning_tree with 3 个节点：
  - `n1: {title: "分布式文件系统及主流技术HDFS"}` — 应被标记为 known
  - `n2: {title: "ETL过程"}` — 应被标记为 known
  - `n3: {title: "分布式数据库中典型技术HBase"}` — 应被标记为 unknown
- 调用 `generate_state(profile, learning_tree)`
- 验证 `start_nodes` 只包含 `n3`（HBase），不包含 `n1, n2`

### 4.3 回归验证：Seed 后 Plan 区分度

**用例 6 — medium seed 后 plan 不从 Week 1 开始：**
- 运行 `RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v -k demo_medium`
- 查询该用户的 active plan steps
- 验证：active step 的 title 不是"介绍学科背景…"（Week 1），而应该偏后（HBase 附近）
- 验证：plan 步骤数 > 0

---

## 缓存注意事项

- `_ALIGN_CACHE` 是模块级 dict，进程重启自动清空
- 同一进程内同一 knowledge + tree 组合只调一次 LLM
- 不需要过期机制：同一推荐周期内 knowledge 和 tree 不变
