# 学伴学习进度树 Contract

学伴「小觉」当前能接触到的学习状态信息是严重扁平化的 —— `study_graph_features` 把完整树结构压缩成了 `["标题1", "标题2", ...]` 的字符串列表。这份 contract 设计一份学伴专属的持久化学习进度树，修复输入带宽，并为后续的自演化写通路打底。

---

## 0. 现状感知

### 0.1 当前数据流（完整链）

```
MySQL study_graph_node (14字段，含 mastery_label/score/summary)
    │
    ▼
get_learning_tree_features(user_id, syllabus_id)
    │  ← get_learning_tree_features_payload()
    │  ← 遍历节点，按 mastery.label 分桶
    │
    ▼
{
  "mastered_topics": ["大数据基础", "HDFS 基础", ...],    ← str[]
  "weak_topics":     ["RowKey 热点", "预分区", ...],       ← str[]
  "learned_topics":  ["ETL过程", ...],                     ← str[]
  "recently_grown":  [...],
  "stale_topics":    [...],
}
    │  ← 🔴 丢失: node_id, score, summary, edges, outcomes
    │
    ▼
build_buddy_tree(plan, features)
    │  ← trunk = plan.steps 投影
    │  ← learned = features.learned_topics 分类，score 硬编码 0.85
    │  ← explore = features.weak/stale_topics 分类，score 硬编码 0.3/0.5
    │
    ▼
buddy context (纯文本，注入 LLM prompt)
```

### 0.2 实际数据落差（以 user_214/syllabus_29 为例）

```
study_graph_node (DB 里实际有的):
  node_id: "knowledge:214:29:hbase_rowkey_u8bbeu8ba1"
  title: "HBase RowKey 设计"
  mastery: {label: "weak", score: 0.335}
  summary: "..."
  parent_node_id: "knowledge:214:29:hbase_u6570u636eu6a21u578b"
  edges: →
    parent_of→ RowKey 热点
    parent_of→ 加盐前缀
    parent_of→ 散列前缀

buddy 实际收到的（经过 features 扁平化后）:
  weak_topics: ["HBase RowKey 设计"]    ← 只剩 5 个汉字
```

**原始树有 14 个节点、7 条边、每个节点有 mastery score 和 summary。buddy 只能看到 14 个孤立的标题。**

### 0.3 当前 buddy tree 持久化状态

```
study_buddy/
  user_{id}/syllabus_{id}/
    tree.json              ← 每次重建，仅用于 diff 检测（变化→触发消息）
    buddy_memory.jsonl     ← 文本 tag（唯一真正"自演化"的数据）
    buddy_messages.jsonl   ← 聊天记录
```

`tree.json` 的内容是 `build_buddy_tree()` 的输出（trunk/learned/explore 三个 region），完全从上游派生，没有 buddy 自己的观察。

---

## 1. 设计：学伴学习进度树

### 1.1 核心思路

**学伴学习进度树和 Study Graph Tree 是孪生关系——同样的结构（nodes + edges + mastery），不同的建构路径。**

- Study Graph Tree：**操作建树**——学习事件（step completed / resource consumed）→ delta 更新 mastery score
- Buddy Progress Tree：**观察建树**——聊天感知（用户说了什么、怎么说的）→ 标注 mastery_hint + 文本观察

两者不冲突。不是"谁替代谁"。Study Graph 是权威量化层，Buddy Tree 是质感感知层。结构一样，数据互补。

### 1.2 孪生树的差异化价值

```
Study Graph Tree (权威)              Buddy Progress Tree (感知)
─────────────────────────           ─────────────────────────
RowKey 设计: weak (0.34)            RowKey 设计: weak (0.34)
  来源: demo_seed                     来源: study_graph 快照
                                    buddy_notes:
                                      "用户在聊天中准确区分了 Salt 前缀
                                       和 Hash 前缀的适用场景——对 RowKey
                                       设计的实际理解比分数显示的要好"
                                      mastery_hint: "stronger"
                                      created_at: 1783185000

HBase 基础: learning (0.43)         HBase 基础: learning (0.43)
  来源: demo_seed                     来源: study_graph 快照
                                    buddy_notes:
                                      "用户说'这部分我之前看过了'——
                                      暗示对基础有自信，可能不需要重复"
                                      mastery_hint: "stronger"
```

Study Graph 的 summary 是 demo seed 写的固定文本。Buddy 的观察是对话里长出来的活信息。

### 1.3 建树策略：快照 + 双源 merge

