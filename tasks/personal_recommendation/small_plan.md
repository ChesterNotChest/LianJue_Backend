# 推荐路径深度优化 small plan

> 临时计划文件。文件暂放在 `tasks/generative/`，但实际改造主体属于 `tasks/personal_recommendation/`。`generative` 只在总 Agent 采纳路径后，根据路径节点生成学习资源。

## 目标

当前推荐路径深度主要受教学大纲 JSON 结构影响。教学大纲适合作为课程主干，但天然可能只有章节/小节层级，导致推荐图深度浅、先修边少、候选路径短。

本计划目标是：在不破坏现有推荐入口的前提下，把推荐图从“教学大纲直接映射树”升级为“教学大纲主干 + 知识图谱/RAG 补充 + 画像状态约束”的推荐用学习图。

## 阶段 1：增强 syllabus adapter 的节点展开能力

### 影响范围

```text
tasks/personal_recommendation/syllabus_adapter.py
tasks/personal_recommendation/service.py
tests/test_personal_recommendation_syllabus_adapter.py
tests/test_personal_recommendation_task.py
```

### 数据流

```text
syllabus JSON
  -> syllabus_json_to_learning_tree
  -> expanded learning_tree
  -> run_recommendation_route
  -> graph + candidates + best_path
```

### 包内模块输入输出

`syllabus_json_to_learning_tree(syllabus_json: Any) -> dict`

输入 1：章节/小节结构

```json
{
  "chapters": [
    {
      "id": "chapter_1",
      "title": "机器学习基础",
      "sections": [
        {"id": "sec_1", "title": "监督学习", "outcomes": ["supervised_learning"]}
      ]
    }
  ]
}
```

输入 2：教学周/课次 `period` 结构

```json
{
  "title": "大数据概论",
  "day_one": "2026-03-02",
  "graph_name": "RAG",
  "period": [
    {
      "week_index": "6",
      "content": "HBase：高可靠、高性能、面向列、可伸缩的分布式数据库",
      "enhanced_content": "HBase 运行在 HDFS 之上，适合海量稀疏数据存储，并涉及 RowKey 设计、Region 划分和热点规避。",
      "importance": "medium",
      "day_one": ""
    }
  ]
}
```

输出示例：

```json
{
  "chapter_1": {
    "title": "机器学习基础",
    "prerequisites": [],
    "outcomes": ["机器学习基础"],
    "difficulty": 1,
    "learning_time_est": 1
  },
  "sec_1": {
    "title": "监督学习",
    "prerequisites": ["chapter_1"],
    "outcomes": ["supervised_learning"],
    "difficulty": 1,
    "learning_time_est": 1
  }
}
```

`period` 输出示例：

```json
{
  "hbase_distributed_database": {
    "title": "HBase 分布式数据库",
    "prerequisites": ["distributed_storage_management"],
    "outcomes": ["HBase 分布式数据库", "hbase_distributed_database", "hbase_basic"],
    "difficulty": 2,
    "learning_time_est": 1,
    "node_source": "syllabus_period",
    "week_index": "6",
    "day_one": "",
    "importance": "medium",
    "description": "HBase 运行在 HDFS 之上，适合海量稀疏数据存储，并涉及 RowKey 设计、Region 划分和热点规避。"
  }
}
```

### 关键逻辑

