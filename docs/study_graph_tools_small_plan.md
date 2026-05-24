# Student Learning Growth Tree Tool Plan

## 1. 判断

这个计划不应该继续按“完整学生学习图谱”推进。当前更准确的目标是：维护一棵学生学习成长树。

学生能看到自己学过的内容正在长出来、变粗、变高、开花结果。可读性、进度感和掌握感优先级高于边属性复杂度。

因此第一版应该避开三类东西：

- 课程知识层：课程知识结构不在这里维护，可以来自个人教学大纲或课程原始数据。
- 推荐路径层：推荐是另一个模块的输出，不应该写进学生成长树作为主结构。
- 复杂学生状态图：题目、资源、误解、证据、目标等都只作为输入或详情，不进入主树。

第一版只围绕一棵树：

> 学生学了什么，树上就长出什么；没学过，就不出现在树上。

这棵树追踪的是学生已经触达的知识内容和掌握程度，不是完整课程地图，也不是推荐路线图。

学生成长树不保存总知识库的强引用。总知识库信息由 Teacher Agent 通过 RAG 实时获取；成长树只作为个体学习状态的可读上下文提供给 Teacher Agent。Teacher Agent 负责融合“总知识库结构”和“学生成长树状态”。

## 2. 核心原则

1. 树里只放学生已经学过、问过、答过、被老师确认过或被个人大纲标记为已触达的知识。
2. 未学习内容默认不存在，不显示 locked 节点，不提前铺满课程地图。
3. 节点就是学生的“知识神经节”或“成长枝条”，不要把课程、资源、题目、推荐都塞进同一棵树。
4. 只维护知识节点的掌握指标和少量展示属性。
5. Agent 不直接编辑树，只提交轻量学习信号；tool/算法层负责归一化、合并、挂载和更新掌握度。
6. 复杂证据、置信度、事件明细可以存在于后台日志或详情里，不进入主展示树。

## 3. 树模型

每个学生在一个课程范围内有一棵成长树。

根节点可以是课程或学习主题，但它只是展示容器，不代表课程知识层。

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "tree_id": "growth_tree:8:20",
  "title": "HBase 学习树",
  "nodes": [],
  "edges": [],
  "summary": {
    "learned_node_count": 0,
    "mastered_node_count": 0,
    "weak_node_count": 0,
    "tree_growth": 0.0,
    "last_updated_at": 0
  }
}
```

## 4. 节点

第一版只需要一种真实业务节点：`KnowledgeNode`。

可选保留一个展示根节点：`TreeRoot`。

| 类型 | 用途 | 是否进入主树 |
|---|---|---|
| `TreeRoot` | 展示容器，例如课程名 | 可选 |
| `KnowledgeNode` | 学生已经触达的知识/能力点 | 是 |

其他信息可以作为外部输入、后台日志或详情引用，但不作为节点进入成长树主结构。

### 4.1 KnowledgeNode 最小字段

```json
{
  "id": "knowledge:8:20:rowkey_hotspot",
  "type": "knowledge",
  "title": "RowKey 热点问题",
  "summary": "理解 RowKey 热点产生原因和常见规避方式",
  "parent_id": "knowledge:8:20:hbase_rowkey",
  "mastery": {
    "label": "weak|learning|normal|mastered",
    "score": 0.0,
    "progress": 0.0
  },
  "display": {
    "growth_stage": "seed|sprout|branch|fruit",
    "height": 0.0,
    "color_state": "weak|growing|stable|mastered"
  },
  "source": {
    "kind": "dialogue|answer_record|personal_syllabus|teacher|system",
    "summary": "学生多次询问 RowKey 热点，并在相关题目上出错"
  },
  "first_seen_at": 0,
  "last_updated_at": 0
}
```

字段取舍：

- `title`、`summary`：服务可读性。
- `parent_id`：让树能长出层级。
- `mastery`：表达掌握情况。
- `display`：服务“养成游戏式成长”的 UI。
- `source.summary`：保留最短解释，避免主树变成审计系统。

缺省语义：

- 没有节点 = 没学过或没有可靠触达记录。
- 有节点但 `mastery.label = weak` = 学过但薄弱。
- 有节点且 `mastery.label = mastered` = 已较稳定掌握。

## 5. 边

第一版只保留树边：`PARENT_OF`。

```json
{
  "source": "knowledge:8:20:hbase_rowkey",
  "target": "knowledge:8:20:rowkey_hotspot",
  "type": "parent_of"
}
```

不在第一版主树中维护：

- `PREREQUISITE_OF`
- `RECOMMENDED_NEXT`
- `REVIEW_NEXT`
- `BLOCKED_BY`
- `TEACHES`
- `ASSESSES`
- `SUPPORTED_BY`
- `DERIVED_FROM`

如果后续确实需要推荐或前置关系，可以由推荐模块临时计算，不写入这棵成长树。

## 6. 成长树变更候选

只提交 `learning_signal` 太黑盒：agent 说“学了 RowKey 热点”，但没有表达它认为这个知识应该挂在哪里、是否是已有节点的重复、为什么要更新掌握度。

第一版应让 agent 参与提交“成长树变更候选”，但不允许 agent 直接写树。tool/算法层负责最终裁决。

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "changes": [
    {
      "op": "upsert_knowledge_node",
      "client_change_id": "chg_001",
      "knowledge": {
        "title": "RowKey 热点问题",
        "summary": "RowKey 热点产生原因和规避方式",
        "aliases": ["RowKey 热点", "热点问题"]
      },
      "parent_candidate": {
        "title": "RowKey 设计",
        "existing_node_id": null,
        "reason": "对话中的问题属于 RowKey 设计下的子问题"
      },
      "mastery": {
        "signal": "struggled",
        "delta": -0.2,
        "label_hint": "weak"
      },
      "confidence": 0.72
    }
  ],
  "source": {
    "kind": "dialogue",
    "summary": "学生说 RowKey 热点很容易卡住"
  },
  "timestamp": 1760000000
}
```

