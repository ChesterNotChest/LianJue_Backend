# Study Graph Tools Contract

本文档是 `docs/study_graph_tools_small_plan.md` 的收口级实现计划，用于直接指导“学生学习成长树”工具集合的实现。

目标不是构建完整课程知识图谱，也不是复制总知识库。目标是在每个 `user_id + syllabus_id` 范围内维护一棵学生已经触达过的学习成长树：

```text
学生触达知识 -> Student Agent 提交变更候选 -> Tool/算法裁决 -> Manifest 落盘 -> 前端/Agent 读取成长树或摘要
```

总知识库信息由 Teacher Agent 或 Student Agent 通过 RAG 实时获取；学生成长树只提供个体学习状态。Teacher Agent 负责融合“总知识库结构、学生成长树状态、画像评分和资源任务”。

## 0. 总体边界

### 0.1 当前实现范围

- 每个学生每个大纲一棵成长树。
- 只维护已触达知识节点。
- 只维护 `parent_of` 树边。
- Agent 只能提交变更候选，不能直接写树。
- Tool/算法层负责归一化、去重、父节点裁决、掌握度更新和展示状态更新。
- 前端读取可渲染树，Teacher/Student Agent 读取摘要特征。

### 0.2 当前不做范围

- 不维护完整课程知识图谱。
- 不提前展示未学习节点。
- 不保存总知识库强引用。
- 不维护推荐边、前置边、资源边、题目边。
- 不把审计明细塞进主树。
- 不让 Agent 任意创建节点和边。
- 当前采用 manifest 作为运行时存储，不新增 MySQL 表。SQL 表作为独立迁移目标，迁移时统一落到 `study_graph_*` 关系表。

### 0.3 推荐模块关系

推荐模块可以读取成长树，但推荐结果不属于成长树。推荐可以临时说“下一步建议学 X”，但 X 在学生真正触达前不生成树节点。

### 0.4 Agent 归属决策

由 Student Agent 负责维护学生学习成长树。本文档定义的是成长树工具集合，不定义完整 Agent prompt；Student Agent 通过这些工具提交成长树变更候选，并通过 RAG 工具补充当前提问相关的总知识库上下文。

Agent 职责边界：

- Teacher Agent：总调度。融合 RAG、学生成长树摘要、画像评分和资源任务，决定下一步推荐、追问或资源生成。
- Student Agent：维护学习成长树。消化个人教学大纲、RAG 结果、提问内容和学习事件，产出成长树变更候选。
- 学习画像 Agent：维护个人教学大纲和整体表现多维分数。消化个人教学大纲内信息、提问内容和表现事件，产出多维评分与画像摘要。
- 资源推荐/生成 Agent：根据 Teacher Agent 或 Student Agent 给出的学习目标、薄弱点和资源类型，生成或推荐可渲染资源。

理由：

- 成长树是结构化、时序化、可视化的学习进度状态；画像是统计评分、学习偏好和整体表现摘要。二者相关，但不是同一个状态对象。
- Student Agent 需要同时读取“个人教学大纲 + RAG 工具 + 提问内容”，比画像 Agent 更适合判断学生触达了哪个知识节点，以及该节点应如何进入成长树。
- Tool/算法层已经负责最终裁决，Student Agent 只提交候选，因此不会因为引入 Student Agent 而放大写入风险。
- 工具集合保持低耦合：如果 Agent 归属再调整，只需要替换调用者，不需要改动 `study_graph_task.py` 的核心契约。

Teacher Agent 默认只消费成长树摘要，负责把 RAG 得到的总知识库结构、学生成长树状态和画像评分融合，生成推荐或资源任务。只有当 Teacher Agent 观察到学生真实触达结果时，才可以通过同一组 tool 提交变更候选。

## 阶段 1：常量、契约模型与文件边界

### 0. 新增常量定义

建议新增到 `constant.py`：

```python
class StudyGraphNodeType(Enum):
    TREE_ROOT = "tree_root"
    KNOWLEDGE = "knowledge"


class StudyGraphEdgeType(Enum):
    PARENT_OF = "parent_of"


class StudyGraphChangeOp(Enum):
    UPSERT_KNOWLEDGE_NODE = "upsert_knowledge_node"
    ATTACH_PARENT = "attach_parent"
    UPDATE_MASTERY = "update_mastery"


class StudyGraphChangeStatus(Enum):
    ACCEPTED = "accepted"
    MERGED = "merged"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"


class StudyGraphMasteryLabel(Enum):
    WEAK = "weak"
    LEARNING = "learning"
    NORMAL = "normal"
    MASTERED = "mastered"


class StudyGraphSignal(Enum):
    LEARNED = "learned"
    PRACTICED = "practiced"
    STRUGGLED = "struggled"
    MASTERED = "mastered"


class StudyGraphDisplayStage(Enum):
    SEED = "seed"
    SPROUT = "sprout"
    BRANCH = "branch"
    FRUIT = "fruit"


class StudyGraphDisplayColor(Enum):
    WEAK = "weak"
    GROWING = "growing"
    STABLE = "stable"
    MASTERED = "mastered"
```

建议新增数值常量：

```python
STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD = 0.45
STUDY_GRAPH_DEFAULT_ROOT_ID_PREFIX = "study_tree_root"
STUDY_GRAPH_TREE_ID_PREFIX = "study_tree"
STUDY_GRAPH_NODE_ID_PREFIX = "knowledge"
STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX = "学习成长树"
STUDY_GRAPH_MASTERY_WEAK_MAX = 0.39
STUDY_GRAPH_MASTERY_LEARNING_MAX = 0.59
STUDY_GRAPH_MASTERY_NORMAL_MAX = 0.79
```

### 1. 影响的文件范围

新增：

```text
tasks/study_graph/
  __init__.py
  contracts.py
  normalizer.py
  tree_builder.py
  features.py
  storage.py

tasks/study_graph_task.py

tests/test_study_graph_contracts.py
tests/test_study_graph_normalizer.py
tests/test_study_graph_tree_builder.py
tests/test_study_graph_task.py
tests/test_study_graph_storage.py
```

API 暴露项：

```text
blueprint/study_graph_api.py
tests/test_study_graph_api.py
```

### 2. 函数级收口的完整数据流

本阶段只定义契约，不写业务流：

```text
raw dict payload
  -> contracts dataclass / typed dict normalization
  -> downstream phases consume stable dict schema
```

### 3. 精确到输入输出的函数级收口

文件：`tasks/study_graph/contracts.py`

#### `build_tree_id(user_id: int, syllabus_id: int) -> str`

输入：

```json
{"user_id": 8, "syllabus_id": 20}
```

输出：

```text
study_tree:8:20
```

逻辑：

- `user_id`、`syllabus_id` 转 int。
- 返回稳定字符串。

#### `build_root_node_id(user_id: int, syllabus_id: int) -> str`

输出：

```text
study_tree_root:8:20
```

#### `build_virtual_root_node(user_id: int, syllabus_id: int, subject_title: str | None, now_ts: int) -> dict`

输出：

```json
{
  "node_id": "study_tree_root:8:20",
  "tree_id": "study_tree:8:20",
  "type": "tree_root",
  "title": "大数据概论",
  "virtual": true,
  "created_at": 1760000000,
  "updated_at": 1760000000
}
```

逻辑：