- 识别 `chapters -> sections -> topics/subtopics` 这类嵌套结构。
- 识别 `period` 这类教学周/课次结构，但不能把 `week_6` 作为主学习节点。
- `period` 节点身份必须优先来自内容语义：从 `content`、`enhanced_content`、冒号前主题、关键词短语中抽取 `title` 和稳定 `node_id`。
- `week_index`、`day_one`、`importance` 只作为节点元数据保留，不定义节点身份。
- 周次顺序可以生成弱先修边，但边连接的是语义节点，例如 `distributed_storage_management -> hbase_distributed_database`，不是 `week_5 -> week_6`。
- `importance` 可以映射为默认难度：`low=1`、`medium=2`、`high=3`；缺失时使用默认难度。
- `enhanced_content` 可作为 `description` 或后续 RAG/解释字段保留。
- 只有无法抽取任何语义主题时，才 fallback 到 `period_{week_index}`，并标记 `node_source="syllabus_period_fallback"`，方便后续质量检查。
- 父子节点自动生成弱先修边：`parent -> child`。
- 如果节点已有显式 `prerequisites`，优先保留显式先修边。
- 对没有 `outcomes` 的目录节点，使用标题生成最小 outcome，避免算法无法匹配目标。

### 测试用例

- 嵌套 syllabus 能展开为多层 learning_tree。
- 父子边存在。
- 显式 prerequisites 不被覆盖。
- 展开后的树能生成长度大于 1 的候选路径。
- `period` syllabus 能展开为语义主题节点，而不是 `week_x` 主节点。
- `period.week_index`、`day_one`、`importance` 被保留为元数据。
- `period` 周次顺序能生成语义节点之间的弱先修边。
- `period` 节点 outcomes 至少包含语义标题和稳定 slug，使 RowKey/HBase 这类目标可以命中。
- 无法抽取语义主题的 `period` 才使用 `period_{week_index}` fallback，并带 `node_source="syllabus_period_fallback"`。

## 阶段 2：引入推荐图构建器，分离“原始大纲”和“推荐用图”

### 影响范围

```text
tasks/personal_recommendation/graph_builder.py  # 新增
tasks/personal_recommendation/service.py
tasks/personal_recommendation/rag_overlay.py
tests/test_personal_recommendation_task.py
```

### 数据流

```text
syllabus learning_tree
  + rag_overlay
  + profile state
  -> build_recommendation_graph_tree
  -> candidate_generator.generate
```

### 包内模块输入输出

`build_recommendation_graph_tree(learning_tree: dict, rag_overlay: dict | None, profile: dict | None) -> dict`

输入：

```json
{
  "learning_tree": {"n1": {"prerequisites": [], "outcomes": ["a"]}},
  "rag_overlay": {
    "temporary_edges": [
      {"source": "n1", "target": "n2", "reason": "RAG evidence"}
    ]
  },
  "profile": {"knowledge_levels": {"a": 0.8}}
}
```

输出：

```json
{
  "n1": {
    "prerequisites": [],
    "outcomes": ["a"],
    "edge_sources": []
  },
  "n2": {
    "prerequisites": ["n1"],
    "outcomes": ["b"],
    "edge_sources": ["rag"]
  }
}
```

### 关键逻辑

- 原始 `learning_tree` 不被原地修改。
- RAG temporary edges 可以进入推荐用图，但必须标记 `edge_sources=["rag"]`。
- RAG 边默认是 soft edge，后续评分可降权或要求置信度。
- profile 不直接改图，只用于补充节点状态，例如 `known`、`weak`、`blocked`。

### 测试用例

- RAG temporary edge 能进入推荐用图。
- 原始 learning_tree 不被污染。
- 图构建器输出仍兼容 `candidate_generator.generate`。

## 阶段 3：让 candidate generator 支持边来源和深度策略

### 影响范围

```text
tasks/personal_recommendation/candidate_generator.py
tasks/personal_recommendation/graph_adapter.py
tasks/personal_recommendation/evaluator.py
tests/test_personal_recommendation_task.py
```

### 数据流

```text
recommendation_graph_tree
  -> GraphAdapter
  -> candidate_generator.generate
  -> candidates with path_depth/path_edge_sources
  -> evaluator.score
```

### 包内模块输入输出

`generate(..., depth_strategy: str = "balanced") -> list[dict]`

新增输入：

```python
depth_strategy = "shortest" | "balanced" | "deep_prerequisite"
```

输出候选项新增：