允许的 `op` 第一版只保留三个：

| op | 用途 |
|---|---|
| `upsert_knowledge_node` | 新增或更新一个学生已触达的知识节点 |
| `attach_parent` | 提交父子关系候选 |
| `update_mastery` | 更新已有节点的掌握指标 |

不开放删除、任意改边、推荐边写入。

tool/算法层负责：

- 归一化知识名称。
- 判断是否创建新节点。
- 判断挂到哪个父节点。
- 合并重复知识节点。
- 更新 `mastery.score`、`mastery.progress`、`mastery.label`。
- 更新展示用 `growth_stage`、`height`、`color_state`。
- 返回每个 `client_change_id` 的处理结果，避免维护逻辑变成不可解释的灰洞。

## 7. Tool 组

第一版只暴露四个 agent 可用工具。底层写入逻辑是 `submit_learning_tree_changes` 的内部实现，不单独作为 tool 设计。

### 7.1 `get_student_learning_tree_context`

给 agent 提供必要上下文，避免它盲猜父节点。

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
  "existing_nodes": [],
  "possible_parents": [],
  "personal_syllabus_hints": []
}
```

### 7.2 `submit_learning_tree_changes`

提交成长树变更候选。

输入是一个或多个受限 `changes`。输出必须逐条解释接受、合并、拒绝或降级原因。

```json
{
  "results": [
    {
      "client_change_id": "chg_001",
      "status": "accepted|merged|rejected|needs_review",
      "created_node_id": null,
      "updated_node_id": "knowledge:8:20:rowkey_hotspot",
      "attached_parent_id": "knowledge:8:20:hbase_rowkey",
      "reason": "merged with existing node by normalized title"
    }
  ],
  "created_nodes": [],
  "updated_nodes": [],
  "created_edges": [],
  "warnings": []
}
```

`submit_learning_tree_changes` 的内部实现职责：

- upsert knowledge node。
- create/update `PARENT_OF`。
- apply mastery update。
- merge duplicate nodes。
- append change log。

### 7.3 `get_student_learning_tree`

读取学生成长树，用于前端展示。

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "include_debug": false
}
```

返回：

```json
{
  "tree": {
    "nodes": [],
    "edges": [],
    "summary": {}
  }
}
```

### 7.4 `get_learning_tree_features`

给画像 agent 或推荐模块读取摘要。

```json
{
  "learned_topics": [],
  "weak_topics": [],
  "mastered_topics": [],
  "recently_grown": [],
  "stale_topics": [],
  "tree_growth": 0.0,
  "updated_at": 0
}
```