- `title` 优先使用大纲/学科名，例如 `大数据概论`。
- 没有学科名时使用传入的 tree title。
- 仍然为空时使用 `学习成长树`。
- 该节点只用于读取和展示，不写入 manifest 的 `nodes`，也不产生真实 `parent_of` 边。

#### `build_knowledge_node_id(user_id: int, syllabus_id: int, normalized_title: str) -> str`

输出：

```text
knowledge:8:20:rowkey_hotspot
```

逻辑：

- `normalized_title` 必须非空。
- 只允许小写字母、数字、下划线、短横线。
- 超长 title 截断后加短 hash，保证稳定且不太长。

#### `build_client_change_id(user_id: int, syllabus_id: int, source_kind: str, op: str, normalized_title: str, evidence_key: str | None) -> str`

输出：

```text
student:8:20:upsert_knowledge_node:rowkey_热点:9f2a1c7b
```

逻辑：

- `source_kind` 使用稳定来源前缀，例如 `student`、`resource`、`teacher`。
- `op` 使用 `StudyGraphChangeOp` 的值。
- `normalized_title` 使用 `normalize_knowledge_title` 的输出。
- `evidence_key` 必须由稳定输入生成，不直接使用随机数。
- `evidence_key` 推荐格式：

```text
{event_kind}:{topic_or_question_hash}:{stable_event_span}
```

- `stable_event_span` 对实时交互使用请求轮次或事件序号；对资源事件优先使用资源事件自身 id。
- 最终 id 格式：

```text
{source_kind}:{user_id}:{syllabus_id}:{op}:{normalized_title}:{short_hash(evidence_key)}
```

- 同一轮 student payload 重放时必须得到相同 `client_change_id`。
- 不同知识点、不同 op、不同可靠事件必须得到不同 `client_change_id`。
- `evidence_key` 的默认构造必须只依赖稳定字段，不得引入随机数、时间戳或进程内序列：

```text
evidence_key = sha1(
  normalized_question_or_topic + "|" +
  sorted_detected_topics + "|" +
  sorted_event_signatures + "|" +
  sorted_rag_titles + "|" +
  sorted_parent_candidates
)
```

- 同一 Student Agent 处理同一组证据时，`build_client_change_id` 必须返回同一结果。
- 只要 `source_kind`、`op`、`normalized_title`、`evidence_key` 任一变化，ID 就必须变化。
- `evidence_key` 只作为幂等锚点，不作为业务排序分数。

#### `make_empty_tree(user_id: int, syllabus_id: int, title: str | None, now_ts: int) -> dict`

输出：

```json
{
  "tree_id": "study_tree:8:20",
  "user_id": 8,
  "syllabus_id": 20,
  "subject_title": "大数据概论",
  "title": "大数据概论学习树",
  "virtual_root": {
    "node_id": "study_tree_root:8:20",
    "tree_id": "study_tree:8:20",
    "type": "tree_root",
    "title": "大数据概论",
    "virtual": true
  },
  "nodes": [],
  "edges": [],
  "summary": {
    "learned_node_count": 0,
    "mastered_node_count": 0,
    "weak_node_count": 0,
    "tree_growth": 0.0,
    "last_updated_at": 1760000000
  }
}
```

#### 契约对象字段

`KnowledgeNode`：

```json
{
  "node_id": "knowledge:8:20:rowkey_hotspot",
  "tree_id": "study_tree:8:20",
  "type": "knowledge",
  "title": "RowKey 热点问题",
  "normalized_title": "rowkey_hotspot",
  "aliases": ["RowKey 热点", "热点问题"],
  "summary": "理解 RowKey 热点产生原因和规避方式",
  "parent_node_id": null,
  "mastery": {"label": "weak", "score": 0.38, "progress": 0.2},
  "display": {"growth_stage": "seed", "height": 0.38, "color_state": "weak"},
  "source": {"kind": "dialogue", "summary": "学生说 RowKey 热点很容易卡住"},
  "first_seen_at": 1760000000,
  "last_updated_at": 1760000000
}
```

`StudyGraphChange`：

```json
{
  "op": "upsert_knowledge_node",
  "client_change_id": "chg_001",
  "knowledge": {
    "title": "RowKey 热点问题",
    "summary": "RowKey 热点产生原因和规避方式",
    "aliases": ["RowKey 热点", "热点问题"],
    "node_id": null
  },
  "parent_candidate": {
    "title": "RowKey 设计",
    "existing_node_id": null,
    "reason": "属于 RowKey 设计下的子问题"
  },
  "mastery": {
    "signal": "struggled",
    "delta": -0.2,
    "label_hint": "weak"
  },
  "confidence": 0.72
}
```

### 4. 测试用例的构建描述

`tests/test_study_graph_contracts.py`

- `build_tree_id` 对相同输入稳定。
- `build_knowledge_node_id` 对同一 normalized title 稳定。
- `build_client_change_id` 对同一 payload evidence 稳定，对不同知识点/op/事件区分。
- `build_virtual_root_node` 优先使用学科/大纲名作为展示根节点标题。
- 空树 summary 字段完整。
- KnowledgeNode 最小字段可序列化为 JSON。
- 缺少 `user_id`、`syllabus_id` 时契约函数抛出明确错误。

## 阶段 2：Manifest 存储与 SQL 迁移边界

### 0. 新增常量定义

建议新增 manifest 路径常量：

```python
STUDY_GRAPH_ROOT = "study_graph"
STUDY_GRAPH_MANIFEST_NAME = "manifest.json"
STUDY_GRAPH_CHANGE_LOG_NAME = "change_log.jsonl"
```

### 1. 影响的文件范围

新增：

```text
tasks/study_graph/storage.py
tests/test_study_graph_storage.py
```

迁移目标，当前不新增：

```text
schemas/student_learning_tree.py
schemas/student_learning_tree_node.py
schemas/student_learning_tree_edge.py
schemas/student_learning_tree_change_log.py
repositories/study_graph_repo.py
```

这些 SQL schema 与 SQL repository 作为迁移目标保留在本阶段末尾，不进入当前 manifest 实现范围。

### 2. 函数级收口的完整数据流

```text
study_graph_task / tree_builder
  -> tasks.study_graph.storage
      -> study_graph/user_{user_id}/syllabus_{syllabus_id}/manifest.json
      -> study_graph/user_{user_id}/syllabus_{syllabus_id}/change_log.jsonl
  -> return dict data
```

Storage 只做读写，不承载节点归并、父节点裁决、掌握度计算。manifest 是当前运行时存储，不是测试 fixture。`apply_learning_tree_changes` 不感知底层是 manifest 还是 SQL。

### 3. 精确到输入输出的函数级收口

#### 文件结构

```text
study_graph/
  user_8/
    syllabus_20/
      manifest.json
      change_log.jsonl
```

#### `manifest.json`

```json
{
  "schema_version": 1,
  "tree_id": "study_tree:8:20",
  "user_id": 8,
  "syllabus_id": 20,
  "subject_title": "大数据概论",
  "title": "大数据概论学习树",
  "nodes": [],
  "edges": [],
  "summary": {
    "learned_node_count": 0,
    "mastered_node_count": 0,
    "weak_node_count": 0,
    "tree_growth": 0.0,
    "last_updated_at": 1760000000
  },
  "created_at": 1760000000,
  "updated_at": 1760000000
}
```

#### `change_log.jsonl`

每行一个 JSON 对象：

```json
{"client_change_id":"chg_001","op":"upsert_knowledge_node","status":"accepted","request":{},"result":{},"created_at":1760000000}
```