```
                ┌──────────────────────────┐
                │   study_graph (DB/权威)   │  ← 操作建树
                │   nodes + edges + mastery │
                └──────────┬───────────────┘
                           │
                    get_student_learning_tree()
                    (完整节点 + 边，不扁平化)
                           │
                           ▼
              ┌────────────────────────────┐
              │     buddy_tree.json (文件)  │  ← 观察建树
              │                            │
              │  nodes: {node_id: {        │
              │    node_id, title,          │
              │    mastery: {label, score}, │  ← 从 study_graph 同步
              │    summary, outcomes,       │
              │    parent_node_id,          │
              │    edges: [{target, rel}],  │
              │    buddy_notes: [           │  ← buddy 自己的观察（不覆盖）
              │      {note, created_at,     │
              │       source, mastery_hint} │
              │    ]                        │
              │  }}                         │
              │  regions: {trunk, learned,  │  ← 派生 region 分类
              │            explore}        │
              │  buddy_observations: {      │  ← 全局统计
              │    last_observed_at,        │
              │    total_observations}      │
              └────────────────────────────┘
                           │
                           ▼
                   build_buddy_context()
                   (量化 + 质化混合，注入 LLM)
```

### 1.3 Merge 逻辑

每次 `build_buddy_tree()` 调用时：

1. **读 buddy_tree.json** (如果存在)
2. **读 study_graph 完整树** (`get_student_learning_tree`)
3. **读 active_plan** (trunk 来源)
4. **Merge**:
   - study_graph 中新增/变化的节点 → 更新 mastery 和 summary
   - study_graph 中已删除的节点 → 保留但标记 `removed_from_source: true`
   - buddy 已有的 `buddy_notes` → 保留不动
   - plan steps → 标记 trunk region
5. **重新分类 regions** (trunk/learned/explore，算法同现在)
6. **写回 buddy_tree.json**

### 1.4 上下文注入

`build_buddy_context()` 不再只输出 flat 文本。新增**结构化节点摘要**：

```
当前学习进度 ────────
主干路径（正在学）：
  [active] HBase RowKey 设计
    └ 学习进度: weak (0.34) — 盐值、热点、预分区三个子节点均薄弱
    └ 前驱: HBase 数据模型 (learning, 0.43)

已掌握：
  [mastered] 大数据基础 (0.85) — 对基本概念、4V特征有稳定理解

可以探索的（薄弱/过期）：
  [weak] 预分区 (0.09)   ← 关联: HBase RowKey 设计
  [weak] RowKey 热点 (0.09) ← 关联: HBase RowKey 设计
  [weak] 加盐前缀 (0.34)   ← 关联: RowKey 热点

你的记忆 ────────
  学习风格：偏好先搭框架、理清学科关系，再深入细节
```

LLM 可以引用具体的节点名、分数、前驱关系，而不是猜。

---

## 2. 存储选型：文件 vs 数据库

### 2.1 结论：**文件（JSON）**

| 维度 | 文件 (JSON) | 数据库 (MySQL) |
|---|---|---|
| 部署复杂度 | 零 —— buddy 已有文件存储 | 需要 migration + 新表 |
| 数据体积 | ~5-50KB / 树 | 同 |
| 查询需求 | 单树整体读写 | 无跨树查询需求 |
| 调试方便度 | 直接 `cat` / IDE 打开 | 需要 mysql CLI |
| 原子写入 | 已有 `tempfile + os.replace` | DB 事务 |
| 迁移成本 | 当前 `tree.json` 原地升级 schema | 新建表 + 代码双写 |
| 一致性 | buddy 树是缓存/派生数据，丢了可以从 study_graph 重建 | — |

**选择文件的理由：**

1. **buddy 树是派生数据** —— 它的权威来源是 `study_graph` (DB) + `active_plan`。即使 `buddy_tree.json` 丢失，下次 build 时会自动从零重建（只是丢了 buddy_notes）。
2. **当前基础设施支持** —— `tree_store.py` 已经有原子读写（`mkstemp` + `os.replace`）。
3. **没有跨树查询需求** —— buddy 只需要自己用户的树，不需要 JOIN 或聚合。
4. **后续可迁移** —— 如果将来需要跨 buddy 聚合分析，加一张 `study_buddy_tree` DB 表即可，JSON 字段映射到列。

---

## 3. 数据格式

### 3.1 buddy_tree.json schema