## 8. 内部函数收口：`apply_learning_tree_changes`

`apply_learning_tree_changes` 是架构收口点，但不是 agent tool。它应该写成数据库无关的内部函数：输入标准化变更候选，读取当前树快照，产出确定性的写入计划，然后通过 repository/adapter 落库。

这样不会被数据库选型卡住。JSON 文件、关系表、图数据库都只需要实现同一组 repository 方法。

### 8.1 函数级完整数据流

```text
submit_learning_tree_changes
  -> validate_change_request
  -> load_tree_snapshot
  -> normalize_change_candidates
  -> apply_learning_tree_changes
      -> resolve_target_node
      -> resolve_parent_node
      -> compute_mastery_update
      -> compute_display_update
      -> build_write_operations
      -> persist_write_operations
      -> build_change_results
  -> recompute_tree_summary
  -> return per-change results
```

关键分工：

- `submit_learning_tree_changes`：API/tool 入口，负责鉴权、参数校验、调用内部函数、组装响应。
- `apply_learning_tree_changes`：纯业务收口，负责节点归并、父子关系裁决、掌握度更新、展示状态更新。
- `LearningTreeRepository`：存储适配层，负责读写，不承载业务判断。

### 8.2 `apply_learning_tree_changes` 输入

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "tree": {
    "tree_id": "growth_tree:8:20",
    "nodes": [],
    "edges": [],
    "summary": {}
  },
  "changes": [
    {
      "op": "upsert_knowledge_node",
      "client_change_id": "chg_001",
      "knowledge": {
        "title": "RowKey 热点问题",
        "summary": "RowKey 热点产生原因和规避方式",
        "aliases": ["RowKey 热点", "热点问题"]
      },
      "parent_candidate": {
        "title": "RowKey 设计",
        "existing_node_id": null,
        "reason": "对话中的问题属于 RowKey 设计下的子问题"
      },
      "mastery": {
        "signal": "struggled",
        "delta": -0.2,
        "label_hint": "weak"
      },
      "confidence": 0.72
    }
  ],
  "source": {
    "kind": "dialogue",
    "summary": "学生说 RowKey 热点很容易卡住",
    "event_id": "dialogue:optional"
  },
  "now_ts": 1760000000
}
```

输入约束：

- `user_id`、`syllabus_id` 必须已确定。
- `tree` 是当前学生成长树快照，可以为空树。
- `changes` 只允许 `upsert_knowledge_node`、`attach_parent`、`update_mastery`。
- `source.summary` 是最小可解释证据；`event_id` 可选。
- `confidence` 低于阈值的 change 不直接写入，可以返回 `needs_review`。

### 8.3 `apply_learning_tree_changes` 输出

```json
{
  "tree_id": "growth_tree:8:20",
  "results": [
    {
      "client_change_id": "chg_001",
      "status": "accepted|merged|rejected|needs_review",
      "op": "upsert_knowledge_node",
      "created_node_id": null,
      "updated_node_id": "knowledge:8:20:rowkey_hotspot",
      "merged_into_node_id": "knowledge:8:20:rowkey_hotspot",
      "attached_parent_id": "knowledge:8:20:hbase_rowkey",
      "mastery_before": {
        "label": "normal",
        "score": 0.55,
        "progress": 0.4
      },
      "mastery_after": {
        "label": "weak",
        "score": 0.38,
        "progress": 0.2
      },
      "reason": "merged by normalized title and updated mastery from struggled signal"
    }
  ],
  "write_operations": [
    {
      "type": "upsert_node",
      "node_id": "knowledge:8:20:rowkey_hotspot"
    },
    {
      "type": "upsert_edge",
      "source": "knowledge:8:20:hbase_rowkey",
      "target": "knowledge:8:20:rowkey_hotspot",
      "edge_type": "parent_of"
    }
  ],
  "summary_delta": {
    "created_node_count": 0,
    "updated_node_count": 1,
    "merged_node_count": 1,
    "weak_node_count_delta": 1,
    "tree_growth_delta": 0.0
  },
  "warnings": []
}
```

输出要求：

- 每个输入 change 必须有一个 result。
- result 必须说明 accepted、merged、rejected 或 needs_review。
- 对 agent 可见的响应可以隐藏 `write_operations`；测试和调试可以保留。
- 不允许静默失败。

### 8.4 重要内部函数

#### `normalize_knowledge_title(title: str) -> str`

职责：

- 去空格、统一大小写、统一中英文标点。
- 去掉“问题”“知识点”等低信息后缀时要保守。
- 返回 `normalized_title`，用于查重和生成稳定 id。

第一版不要做复杂语义聚类，避免误合并。

#### `resolve_target_node(tree, change) -> NodeResolution`

输入：

```json
{
  "knowledge.title": "RowKey 热点问题",
  "knowledge.aliases": ["RowKey 热点", "热点问题"]
}
```

输出：

```json
{
  "action": "create|update|merge|reject",
  "node_id": "knowledge:8:20:rowkey_hotspot",
  "matched_by": "id|normalized_title|alias|none",
  "confidence": 0.0,
  "reason": ""
}
```

规则：

- 如果 change 指定已有 `node_id` 且属于当前树，优先 update。
- 如果 `normalized_title` 命中已有节点，merge/update。
- 如果 alias 命中唯一节点，merge/update。
- 如果 alias 命中多个节点，返回 `needs_review`。
- 否则 create。

#### `resolve_parent_node(tree, change, target_resolution) -> ParentResolution`

职责：

- 裁决新节点或已有节点应该挂到哪里。
- 接受 agent 的 `parent_candidate`，但不盲信。

输出：

```json
{
  "action": "attach|keep_existing|move|needs_review|root",
  "parent_node_id": "knowledge:8:20:hbase_rowkey",
  "reason": ""
}
```

规则：

- 如果目标节点已有父节点，默认 `keep_existing`。
- 如果 `parent_candidate.existing_node_id` 存在且属于当前树，可以 attach。
- 如果 `parent_candidate.title` 命中唯一已有节点，可以 attach。
- 如果找不到父节点，可以挂到 `TreeRoot`，或者在置信度足够时先创建父节点。
- 如果会形成环，必须 reject 或 needs_review。
- 第一版不做复杂重排；移动已有节点需要更高置信度或人工确认。

#### `compute_mastery_update(current_mastery, mastery_change, confidence) -> MasteryUpdate`

职责：

- 把 `learned|struggled|practiced|mastered` 和 `delta` 转成稳定的掌握指标。

建议初始规则：

| signal | 默认 delta |
|---|---|
| `learned` | `+0.15` |
| `practiced` | `+0.08` |
| `struggled` | `-0.12` |
| `mastered` | `+0.25` |

实际 delta：

```text
effective_delta = clamp(input_delta or default_delta, -0.3, 0.3) * clamp(confidence, 0.2, 1.0)
score_after = clamp(score_before + effective_delta, 0.0, 1.0)
```

label 映射：

| score | label |
|---|---|
| `< 0.35` | `weak` |
| `< 0.65` | `learning` |
| `< 0.85` | `normal` |
| `>= 0.85` | `mastered` |

`label_hint` 只能作为弱信号，不能直接覆盖 score。

#### `compute_display_update(mastery_after, node_age, activity) -> DisplayUpdate`

职责：

- 把掌握指标转成前端成长视觉。

建议映射：

| mastery.label | growth_stage | color_state |
|---|---|---|
| `weak` | `seed` | `weak` |
| `learning` | `sprout` | `growing` |
| `normal` | `branch` | `stable` |
| `mastered` | `fruit` | `mastered` |

`height` 可以第一版直接等于 `mastery.score`。

#### `build_write_operations(resolutions) -> list[WriteOperation]`

职责：

- 只产出原子写操作，不直接写库。
- 便于单元测试和数据库适配。

操作类型第一版只需要：

- `upsert_tree`
- `upsert_node`
- `upsert_edge`
- `append_change_log`
- `update_tree_summary`

#### `persist_write_operations(repo, operations) -> PersistResult`

职责：

- 调用 repository/adapter 执行写入。
- 保证同一批 change 尽量事务化。
- 如果数据库不支持事务，至少保证幂等：重复提交同一个 `client_change_id` 不重复长节点。

### 8.5 Repository 接口

数据库选型只影响这一层。

```python
class LearningTreeRepository:
    def get_tree(self, user_id: int, syllabus_id: int) -> dict | None: ...
    def create_tree_if_missing(self, user_id: int, syllabus_id: int, title: str | None = None) -> dict: ...
    def list_nodes(self, tree_id: str) -> list[dict]: ...
    def upsert_node(self, tree_id: str, node: dict) -> dict: ...
    def upsert_edge(self, tree_id: str, source: str, target: str, edge_type: str) -> dict: ...
    def append_change_log(self, tree_id: str, entry: dict) -> dict: ...
    def update_summary(self, tree_id: str, summary: dict) -> dict: ...