```json
{
  "path": ["n1", "n2", "n3"],
  "cost": 10,
  "skills": ["a", "b", "c"],
  "path_depth": 3,
  "path_edge_sources": ["syllabus", "rag"]
}
```

### 关键逻辑

- `shortest`：偏向最短达成目标，适合快速学习。
- `balanced`：在长度、成本、风险之间折中，作为默认。
- `deep_prerequisite`：更重视补齐前置链路，适合基础薄弱用户。
- 不建议简单把 `L_max` 拉很大；应通过策略控制路径深度，否则候选路径会变长但不一定更合理。

### 测试用例

- `depth_strategy="shortest"` 返回较短路径。
- `depth_strategy="deep_prerequisite"` 更倾向包含前置节点。
- 默认 `balanced` 保持现有测试稳定。

## 阶段 4：调整评分，显式加入路径深度和 RAG 结构置信度

### 影响范围

```text
tasks/personal_recommendation/evaluator.py
tasks/personal_recommendation/service.py
tests/test_personal_recommendation_task.py
```

### 数据流

```text
candidates
  + state
  + recommendation_graph_tree
  -> score
  -> normalized scores
  -> scalar_scores
  -> soft prune / selection
```

### 包内模块输入输出

`score(path_item: dict, state: dict, learning_tree: dict) -> dict`

建议新增评分维度：

```json
{
  "E": 0.2,
  "D": 1.0,
  "R": 0.3,
  "P": 0.5,
  "G": 0.8,
  "C": 0.7
}
```

字段含义：

```text
G = path granularity/depth quality，路径粒度与深度质量
C = graph confidence，图结构置信度，syllabus 边高于 rag soft edge
```

### 关键逻辑

- 过短路径不一定最优，尤其当用户基础薄弱。
- 过长路径也不一定最优，需要结合 `T_max`、知识掌握度和先修风险。
- RAG 边能帮助加深结构，但置信度应低于 syllabus 显式先修边。

### 测试用例

- 含合理前置链路的路径在基础薄弱 profile 下得分更高。
- 纯 RAG soft edge 不应无条件压过 syllabus 主干路径。
- 评分结果仍保持 JSON 可序列化。

## 阶段 5：总 Agent 采纳路径后，再交给 generative 生成资源

### 影响范围

```text
tasks/personal_recommendation_task.py
tasks/generative_task.py
后续总 Agent 门户文件
```

### 数据流

```text
total agent
  -> personal_recommendation_task.run_recommendation_route_from_payload
  -> best_path / selected
  -> accept learning plan
  -> generative_task.generate_resources_from_request
```

### 包内模块输入输出

`personal_recommendation_task.run_recommendation_route_from_payload(payload: dict) -> dict`

输出给总 Agent：

```json
{
  "best_path": {
    "path": ["n1", "n2"],
    "skills": ["a", "b"],
    "path_edges": []
  },
  "graph": {"nodes": [], "edges": []}
}
```

`generative_task.generate_resources_from_request(request_payload: dict) -> dict`

输入来自被采纳路径的单个节点或节点组：

```json
{
  "user_id": 8,
  "syllabus_id": 20,
  "topic": "监督学习",
  "learning_objectives": ["supervised_learning"],
  "resource_types": ["quiz", "document", "mindmap"]
}
```

### 关键逻辑

- 推荐模块只负责产生路径和候选解释。
- 总 Agent 负责决定是否采纳路径。
- generative 模块只在路径被采纳后生成资源，不参与路径结构决策。

### 测试用例

- 推荐路径输出可以被转换为资源生成 payload。
- 资源生成请求不直接依赖推荐模块包内实现。
- 总 Agent 后续只调用 task 门户，不直接 import 包内函数。

## 推荐优先级

建议先做：

```text
阶段 1：增强 syllabus adapter 的嵌套展开
阶段 2：新增 recommendation graph builder
```

这两个阶段收益最高，风险最低。它们可以直接改善“教学大纲树太浅”的问题，同时不会要求立刻改总 Agent 或资源生成链路。