#### `get_tree(user_id: int, syllabus_id: int) -> dict | None`

输出：

```json
{
  "tree_id": "study_tree:8:20",
  "user_id": 8,
  "syllabus_id": 20,
  "title": "大数据概论学习树",
  "summary": {},
  "created_at": 1760000000,
  "updated_at": 1760000000
}
```

逻辑：

- 读取 manifest。
- 文件不存在返回 None。
- JSON 损坏返回 None，并由调用方按空树恢复或返回 structured error。

#### `create_tree_if_missing(user_id: int, syllabus_id: int, title: str | None, now_ts: int) -> dict`

逻辑：

- manifest 存在则返回。
- manifest 不存在则创建目录和空 manifest。
- manifest 可保存 `subject_title`，优先来自真实大纲/学科名，例如 `大数据概论`；没有时回退到传入 `title`。
- 不创建实体 root 节点。`parent_node_id = null` 表示顶层知识节点；读取展示层生成以学科/大纲命名的虚拟 root，并把所有顶层节点挂到虚拟 root 下用于布局。

#### `load_tree_manifest(user_id: int, syllabus_id: int) -> dict`

返回完整 manifest，保证包含 `nodes`、`edges`、`summary`。

#### `save_tree_manifest(user_id: int, syllabus_id: int, manifest: dict) -> dict`

逻辑：

- 写入临时文件。
- 原子替换 manifest。
- 更新 `updated_at`。

#### `list_nodes(tree_id: str) -> list[dict]`

从 manifest 返回所有节点，按 `first_seen_at ASC`。

#### `list_edges(tree_id: str) -> list[dict]`

从 manifest 返回所有边。

#### `upsert_node(tree_id: str, node: dict) -> dict`

逻辑：

- `node_id` 存在则更新。
- 不存在则插入。
- 通过扫描 manifest 维护 `normalized_title` 唯一。
- `parent_node_id` 可以为 null；此时表示顶层知识节点。读取展示层临时挂到虚拟 root，但存储层不写 root 边。

#### `upsert_edge(tree_id: str, source: str, target: str, edge_type: str, now_ts: int) -> dict`

逻辑：

- 生成稳定 `edge_id = f"{tree_id}:{edge_type}:{source}:{target}"` 的 hash 或清洗版本。
- 已存在则更新 `updated_at`。
- 不存在则插入。

#### `append_change_log(tree_id: str, entry: dict) -> dict`

逻辑：

- 扫描 `change_log.jsonl` 检查同一 `client_change_id` 是否已存在。
- 已存在则返回旧 log，并标记 `duplicate=True`。
- 不存在则追加一行 JSON。

#### `get_change_log(tree_id: str, client_change_id: str) -> dict | None`

用于提交前幂等检查。

#### `update_summary(tree_id: str, summary: dict, now_ts: int) -> dict`

更新 manifest 的 `summary` 和 `updated_at`。

#### SQL 迁移目标

统一表结构时，迁移到独立命名空间，避免污染现有业务表：

```text
study_graph_tree
study_graph_node
study_graph_edge
study_graph_change_log
```

建议字段：

```text
study_graph_tree(tree_id, user_id, syllabus_id, title, summary_json, created_at, updated_at, UNIQUE(user_id, syllabus_id))
study_graph_node(node_id, tree_id, type, title, normalized_title, aliases_json, summary, parent_node_id, mastery_label, mastery_score, progress, display_json, source_kind, source_summary, first_seen_at, last_updated_at, UNIQUE(tree_id, normalized_title))
study_graph_edge(edge_id, tree_id, source_node_id, target_node_id, edge_type, created_at, updated_at, UNIQUE(tree_id, source_node_id, target_node_id, edge_type))
study_graph_change_log(log_id, tree_id, client_change_id, op, status, source_kind, source_summary, request_json, result_json, created_at, UNIQUE(tree_id, client_change_id))
```

### 4. 测试用例的构建描述

`tests/test_study_graph_storage.py`

- 创建空树后可读取。
- 同一 `(user_id, syllabus_id)` 重复 `create_tree_if_missing` 不重复创建。
- `upsert_node` 新增节点。
- 同 `normalized_title` 重复 upsert 不重复创建。
- `upsert_edge` 重复调用保持唯一。
- `append_change_log` 对同一 `client_change_id` 幂等。
- `update_summary` 后 `get_tree` 能读取新 summary。

SQL 迁移不属于当前实现验收，只要求 manifest 数据结构可完整迁移。

## 阶段 3：归一化与读取上下文

### 0. 新增常量定义

```python
STUDY_GRAPH_TITLE_STOP_SUFFIXES = ["问题", "知识点", "概念", "内容"]
STUDY_GRAPH_MAX_CONTEXT_CANDIDATES = 8
```

### 1. 影响的文件范围

新增：

```text
tasks/study_graph/normalizer.py
tasks/study_graph_task.py
tests/test_study_graph_normalizer.py
tests/test_study_graph_task.py
```

可能读取：

```text
tasks/learning_profile_task.py
repositories.user_syllabus_repo.py
repositories.syllabus_repo.py
```

### 2. 函数级收口的完整数据流

```text
get_student_learning_tree_context
  -> validate user_id/syllabus_id/query
  -> storage.create_tree_if_missing
  -> storage.list_nodes
  -> load personal syllabus hints
  -> normalize query
  -> rank tree candidates once
  -> return context
```

### 3. 精确到输入输出的函数级收口

#### `normalize_knowledge_title(title: str) -> str`

输入：

```text
" RowKey 热点问题 "
```

输出：

```text
"rowkey_热点"
```

逻辑：

- strip。
- 全角标点转半角。
- 多空格合并。
- 英文小写。
- 保守移除低信息后缀：`问题`、`知识点`、`概念`、`内容`。
- 中文保留原字；英文和数字保留。
- 分隔符统一为 `_`。
- 如果结果为空，返回空字符串，由上层拒绝。

#### `normalize_aliases(aliases: Any) -> list[str]`

逻辑：

- 只接受字符串列表。
- 每个 alias strip。
- 去重。
- 最多保留 8 个。

#### `rank_tree_candidates(nodes: list[dict], query: str, max_candidates: int) -> list[dict]`

输出项：

```json
{
  "node_id": "knowledge:8:20:rowkey_hotspot",
  "title": "RowKey 热点问题",
  "normalized_title": "rowkey_热点",
  "mastery": {"label": "weak", "score": 0.38},
  "score": 0.92,
  "matched_by": "normalized_title|alias|title|substring",
  "candidate_roles": ["existing_node", "possible_parent"]
}
```

排序逻辑：

- normalized title 精确命中最高。
- alias 精确命中次之。
- title 包含 query 或 query 包含 title。
- 字符重叠得分。
- `candidate_roles` 由上层按需要解释：精确命中适合作为查重候选，已存在且更泛化的节点适合作为父节点候选。
- 最多返回 `max_candidates`。

评分公式：

```text
query_norm = normalize_knowledge_title(query)
candidate_norm = normalized_title

exact_title = 1.0 if candidate_norm == query_norm else 0.0
alias_exact = 1.0 if any(normalize_knowledge_title(alias) == query_norm for alias in aliases) else 0.0
substring = 1.0 if (query_norm in candidate_norm or candidate_norm in query_norm) else 0.0
token_jaccard = |tokens(query_norm) ∩ tokens(candidate_norm)| / |tokens(query_norm) ∪ tokens(candidate_norm)|
prefix = common_prefix_len(query_norm, candidate_norm) / max(len(query_norm), len(candidate_norm), 1)
levenshtein = 1 - normalized_edit_distance(query_norm, candidate_norm)

score = clamp(
  0.42 * exact_title +
  0.24 * alias_exact +
  0.16 * substring +
  0.10 * token_jaccard +
  0.05 * prefix +
  0.03 * levenshtein,
  0.0,
  1.0
)
```