```json
{
  "schema_version": "study_buddy.tree.v2",
  "user_id": 214,
  "syllabus_id": 29,
  "updated_at": 1783184282,
  "nodes": {
    "knowledge:214:29:hbase_rowkey_u8bbeu8ba1": {
      "node_id": "knowledge:214:29:hbase_rowkey_u8bbeu8ba1",
      "title": "HBase RowKey 设计",
      "normalized_title": "hbase_rowkey_u8bbeu8ba1",
      "mastery": {"label": "weak", "score": 0.335},
      "summary": "...",
      "outcomes": [],
      "parent_node_id": "knowledge:214:29:hbase_u6570u636eu6a21u578b",
      "edges": [
        {"target": "knowledge:214:29:rowkey_u70edu70b9", "relation": "parent_of"},
        {"target": "knowledge:214:29:u52a0u76d0u524du7f00", "relation": "parent_of"},
        {"target": "knowledge:214:29:u6563u5217u524du7f00", "relation": "parent_of"}
      ],
      "source": {"kind": "study_graph_snapshot", "synced_at": 1783184282},
      "buddy_notes": []
    }
  },
  "regions": {
    "trunk": ["knowledge:214:29:hbase_rowkey_u8bbeu8ba1"],
    "learned": ["knowledge:214:29:u5927u6570u636eu57fau7840", "..."],
    "explore": ["knowledge:214:29:rowkey_u70edu70b9", "..."]
  },
  "buddy_observations": {
    "last_observed_at": null,
    "total_observations": 0
  }
}
```

### 3.2 buddy_notes 条目格式

```json
{
  "note": "用户聊天中主动提到能区分 Salt 和 Hash，RowKey 设计理解比 mastery 显示的要深",
  "created_at": 1783185000,
  "source": "chat",
  "mastery_hint": "stronger"
}
```

### 3.3 关键设计决策

| 决策 | 理由 |
|---|---|
| nodes 用 `dict[node_id]` 而非 `list` | O(1) 按 ID 查找，merge 时高效 |
| regions 存 `node_id[]` 而非嵌入节点 | 节点数据一份，region 只是分类索引 |
| buddy_notes 只增不删 | buddy 的观察是增量证据，不覆盖历史 |
| mastery 从 study_graph 同步覆盖 | mastery 权威来源是 study_graph，buddy 不篡改 |
| `mastery_hint` 只做提示 | buddy 对掌握度的判断只做标注，由后续 agent 决定是否采纳 |

---

## 4. 影响范围

### 4.1 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `tasks/study_buddy/tree.py` | **重写** | `build_buddy_tree()` 改为 merge 模式；新增 `_snapshot_from_study_graph()` |
| `tasks/study_buddy/tree_store.py` | **改** | `save_buddy_tree()` / `load_buddy_tree()` 适配 v2 schema |
| `tasks/study_buddy/buddy_agent.py` | **改** | `build_buddy_context()` 输出富含节点信息的结构化文本 |
| `tasks/study_buddy/contracts.py` | **改** | `BUDDY_TREE_SCHEMA_VERSION` → v2；新增 `BUDDY_NOTE_MAX_CHARS` |
| `tasks/study_buddy_task.py` | **不变** | 对外接口不变，内部数据结构升级 |
| `tasks/total_agent/agent_tools.py` | **改** | `get_study_graph_features()` 调用处传入完整节点而非 flat features |

### 4.2 不变清单

- ✅ buddy 的 tools（create/delete memory tag）不变
- ✅ buddy 的 chat/proactive 入口函数签名不变
- ✅ `study_graph` 存储层不变 —— buddy 只读不写
- ✅ 前端不变 —— 接口返回格式不变
- ✅ memory tags 和 messages 存储不变

---

## 5. 阶段划分

### 阶段 1：输入带宽修复（核心）

**目标**：让 buddy 看到完整的节点信息（node_id, mastery score, edges）。

- 新增 `_snapshot_from_study_graph(user_id, syllabus_id)` → 从 `get_student_learning_tree()` 读取完整树，映射到 buddy 节点格式
- 重写 `build_buddy_tree()` → 合并 study_graph 快照 + plan.steps 投影 + 现有 buddy_tree.json 中的 notes
- 升级 `save_buddy_tree()` / `load_buddy_tree()` → v2 schema
- 改进 `build_buddy_context()` → 输出包含 score、edges、parent 的结构化摘要

**不收口**：此阶段不引入 buddy 写节点。buddy 只能读。

### 阶段 2：buddy 写通路（增量）

**目标**：让 buddy 能通过 `note_intent` 类似的方式注记节点。

- 新增 `note_tree_node` 工具 → buddy LLM 可调用，写入 `buddy_notes`
- 不需要新增 DB 表 —— 直接 append 到 `buddy_tree.json` 的 nodes 中
- `mastery_hint` 先只做标注，不做实际 mastery 调整

**不收口**：此阶段 buddy_notes 不影响 study_graph，纯本地记录。

### 阶段 3：闭环反馈 ❌ 不做