```

第一版可以先做 JSON repository 或关系表 repository。`apply_learning_tree_changes` 不应该知道底层是 JSON、MySQL 还是图数据库。

### 8.6 最小测试用例

必须覆盖：

1. 空树上提交 `upsert_knowledge_node`，创建节点并挂到 root。
2. 已有同名节点时提交新 change，merge/update 而不是重复创建。
3. 提交 `parent_candidate`，能挂到唯一匹配父节点。
4. 父节点不存在时，按规则挂 root 或创建父节点。
5. `struggled` 降低 mastery，`mastered` 提高 mastery。
6. 低 confidence change 返回 `needs_review`，不直接写主树。
7. 同一批 change 每个 `client_change_id` 都有 result。
8. 重复提交同一个 `client_change_id` 幂等。

## 9. 与个人教学大纲的关系

个人教学大纲不是这棵树本身，而是树的一个输入来源。

大纲可以帮助：

- 给新知识节点找父节点。
- 给知识节点补 `summary`。
- 从 `competance` 和 `competance_progress` 推掌握度。
- 作为初始化已有学习内容的来源。

但不要把大纲的所有周次提前铺进树。只有学生已经触达的周次或知识，才生成节点。

## 10. Agent 边界

画像 agent 可以：

- 读取个人教学大纲。
- 读取学生成长树摘要。
- 调用 `get_student_learning_tree_context` 查询已有节点和候选父节点。
- 从问答、答题、行为记录中抽取成长树变更候选。
- 提出知识节点候选、父子关系候选和掌握度更新候选。
- 调用 `submit_learning_tree_changes`。

画像 agent 不应该：

- 直接创建树节点。
- 直接写入或自由编辑父子关系。
- 创建推荐边。
- 把完整课程知识结构灌进树。

换句话说，agent 可以说“我认为 RowKey 热点问题应该挂在 RowKey 设计下面，因为学生这次问的是热点规避”，但最终是否新建、合并、挂载、降级为待审核，由 tool/算法层决定。

推荐模块可以读取这棵树，但推荐结果不属于这棵树。推荐可以临时说“建议下一步学 X”，但 X 在学生真正触达前不应该长成树节点。

## 11. 存储建议

第一版可以用 JSON 或关系表。

推荐表结构：

- `student_learning_tree`
  - `tree_id`
  - `user_id`
  - `syllabus_id`
  - `title`
  - `summary_json`
  - `updated_at`

- `student_learning_tree_node`
  - `node_id`
  - `tree_id`
  - `parent_node_id`
  - `title`
  - `normalized_title`
  - `summary`
  - `mastery_label`
  - `mastery_score`
  - `progress`
  - `display_json`
  - `source_summary`
  - `first_seen_at`
  - `last_updated_at`

如果后续确实需要图数据库，也只把这棵成长树迁移进去，不再恢复“课程知识层 + 学生状态层 + 推荐层”的大模型。

## 12. 第一版不做

- 不维护完整课程知识图谱。
- 不提前展示未学知识。
- 不维护推荐路径边。
- 不维护资源、题目、证据、误解等复杂节点。
- 不让 agent 任意创建节点和边。
- 不把主展示树做成审计视图。

## 13. 与 llm-wiki-skill 的映射

| llm-wiki-skill | 学生成长树 |
|---|---|
| `wikilink` | 轻量父子关系 |
| `compile` | 合并和整理已出现知识节点 |
| `lint` | 检查重复节点、孤立节点、掌握度异常 |
| `audit` | 人工调整节点名称、父节点或掌握度 |
| web graph viewer | 成长树/进度树展示 |

关键借鉴点不是“建一个完整图谱”，而是“用很轻的结构持续积累”。这里的结构应该更轻：学生学到哪里，树就长到哪里。