- 若 `exact_title = 1.0`，直接视为强候选。
- 若 `alias_exact = 1.0` 且无歧义，同样视为强候选。
- 父候选可在上式基础上额外乘以 `parent_boost = 1.05`，但最终仍需 `clamp(0, 1)`。
- `candidate_roles` 只改变解释，不改变基础分值。
- `max_candidates` 只截断排序结果，不改变分值。

#### `load_personal_syllabus_hints(user_id: int, syllabus_id: int, query: str, max_candidates: int) -> list[dict]`

输出：

```json
[
  {
    "week_index": 6,
    "title": "HBase RowKey 设计",
    "content": "RowKey 热点、散列、预分区",
    "competance": "weak",
    "competance_progress": 1,
    "score": 0.81
  }
]
```

逻辑：

- 可复用个人大纲读取能力。
- 不生成树节点，只作为 parent/summary/mastery hints。

#### `get_student_learning_tree_context(user_id: int, syllabus_id: int, query: str, max_candidates: int = 8) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "query": "RowKey 热点问题",
  "max_candidates": 8
}
```

输出：

```json
{
  "tree_id": "study_tree:8:20",
  "query": "RowKey 热点问题",
  "normalized_query": "rowkey_热点",
  "ranked_candidates": [],
  "personal_syllabus_hints": [],
  "warnings": []
}
```

内部逻辑：

- 创建或读取树。
- 读取现有节点。
- 只计算一次 `ranked_candidates`。
- Agent 根据 `candidate_roles` 判断候选是更适合作为查重对象，还是更适合作为父节点。
- 读取个人大纲 hints。
- 不写节点、不写边。

### 4. 测试用例的构建描述

`tests/test_study_graph_normalizer.py`

- title strip、大小写、标点归一。
- 保守去掉低信息后缀。
- 空 title 返回空。
- aliases 去重。
- query 能命中 normalized title。
- query 能命中 alias。

`tests/test_study_graph_task.py`

- 空树 context 返回空候选。
- 已有同名节点时 `ranked_candidates` 返回该节点并标记 `existing_node`。
- 已有父节点时 `ranked_candidates` 返回该父节点并标记 `possible_parent`。
- personal syllabus hint 能进入输出。
- `max_candidates` 生效。

## 阶段 4：核心算法收口 `apply_learning_tree_changes`

### 0. 新增常量定义

```python
STUDY_GRAPH_SIGNAL_DEFAULT_DELTA = {
    "learned": 0.15,
    "practiced": 0.08,
    "struggled": -0.12,
    "mastered": 0.25,
}
STUDY_GRAPH_DELTA_MIN = -0.3
STUDY_GRAPH_DELTA_MAX = 0.3
```

### 1. 影响的文件范围

新增：

```text
tasks/study_graph/tree_builder.py
tests/test_study_graph_tree_builder.py
```

修改：

```text
tasks/study_graph_task.py
```

### 2. 函数级收口的完整数据流

```text
submit_learning_tree_changes
  -> validate_change_request
  -> storage.create_tree_if_missing
  -> load_tree_snapshot
  -> normalize_change_candidates
  -> apply_learning_tree_changes
      -> check_idempotent_results
      -> resolve_target_node
      -> resolve_parent_node
      -> compute_mastery_update
      -> compute_display_update
      -> build_change_result
      -> build_write_operations
  -> persist_write_operations
  -> recompute_tree_summary
  -> return public response