学伴的观察不应该反向写入 study_graph——学伴定位是"陪聊 + 轻轻推一把"，不是"替老师改分"。buddy_notes 永远只留在 buddy_tree.json 里，不影响推荐和路径决策。

---

## 6. 风险矩阵

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | buddy_tree.json 与 study_graph 不同步 | 🟢 低 | 每次 build 时全量 merge study_graph 节点 |
| R2 | 节点数量增长导致 context 过大 | 🟡 中 | region 分类 + 限制每个 region 展示数量（当前已有 trunk≤10, learned≤8, explore≤8） |
| R3 | `get_student_learning_tree` 返回的节点缺少 edge 信息 | 🟡 中 | edges 需要单独从 `list_edges(tree_id)` 查询；需在 snapshot 阶段 join |
| R4 | v1 schema 的旧 `tree.json` 文件存在 | 🟢 低 | 首次加载时检测 schema_version，v1 直接覆盖重建 |
| R5 | buddy_tree 文件损坏 | 🟢 低 | 原子写入（tmpfile + replace）；损坏时从 study_graph 重建 |

---

## 7. 验证

### 7.1 单元/集成

```
TC1: 首次 build（无 buddy_tree.json）
     → 从 study_graph 快照创建 buddy_tree.json
     → nodes 数量 = study_graph 节点数
     → regions.trunk 包含 active_plan.steps

TC2: 二次 build（已有 buddy_tree.json）
     → study_graph 中某节点 mastery 从 0.3 → 0.6
     → buddy_tree.json 中该节点 mastery 更新为 0.6
     → buddy_notes 保留不变

TC3: study_graph 新增节点
     → buddy_tree.json nodes 增加该节点
     → 已有节点的 buddy_notes 不受影响

TC4: build_buddy_context 输出
     → 包含节点标题 + mastery score + 前驱关系
     → 不再只有 flat 标题

TC5: user_214 实际数据
     → buddy context 输出 "HBase RowKey 设计 (weak 0.34)" 而非仅标题
     → 能看到 "前驱: HBase 数据模型 → HBase RowKey 设计"
```

### 7.2 回归

- `test_personal_recommendation_api.py` 5 个用例全过
- `test_total_agent_agent_choice.py` stream pipeline 用例过
- 编译检查：`agent_tools.py`, `agent_runtime.py`, `agent_contracts.py`, `tree.py`, `tree_store.py`, `buddy_agent.py` 全部 `py_compile` OK

---

## 附录：孪生树双生命周期

```
═══════════════════════════════════════════════════════════════════
                    Study Graph Tree (权威量化层)
                            操作建树
═══════════════════════════════════════════════════════════════════

  Phase 1: Demo Seed (一次性全量注入)
    test_seed_demo_students.py
    → submit_learning_tree_changes()
    → upsert_node + upsert_edge
    source.kind = "demo_student_seed"
    产出: N 个 mastery-labeled 节点 + parent_of 边

  Phase 2: 学习事件增量 (运行时持续)
    record_learning_feedback
    → sync_study_graph=True
    → build_study_graph_changes_from_resource_event
    → submit_learning_tree_changes
    source.kind = "resource"
    产出: mastery delta 更新 (signal + confidence → score ±0.3)

  Phase 3: Student Agent (LLM 驱动扩建)
    run_student_agent(payload)
    → rag_search → tree_context → build_changes → submit
    source.kind = "student"
    产出: LLM 判断的新节点 + parent 关系

═══════════════════════════════════════════════════════════════════
                  Buddy Progress Tree (质感感知层)
                          观察建树
═══════════════════════════════════════════════════════════════════

  Phase 1: Snapshot (从权威树拍快照)
    build_buddy_tree()
    → get_student_learning_tree()  ← 完整节点 + 边
    → 映射为 buddy 节点格式
    → 写回 buddy_tree.json (v2)
    产出: 结构一致的树副本

  Phase 2: Sync (持续同步权威变化)
    build_buddy_tree()
    → merge study_graph 新增/变化节点
    → 保留 buddy_notes 不覆盖
    产出: mastery score 更新，观察保留

  Phase 3: Observe (对话感知追加)
    buddy chat / proactive event
    → LLM 调 note_tree_node(title, note, mastery_hint)
    → append buddy_notes
    产出: 质化观察层，一次对话即可产多条

═══════════════════════════════════════════════════════════════════

  两者关系:
  - 结构同构 (nodes + edges + mastery)
  - 建树路径不同 (操作 vs 观察)
  - 数据互补 (量化 score vs 质化 note)
  - 互不覆盖 (sync 更新 mastery，buddy_notes 只增不删)
```