阶段 3 和阶段 4 属于算法质量优化，适合在有更多真实 syllabus/RAG 样本后推进。

## 补充边界：study_graph 输入与 learning_plan 持久化

推荐路径落地后，需要把“推荐生成”和“路径执行”分开处理。

建议边界：

```text
推荐生成：study_graph 作为只读输入
推荐持久化：单独存 learning_plan
和 study_graph 关系：plan step 引用 study_graph node_id
同步时机：step 状态变化后再更新 study_graph
存储策略：逻辑复写，旧 active plan 标记 superseded，不物理覆盖
```

### 数据流

```text
study_graph_task
  -> read user study graph / progress tree
  -> personal_recommendation_task
      -> profile + syllabus learning_tree + RAG + study_graph progress state
      -> generate candidates / selected / best_path

frontend / total agent
  -> accept selected path
  -> create learning_plan
  -> create learning_plan_steps

learning_plan_step status changed
  -> update learning_plan_step
  -> call study_graph_task to update node progress
  -> call learning_profile_task to refresh or patch profile
```

### 影响范围

推荐生成阶段：

```text
tasks/personal_recommendation_task.py
tasks/personal_recommendation/service.py
tasks/personal_recommendation/perception.py
tasks/study_graph_task.py
```

后续持久化阶段：

```text
tasks/personal_recommendation/learning_plan.py  # 可选新增
repositories/learning_plan_repo.py              # 可选新增
models/learning_plan.py                         # 可选新增
tasks/personal_recommendation_task.py
tasks/study_graph_task.py
```

### 函数级收口建议

推荐生成入口可以逐步扩展：

```python
run_recommendation_route(
    user_id: int,
    syllabus_id: int | None = None,
    goals: list[str] | None = None,
    study_graph_state: dict | None = None,
    ...
) -> dict
```

`study_graph_state` 只读输入示例：

```json
{
  "current_node_id": "n2",
  "completed_node_ids": ["n1"],
  "blocked_node_ids": ["n3"],
  "skipped_node_ids": [],
  "weak_node_ids": ["n4"]
}
```

被采纳路径持久化入口建议后续新增：

```python
accept_recommendation_path(
    user_id: int,
    syllabus_id: int | None,
    recommendation_result: dict,
    candidate_index: int | None = None,
) -> dict
```

输出：

```json
{
  "success": true,
  "plan_id": "plan_xxx",
  "status": "active",
  "superseded_plan_id": "plan_old",
  "steps": [
    {
      "step_id": "step_1",
      "node_id": "n2",
      "status": "active",
      "order_index": 0
    }
  ]
}
```

更新学习计划步骤状态：

```python
update_learning_plan_step_status(
    plan_id: str,
    step_id: str,
    status: str,
) -> dict
```

内部逻辑：

- 推荐确认时只创建 `learning_plan` 和 `learning_plan_steps`，不直接修改 `study_graph`。
- 每个 step 保存 `node_id`，该 `node_id` 可引用推荐图节点或 study_graph 节点。
- 如果已有 active plan，新确认路径时把旧 plan 标记为 `superseded`，新 plan 标记为 `active`。
- step 状态变化时，再调用 `study_graph_task` 更新对应节点进度。
- `study_graph` 继续维护学习事实和进度树，不承担推荐计划存储职责。

### 测试用例

推荐生成测试：

- `study_graph_state.completed_node_ids` 中的节点不应被优先推荐为下一步。
- `study_graph_state.blocked_node_ids` 可进入约束，避免生成不可执行路径。
- 不传 `study_graph_state` 时保持当前推荐行为。

持久化测试：

- 确认某条 candidate 后创建 active learning_plan。
- 新确认一条路径时，旧 active plan 标记为 superseded，不物理删除。
- learning_plan_step 保存 `node_id`，但不复制整个 study_graph 节点。
- step completed 后才触发 study_graph 更新。