```

### 3. 精确到输入输出的函数级收口

#### `validate_change_request(payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "changes": [],
  "source": {"kind": "dialogue", "summary": "学生说 RowKey 热点卡住"},
  "timestamp": 1760000000
}
```

输出：

```json
{
  "valid": true,
  "payload": {},
  "errors": []
}
```

规则：

- `user_id`、`syllabus_id` 必须可转 int。
- `changes` 必须是非空 list，最多限制 20 条。
- 每个 change 必须有 `op`、`client_change_id`。
- `op` 只允许三种。
- `source.summary` 必须存在或从 change reason 降级生成。

#### `normalize_change_candidates(changes: list[dict]) -> list[dict]`

输出 change 增补字段：

```json
{
  "normalized_title": "rowkey_热点",
  "normalized_aliases": ["rowkey_热点", "热点"],
  "confidence": 0.72
}
```

规则：

- confidence clamp 到 0-1。
- 缺 title 的 upsert change 直接标记 invalid。
- `delta` clamp 不在此处做，放 mastery 阶段。

#### `apply_learning_tree_changes(input_payload: dict) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "tree": {"tree_id": "study_tree:8:20", "nodes": [], "edges": [], "summary": {}},
  "changes": [],
  "source": {"kind": "dialogue", "summary": "学生说 RowKey 热点卡住"},
  "existing_change_logs": [],
  "now_ts": 1760000000
}
```

输出：

```json
{
  "tree_id": "study_tree:8:20",
  "results": [],
  "write_operations": [],
  "summary_delta": {},
  "warnings": []
}
```

内部逻辑：

- 对每个 change 单独产出 result。
- 若 `client_change_id` 已在 change log 中，返回旧 result，status 可为 `skipped` 或沿用旧 status，不生成写操作。
- 低 confidence 返回 `needs_review`，不生成 node/edge 写操作，但可生成 change_log。
- `upsert_knowledge_node`：
  - `resolve_target_node`
  - `resolve_parent_node`
  - `compute_mastery_update`
  - `compute_display_update`
  - build upsert node/edge/log operations
- `attach_parent`：
  - 目标节点必须存在。
  - 父节点必须存在，可以是任意已有知识节点，包括 `parent_node_id = null` 的顶层节点。
  - 检查环。
  - 只生成 edge/node parent update/log operations。
- `update_mastery`：
  - 目标节点必须存在。
  - 只更新 mastery/display/log。

#### `resolve_target_node(tree: dict, change: dict) -> dict`

输出：

```json
{
  "action": "create|update|merge|reject|needs_review",
  "node_id": "knowledge:8:20:rowkey_hotspot",
  "matched_by": "id|normalized_title|alias|none|ambiguous_alias",
  "existing_node": null,
  "reason": ""
}
```

规则：

- change 指定 `knowledge.node_id` 且属于当前树：`update`。
- `normalized_title` 命中唯一节点：`merge`。
- alias 命中唯一节点：`merge`。
- alias 命中多个节点：`needs_review`。
- title 为空：`reject`。
- 否则：`create`，node_id 由 `build_knowledge_node_id` 生成。

#### `resolve_parent_node(tree: dict, change: dict, target_resolution: dict) -> dict`

输出：

```json
{
  "action": "attach|keep_existing|top_level|needs_review|reject",
  "parent_node_id": "knowledge:8:20:hbase_rowkey",
  "reason": ""
}
```

规则：

- 目标节点已有父节点：默认 `keep_existing`。
- `parent_candidate.existing_node_id` 属于当前树：`attach`。
- `parent_candidate.title` normalized 后命中唯一节点：`attach`。
- 父节点会形成环：`reject`。
- 找不到父节点：`top_level`，`parent_node_id` 保持 null，不创建 `parent_of` 边。该节点是顶层知识节点，读取展示层临时挂到虚拟 root。
- 顶层知识节点仍然可以作为其他节点的合法父节点；例如 A 的 `parent_node_id = null`，后续 B 可以通过 `attach_parent` 挂到 A 下，此时只更新 B 的 `parent_node_id = A.node_id` 并写入 A -> B 的 `parent_of` 边。
- 不自动创建父节点，避免 Agent 虚构层级。

#### `compute_mastery_update(current_mastery: dict | None, mastery_change: dict | None, confidence: float) -> dict`

输出：

```json
{
  "before": {"label": "normal", "score": 0.55, "progress": 0.4},
  "after": {"label": "weak", "score": 0.38, "progress": 0.2},
  "effective_delta": -0.17,
  "reason": "signal=struggled"
}
```

规则：

```text
base_score = current.score or 0.2
input_delta = mastery_change.delta if numeric else default_delta[signal]
effective_delta = clamp(input_delta, -0.3, 0.3) * clamp(confidence, 0.2, 1.0)
score_after = clamp(base_score + effective_delta, 0, 1)
progress_after = score_after
label_after = score_to_label(score_after)
```

`label_hint` 只能影响 reason，不直接覆盖 score。

#### `score_to_mastery_label(score: float) -> str`

输出：

```text
weak|learning|normal|mastered
```

阈值：

```text
0.00 <= score <= 0.39 -> weak
0.40 <= score <= 0.59 -> learning
0.60 <= score <= 0.79 -> normal
0.80 <= score <= 1.00 -> mastered
```

规则：

- 输入 score 先 clamp 到 `[0, 1]`。
- `compute_mastery_update`、`compute_display_update`、`get_learning_tree_features` 必须使用同一套阈值。
- `mastery.label` 由 `score_to_mastery_label` 生成；`label_hint` 不能直接覆盖阈值判断。

#### `compute_display_update(mastery_after: dict, node_age_days: float = 0, activity: dict | None = None) -> dict`

输出：

```json
{"growth_stage": "seed", "height": 0.38, "color_state": "weak"}
```

规则：

- weak -> seed/weak
- learning -> sprout/growing
- normal -> branch/stable
- mastered -> fruit/mastered
- height = mastery.score

#### `build_write_operations(results: list[dict]) -> list[dict]`

输出：

```json
[
  {"type": "upsert_node", "node": {}},
  {"type": "upsert_edge", "source": "...", "target": "...", "edge_type": "parent_of"},
  {"type": "append_change_log", "entry": {}}
]
```

规则：

- rejected/needs_review 只写 change log。
- accepted/merged 写 node/log；有父子关系时写 edge。
- `top_level` 的新节点只写 node/log，不写 edge；读取展示时由虚拟 root 临时承接。
- update_mastery 只写 node/log。

### 4. 测试用例的构建描述

`tests/test_study_graph_tree_builder.py`

- 空树 upsert 创建顶层节点，并由读取展示层临时挂到虚拟 root。
- 已有同 normalized title 节点时 merge。
- alias 命中唯一节点时 merge。
- alias 命中多个节点时 needs_review。
- 父候选 existing_node_id 命中时 attach。
- 父候选 title 命中时 attach。
- 父候选不存在时创建顶层节点，不写 parent_of 边，读取展示层临时挂到虚拟 root。
- 顶层节点可以作为后续 `attach_parent` 的父节点。
- 环检测 reject。
- struggled 降低 mastery。
- mastered 提高 mastery。
- 低 confidence 返回 needs_review 且不写 node/edge。
- 每个 change 都有 result。
- 重复 client_change_id 不重复生成写操作。

## 阶段 5：Tool 层实现

### 0. 新增常量定义

无新增。

### 1. 影响的文件范围

新增或修改：

```text
tasks/study_graph_task.py
tasks/study_graph/features.py
tests/test_study_graph_task.py
```

### 2. 函数级收口的完整数据流

#### 写入工具链

```text
submit_learning_tree_changes
  -> validate_change_request
  -> storage.create_tree_if_missing
  -> load_tree_snapshot
  -> normalize_change_candidates
  -> tree_builder.apply_learning_tree_changes
  -> persist_write_operations
  -> recompute_tree_summary
  -> storage.update_summary
  -> return public result
```

#### 读取工具链

```text
get_student_learning_tree
  -> storage.create_tree_if_missing
  -> storage.list_nodes
  -> storage.list_edges
  -> build virtual root
  -> build summary
  -> return tree
```

#### 摘要工具链

```text
get_learning_tree_features
  -> get_student_learning_tree
  -> compute features
  -> return compact summary for Agent
```

### 3. 精确到输入输出的函数级收口

#### `submit_learning_tree_changes(user_id: int, syllabus_id: int, changes: list[dict], source: dict | None = None, timestamp: int | None = None) -> dict`

输入：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "changes": [
    {
      "op": "upsert_knowledge_node",
      "client_change_id": "chg_001",
      "knowledge": {"title": "RowKey 热点问题"},
      "mastery": {"signal": "struggled"},
      "confidence": 0.72
    }
  ],
  "source": {"kind": "dialogue", "summary": "学生说 RowKey 热点卡住"},
  "timestamp": 1760000000
}
```

输出：

```json
{
  "success": true,
  "tree_id": "study_tree:8:20",
  "results": [
    {
      "client_change_id": "chg_001",
      "status": "accepted",
      "created_node_id": "knowledge:8:20:rowkey_热点",
      "updated_node_id": null,
      "attached_parent_id": null,
      "reason": "created new knowledge node without parent edge; display layer may attach it to virtual root"
    }
  ],
  "created_nodes": [],
  "updated_nodes": [],
  "created_edges": [],
  "summary": {},
  "warnings": []
}
```

失败输出：

```json
{
  "success": false,
  "error_code": "invalid_request",
  "error_message": "changes must be a non-empty list",
  "results": [],
  "warnings": []
}
```

#### `persist_write_operations(storage, operations: list[dict]) -> dict`

输出：

```json
{
  "created_nodes": [],
  "updated_nodes": [],
  "created_edges": [],
  "logs": [],
  "errors": []
}
```

逻辑：

- 遍历 operation。
- `upsert_node` 调 storage。
- `upsert_edge` 调 storage。
- `append_change_log` 调 storage。
- 如果任一 operation 失败，返回 `success=false`；manifest 写入应使用临时文件替换，避免半写入状态。

#### `get_student_learning_tree(user_id: int, syllabus_id: int, include_debug: bool = False) -> dict`

输出：

```json
{
  "success": true,
  "tree": {
    "tree_id": "study_tree:8:20",
    "user_id": 8,
    "syllabus_id": 20,
    "subject_title": "大数据概论",
    "title": "大数据概论学习树",
    "virtual_root": {
      "node_id": "study_tree_root:8:20",
      "tree_id": "study_tree:8:20",
      "type": "tree_root",
      "title": "大数据概论",
      "virtual": true
    },
    "nodes": [],
    "edges": [],
    "summary": {}
  },
  "debug": {}
}
```

逻辑：

- 默认带虚拟 root。虚拟 root 的标题优先使用学科/大纲名，例如 `大数据概论`；前端可直接用它作为树的中心展示节点。
- `include_debug=false` 时不返回 change logs。

#### `get_learning_tree_features(user_id: int, syllabus_id: int, stale_days: int = 14) -> dict`

输出：

```json
{
  "success": true,
  "tree_id": "study_tree:8:20",
  "learned_topics": ["RowKey 热点问题"],
  "weak_topics": ["RowKey 热点问题"],
  "mastered_topics": [],
  "recently_grown": ["RowKey 热点问题"],
  "stale_topics": [],
  "tree_growth": 0.18,
  "updated_at": 1760000000
}
```

逻辑：

- learned_topics = 所有 knowledge node title。
- weak_topics = mastery.label == weak。
- mastered_topics = mastery.label == mastered。
- recently_grown = `last_updated_at >= now - 7d`。
- stale_topics = `last_updated_at <= now - stale_days` 且未 mastered。
- tree_growth = 平均 mastery.score 或 summary 中缓存值。

### 4. 测试用例的构建描述

`tests/test_study_graph_task.py`

- submit 成功创建节点。
- submit 参数错误返回 structured error。
- submit 低 confidence 返回 needs_review。
- submit 重复 client_change_id 幂等。
- manifest 写入失败时返回错误且不静默。
- get tree 返回以学科/大纲命名的 virtual root + nodes + edges。
- get features 正确区分 weak/mastered/recent/stale。

## 阶段 6：API 与 Agent 接入边界

### 0. 新增常量定义

无新增。

### 1. 影响的文件范围

API 暴露项：

```text
blueprint/study_graph_api.py
tests/test_study_graph_api.py
```

可能修改：

```text
blueprint/user_api.py
app.py
tasks/student_agent_task.py
tasks/learning_profile_task.py
```

### 2. 函数级收口的完整数据流

#### 前端读取

```text
GET /api/student_learning_tree
  -> study_graph_task.get_student_learning_tree
  -> return tree
```

#### Agent 写入

```text
student_agent_task
  -> RAG search tool
  -> get_student_learning_tree_context
  -> submit_learning_tree_changes
  -> get_learning_tree_features
```

当前不要求前端直接写树。前端只读。

### 3. 精确到输入输出的函数级收口

#### `GET /api/student_learning_tree`

Query：

```text
user_id=8&syllabus_id=20&include_debug=false
```

响应：

```json
{
  "success": true,
  "tree": {
    "nodes": [],
    "edges": [],
    "summary": {}
  }
}
```

错误：

```json
{"success": false, "error_code": "missing_user_id", "error_message": "user_id is required"}
```

#### `POST /api/student_learning_tree/features`

当前可不开放给前端，只给内部 task 调用。如果开放：

```json
{"user_id": 8, "syllabus_id": 20}
```

响应同 `get_learning_tree_features`。

#### Agent tool 注册建议

注册到 Student Agent：

- `get_student_learning_tree_context`
- `submit_learning_tree_changes`
- `get_learning_tree_features`

Student Agent 同时可调用 RAG/search 工具，用于把当前提问内容对齐到总知识库上下文，但 RAG 结果不直接写入成长树；它只能辅助 Student Agent 产出变更候选。

Teacher Agent 默认只读：

- `get_learning_tree_features`

Teacher Agent 的典型流程：

```text
RAG 查询总知识库
  -> get_learning_tree_features 读取学生状态
  -> 生成推荐/资源任务
  -> 学生触达结果进入 Student Agent
  -> Student Agent submit_learning_tree_changes
```

如果 Teacher Agent 直接接收可靠的触达事件，也可以复用 `submit_learning_tree_changes`，但不为它单独创建 StudyGraph Agent。

### 4. 测试用例的构建描述

`tests/test_study_graph_api.py`

- GET 缺 user_id 返回错误。
- GET 缺 syllabus_id 返回错误。
- GET 正常返回 tree。
- GET include_debug=false 不返回 logs。
- POST features 返回摘要。

Agent 接入测试不要求真实 LLM；可在 Student Agent 集成完成后补真实 Agent 调度测试。

## 阶段 7：与 Student Agent、画像、资源生成的协同

### 0. 新增常量定义

无新增。

### 1. 影响的文件范围

可能修改：

```text
tasks/student_agent_task.py
tasks/learning_profile_task.py
tasks/learning_task.py
tasks/generative_task.py
docs/student_agent_workflow.md
docs/learning_profile_agent_workflow.md
tests/test_profile_personal_syllabus_full_chain.py
```

### 2. 函数级收口的完整数据流

#### Student Agent 后置写树

```text
student_agent receives learning payload
  -> load personal syllabus context
  -> RAG query total knowledge base
  -> get_student_learning_tree_context
  -> derive study graph changes from question/event/context payload
  -> submit_learning_tree_changes
  -> get_learning_tree_features
``` 

这是默认写入路径。Student Agent 不直接写树，只调用 `submit_learning_tree_changes` 提交候选；`apply_learning_tree_changes` 负责最终接受、合并、拒绝或降级为待审核。画像 Agent 不维护成长树，只维护个人教学大纲和整体表现多维分数。

#### `StudentAgentDispatchPayload`

真实 Student Agent 集成测和上游总 Agent 传参必须使用同一份固定 payload schema。总 Agent 负责填充这个 payload，Student Agent 只消费，不再自行发明字段。

```json
{
  "dispatch_id": "dispatch:8:20:20260519_001",
  "source_kind": "total_agent",
  "user_id": 8,
  "syllabus_id": 20,
  "subject_title": "大数据概论",
  "question": "RowKey 如何避免热点？",
  "learning_goal": "掌握 HBase RowKey 设计",
  "personal_syllabus_context": {
    "learning_goal": "掌握 HBase RowKey 设计",
    "matched_weeks": [
      {"week_index": 1, "title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}
    ]
  },
  "rag_context": [
    {"title": "HBase RowKey 设计", "summary": "RowKey 热点通常来自单调递增键或访问集中。"}
  ],
  "detected_topics": [
    {"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}
  ],
  "events": [
    {"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": false}
  ],
  "parent_candidates": [],
  "source": {
    "kind": "total_agent",
    "summary": "总 Agent 根据用户提问、画像和 RAG 结果生成 Student Agent 学习任务"
  },
  "timestamp": 1760000000
}
```

字段约束：

- `dispatch_id` 必须稳定，可由总 Agent 任务 id、user_id、syllabus_id 和轮次拼出。
- `source_kind` 固定为 `total_agent`，用于和学生直传事件区分。
- `question` 是用户当前问题或学习意图的原始表达。
- `personal_syllabus_context` 是 Student Agent 的本地学习大纲视图，不得为空。
- `rag_context` 可为空，但若要写树，必须同时存在触达证据字段。
- `detected_topics`、`events` 是判断是否触达的主证据。
- `parent_candidates` 只允许提供候选父节点，不允许单独触发 child 创建。
- `source.summary` 只描述上游任务来源，不承担证据功能。

真实 Student Agent 集成测试必须直接使用该 payload schema 作为 `run_sync(...)` 的入参，避免每个测试各自定义一版输入格式。

#### Teacher Agent 推荐消费

```text
Teacher Agent receives learning request
  -> RAG query total knowledge base
  -> get_learning_tree_features
  -> decide recommendation/resource payload
  -> generative_task generate resource
```

Teacher Agent 不负责维护成长树。它通过 RAG 获取总知识库结构，通过 `get_learning_tree_features` 获取学生状态，然后决定推荐或资源生成任务。

#### 资源完成后写树

```text
resource completion event
  -> derive practiced/learned change
  -> submit_learning_tree_changes
```

建议先让资源完成事件进入 Student Agent 的事件归一化链路，再由 Student Agent 统一提交成长树变更。只有当资源事件已经有稳定、可信的知识点字段时，才直接调用 `submit_learning_tree_changes`。

### 3. 精确到输入输出的函数级收口

#### `build_study_graph_changes_from_student_payload(payload: dict) -> list[dict]`

输入：

```json
{
  "question": "我不理解 RowKey 热点为什么会集中到一个 Region。",
  "personal_syllabus_context": {
    "subject_title": "大数据概论",
    "matched_weeks": [{"title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}]
  },
  "rag_context": [{"title": "HBase RowKey 设计", "summary": "热点通常来自单调递增 RowKey 或访问集中。"}],
  "events": [{"kind": "answer", "topic": "RowKey 热点", "is_correct": false}]
}
```

输出：

```json
[
  {
    "op": "upsert_knowledge_node",
    "client_change_id": "student:8:20:rowkey_hotspot:1760000000",
    "knowledge": {"title": "RowKey 热点", "summary": "Student Agent 识别为已触达且薄弱的知识点"},
    "mastery": {"signal": "struggled", "label_hint": "weak"},
    "confidence": 0.7
  }
]
```

逻辑：

证据判定公式：

```text
evidence_score = clamp(
  0.40 * question_hit +
  0.35 * event_hit +
  0.25 * detected_topic_hit +
  0.10 * personal_syllabus_hit +
  0.00 * rag_only_hit,
  0.0,
  1.0
)
```

其中：

- `question_hit = 1.0` 当 `question` 或对话文本明确指向该知识点，否则为 `0.0`
- `event_hit = 1.0` 当 `events` 中存在该知识点的 answer/resource/practice 证据，否则为 `0.0`
- `detected_topic_hit = max(confidence of matched detected_topics)`，若未命中则为 `0.0`
- `personal_syllabus_hit = 1.0` 当个人教学大纲当前周或匹配条目明确包含该知识点，否则为 `0.0`
- `rag_only_hit = 1.0` 仅当只有 RAG 相关信息、没有任何触达证据时，否则为 `0.0`

决策阈值：

```text
if evidence_score < 0.60:
    return []
if 0.60 <= evidence_score < 0.80:
    allow upsert_knowledge_node only if detected_topic_hit or event_hit == 1.0
if evidence_score >= 0.80:
    allow upsert_knowledge_node and update_mastery
```

约束：

- 只从高置信 student payload evidence 中抽取。
- RAG 结果只能作为解释、摘要、别名和父候选辅助，不能直接强制创建未触达知识节点。
- 只有 `detected_topics`、`question`、`events` 中至少一项能证明学生已经触达该知识点时，才允许生成 `upsert_knowledge_node` 或 `update_mastery`。
- 只有 `rag_context`、没有 `detected_topics`、没有题目/对话/资源事件指向该知识点时，必须返回空 changes。
- `parent_candidates` 必须绑定 `child_title`，且 child 必须来自已触达证据；不能只凭 RAG 父候选创建 child。
- `client_change_id` 必须稳定，避免重复处理同一轮学习事件时重复长节点。
- 没有明确知识点时不提交。
- 这只是 Student Agent 内部的候选生成函数，不是最终调度测；真正的集成测需要验证 Student Agent 自己串起工具链完成建树。

#### `build_study_graph_changes_from_resource_event(event: dict) -> list[dict]`

输入：

```json
{
  "resource_type": "quiz",
  "topic": "RowKey 热点",
  "status": "completed",
  "score": 0.8
}
```

输出：

```json
[
  {
    "op": "upsert_knowledge_node",
    "client_change_id": "resource:quiz:rowkey_hotspot:...",
    "knowledge": {"title": "RowKey 热点"},
    "mastery": {"signal": "practiced", "delta": 0.08},
    "confidence": 0.65
  }
]
```

资源事件写树纳入 Student Agent 的事件归一化链路。只有当资源事件包含稳定、可信的知识点字段时才生成 change；缺少可靠 topic 时不提交。

### 4. 测试用例的构建描述

- student payload 中有明确触达且薄弱的知识点时生成 struggled change。
- student payload 中只有 RAG 知识、没有学生触达证据时不生成 change。
- 同一 student payload 刷新生成稳定 client_change_id。
- RAG-only payload 不生成任何 change。
- resource event completed 生成 practiced change。
- resource event failed 不生成 mastered/learned change。
- `build_study_graph_changes_from_student_payload` 的单测只覆盖候选生成，不替代真实 Student Agent 集成测。

## 阶段 8：完整测试分层与验收

### 0. 新增常量定义

无新增。

### 1. 影响的文件范围

新增：

```text
tests/test_study_graph_contracts.py
tests/test_study_graph_normalizer.py
tests/test_study_graph_tree_builder.py
tests/test_study_graph_task.py
tests/test_study_graph_storage.py
tests/test_study_graph_student_payload_flow.py
tests/test_study_graph_agent_choice.py
tests/test_study_graph_api.py
```

修改：

```text
tests/TEST_REPORT.md
pytest.ini
```

真实 Student Agent 集成必须新增：

```text
tests/test_study_graph_agent_choice.py
```

### 2. 函数级收口的完整数据流

单元测试：

```text
contracts -> normalizer -> tree_builder -> storage -> task -> api
```

集成测试：

```text
student payload round 1..N
  -> RAG/search context
  -> build_study_graph_changes_from_student_payload
  -> submit_learning_tree_changes
  -> tree updated
  -> get_student_learning_tree / get_learning_tree_features
```

集成测试分两层：

```text
student payload round 1..N
  -> RAG/search context
  -> build_study_graph_changes_from_student_payload
  -> submit_learning_tree_changes
  -> tree updated
  -> get_student_learning_tree / get_learning_tree_features
```

```text
real Student Agent choice test
  -> real LLM
  -> tool trace
  -> RAG/search context
  -> get_student_learning_tree_context
  -> submit_learning_tree_changes
  -> get_learning_tree_features
```

第一层保留为 payload 回归测试；第二层必须新增，级别对齐 `tests/test_learning_profile_agent_choice.py`，验证 Student Agent 收到 payload 后会自己调度自己的工具链完成建树。

### 3. 精确到输入输出的函数级收口

测试命令建议：

```bash
python -m pytest -q tests/test_study_graph_contracts.py tests/test_study_graph_normalizer.py tests/test_study_graph_tree_builder.py tests/test_study_graph_storage.py tests/test_study_graph_task.py
```

多轮 payload 集成测试：

```bash
python -m pytest -q tests/test_study_graph_student_payload_flow.py
```

如果实现 API：

```bash
python -m pytest -q tests/test_study_graph_api.py
```

真实 Student Agent 集成测试：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_study_graph_agent_choice.py -m llm
```

### 4. 测试用例的构建描述

#### 单元验收

必须验收：

- 空树创建。
- 同名节点合并。
- alias 命中合并。
- ambiguous alias 返回 needs_review。
- 父节点 attach。
- 父节点不存在时节点 `parent_node_id = null`，表示顶层知识节点；不写 `parent_of` 边，展示层临时挂虚拟 root。
- 顶层知识节点可以作为其他节点的父节点。
- 环检测 reject。
- mastery 四类 signal 映射正确。
- mastery label 阈值固定为 weak: 0-0.39、learning: 0.40-0.59、normal: 0.60-0.79、mastered: 0.80-1.00。
- display 四类状态映射正确。
- low confidence 不写主树。
- repeated client_change_id 幂等。
- RAG-only payload 不写主树。
- get tree 可直接给前端渲染。
- get features 可供 Teacher/Student Agent 消费。
- manifest storage 阻止重复节点、重复边、重复 change log。
- Student Agent 真实 LLM 集成测必须断言 tool trace，且必须看到建树工具链被 agent 自己调度。

#### 多轮 payload 集成验收

文件：`tests/test_study_graph_student_payload_flow.py`

该测试模拟 Student Agent 的多次独立请求。每一轮都使用完整 payload，不依赖上一次的内存对象，只依赖 manifest 中已经持久化的成长树。RAG/search 结果通过 payload 传入，用于辅助节点识别、摘要和父候选判断，但不能单独触发未触达节点写入。

基础 payload 形态：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "subject_title": "大数据概论",
  "question": "",
  "personal_syllabus_context": {
    "learning_goal": "掌握 HBase RowKey 设计",
    "matched_weeks": []
  },
  "rag_context": [],
  "detected_topics": [],
  "events": [],
  "source": {
    "kind": "student_agent",
    "summary": "Student Agent 基于个人大纲、RAG、提问和学习事件生成成长树候选"
  },
  "timestamp": 1760000000
}
```

轮次 1：首次暴露薄弱点。

输入：

```json
{
  "question": "RowKey 如何避免热点？",
  "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
  "rag_context": [
    {"title": "HBase RowKey 设计", "summary": "RowKey 热点通常来自单调递增键或访问集中。"}
  ],
  "events": [
    {"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": false}
  ]
}
```

期望：

- 创建 `RowKey 热点` 节点。
- 节点为 `top_level`，`parent_node_id = null`。
- mastery 为 weak 或 score 下降到 weak 区间。
- `get_student_learning_tree` 返回 `virtual_root.title = 大数据概论`。

轮次 2：同一薄弱点再次出现。

输入：

```json
{
  "question": "我还是不理解 RowKey 热点为什么会集中到一个 Region。",
  "detected_topics": [{"title": "RowKey 热点", "confidence": 0.82, "signal": "struggled"}],
  "rag_context": [
    {"title": "Region 热点", "summary": "访问集中到单个 Region 会导致吞吐瓶颈。"}
  ],
  "events": [
    {"kind": "dialogue", "content": "我还是不理解 RowKey 热点为什么会集中到一个 Region。"}
  ]
}
```

期望：

- merge 到轮次 1 的同一个节点。
- 不重复创建 `RowKey 热点`。
- change log 追加新记录。

轮次 3：出现子知识点并给出父候选。

输入：

```json
{
  "question": "预分区策略怎么缓解 RowKey 热点？",
  "detected_topics": [{"title": "预分区策略", "confidence": 0.74, "signal": "learned"}],
  "rag_context": [
    {"title": "预分区策略", "summary": "预分区通过提前划分 Region 分散写入压力。"}
  ],
  "events": [
    {"kind": "resource", "topic": "预分区策略", "status": "viewed"}
  ],
  "parent_candidates": [
    {"title": "RowKey 热点", "child_title": "预分区策略"}
  ]
}
```

期望：

- 创建 `预分区策略` 节点。
- 通过父候选挂到 `RowKey 热点`。
- 写入一条 `RowKey 热点 -> 预分区策略` 的 `parent_of` 边。

轮次 4：练习完成，掌握度上升。

输入：

```json
{
  "question": "我做完了预分区策略练习。",
  "detected_topics": [{"title": "预分区策略", "confidence": 0.8, "signal": "practiced"}],
  "rag_context": [
    {"title": "预分区策略", "summary": "预分区策略需要结合 RowKey 分布和查询模式。"}
  ],
  "events": [
    {"kind": "answer", "topic": "预分区策略", "is_correct": true},
    {"kind": "resource", "topic": "预分区策略", "status": "completed"}
  ]
}
```

期望：

- 不重复创建 `预分区策略`。
- mastery score 上升。
- `get_learning_tree_features` 中 `recently_grown` 包含 `预分区策略`。

轮次 5：重复提交同一 `client_change_id`。

期望：

- 返回幂等结果。
- 节点数、边数、change log 不重复膨胀。

轮次 6：RAG-only payload 不写树。

输入：

```json
{
  "question": "",
  "detected_topics": [],
  "rag_context": [
    {"title": "HBase Compaction", "summary": "Compaction 是 HBase 的存储文件合并机制。"}
  ],
  "events": []
}
```

期望：

- 不创建 `HBase Compaction` 节点。
- 不写 `parent_of` 边。
- 返回空 changes 或全部 skipped/rejected，且 reason 指明缺少学生触达证据。

轮次 7：最终读取。

期望：

- `get_student_learning_tree` 返回学科 root、两个知识节点、一条父子边。
- `get_learning_tree_features` 能区分 weak/mastered/recently_grown。
- manifest 重新读取后结果不变，证明没有依赖进程内状态。

#### 真实 Student Agent 集成验收

文件：`tests/test_study_graph_agent_choice.py`

该测试必须和 `tests/test_learning_profile_agent_choice.py` 同级别：使用真实 Student Agent、真实 `run_sync(...)`、真实 LLM 配置、真实 tool trace。它验证的不是单个函数，而是 Student Agent 收到学习 payload 后，会自己调用自己的工具完成建树。

最低验收点：

- `@pytest.mark.llm`
- `RUN_LLM_TESTS=1` 时才执行
- 真实 Student Agent 先走 RAG/search
- 真实 Student Agent 再走 `get_student_learning_tree_context`
- 真实 Student Agent 生成候选并调用 `submit_learning_tree_changes`
- 真实 Student Agent 最后调用 `get_learning_tree_features` 或 `get_student_learning_tree`
- tool trace 顺序可断言
- 最终树写入结果可读回，而不是只看到候选

建议的工具链顺序：

```text
load_personal_syllabus_context
RAG/search
get_student_learning_tree_context
submit_learning_tree_changes
get_learning_tree_features
```

## 最终模块边界

```text
tasks/study_graph_task.py
  Agent/API 可调用入口：
  - get_student_learning_tree_context
  - submit_learning_tree_changes
  - get_student_learning_tree
  - get_learning_tree_features

tasks/study_graph/contracts.py
  稳定 id、空树、契约字段构造。

tasks/study_graph/normalizer.py
  title、alias、query、change candidate 归一化。

tasks/study_graph/tree_builder.py
  apply_learning_tree_changes 纯业务收口。

tasks/study_graph/features.py
  从 tree 生成 learned/weak/mastered/recent/stale 摘要。

tasks/study_graph/storage.py
  manifest 读写、tree snapshot 构造、change log 幂等检查；不做业务裁决。

blueprint/study_graph_api.py
  前端读取入口，作为 API 暴露项。
```

## 实现顺序建议

1. 阶段 1：contracts。
2. 阶段 3：normalizer。
3. 阶段 4：tree_builder 纯函数和单元测试。
4. 阶段 2：manifest storage。
5. 阶段 5：task tools。
6. 阶段 6：API。
7. 阶段 7：接画像/Teacher Agent。
8. 阶段 8：更新测试报告和集成测试。

这个顺序的好处是先把最难的业务裁决写成纯函数并测稳，再接 manifest storage 和 Agent。存储迁移或 Agent 波动不会污染核心算法判断。
