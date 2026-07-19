# 学生学习成长树关闭报告

本文档描述当前学生学习成长树的最终实现边界。目标是说明输入输出契约、内部核心逻辑、测试构造和持久化内容，便于后续接入总 Agent、前端接口或数据库迁移维护。

## 当前同步状态

Study Graph 当前提供两类能力：学生个人学习成长树的读写，以及课程/班级层面的只读聚合摘要。Total Agent 在上下文加载阶段读取 `get_learning_tree_features`，用于识别 weak / mastered / stale / recent 节点；在学习反馈阶段通过 learning plan step 状态变更显式同步 study graph，不在推荐阶段直接写树。

课程全局视角通过 `get_course_learning_tree_summary(payload)` 暴露，供 Total Agent 在需要时读取班级或课程级 weak signal。该摘要只用于策略仲裁，例如“个人弱点 + 班级共性弱点”时提高 targeted/review 优先级；它不反向修改个人画像、学习计划或推荐图。

当前边界：

- 推荐模块只读 `study_graph_state`，不写入 study graph。
- Total Agent 的 `record_learning_feedback` 可触发 study graph sync；sync 失败不回滚 learning plan 持久化状态，但必须进入 warning / status event。
- 课程聚合摘要应保持隐私边界，只输出聚合统计、弱节点摘要和最小可用诊断，不输出其他学生明细。
- `tool_status_events` 由 Total Agent 包装读取和同步阶段，前端可把它作为状态展示样本。

成长树模型边界：

- 每个 `user_id + syllabus_id` 维护一棵个人学习成长树。
- 主树只放学生已经触达、学习、提问、练习、答错、掌握或被个人大纲确认过的知识节点。
- 未学习内容默认不出现在树里；不提前铺满完整课程地图，也不展示 locked 节点。
- 当前真实业务节点是 knowledge node；virtual root 只作为展示容器。
- 当前只维护 `parent_of` 树边；推荐边、资源边、题目边、审计边不进入主树。
- Student Agent 只能提交变更候选；归一化、去重、父节点裁决、低置信度拦截、掌握度更新和展示状态更新由 tool/service 层完成。
- 复杂证据、置信度和事件明细只进入 change log 或节点轻量 source，不把主树变成审计系统。
- 推荐结果不属于成长树。推荐可以建议“下一步学 X”，但 X 在学生真实触达前不生成树节点。

Total Agent 中包含 study graph 的统一 E2E 回归入口是：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

## 0. 新增的常量定义

当前常量主要位于 `tasks/study_graph/contracts.py`：

- `STUDY_GRAPH_MANIFEST_VERSION = 1`
- `STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD = 0.45`
- `STUDY_GRAPH_DEFAULT_ROOT_ID_PREFIX = "study_tree_root"`
- `STUDY_GRAPH_TREE_ID_PREFIX = "study_tree"`
- `STUDY_GRAPH_NODE_ID_PREFIX = "knowledge"`
- `STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX = "学习成长树"`
- `STUDY_GRAPH_TITLE_STOP_SUFFIXES = ["问题", "知识点", "概念", "内容"]`
- `STUDY_GRAPH_MAX_CONTEXT_CANDIDATES = 8`
- `STUDY_GRAPH_SIGNAL_DEFAULT_DELTA`
  - `learned: 0.15`
  - `practiced: 0.08`
  - `struggled: -0.12`
  - `mastered: 0.25`
- `STUDY_GRAPH_DELTA_MIN = -0.3`
- `STUDY_GRAPH_DELTA_MAX = 0.3`

稳定枚举值：

```text
node_type:
  tree_root
  knowledge

edge_type:
  parent_of

change_status:
  accepted
  merged
  rejected
  needs_review
  skipped

mastery_label:
  weak
  learning
  normal
  mastered

signal:
  learned
  practiced
  struggled
  mastered

display:
  growth_stage = seed | sprout | branch | fruit
  color_state = weak | growing | stable | mastered
```

## 状态机

Study Graph 有三套需要分清的状态：

| 状态对象 | 字段 | 取值 | 写入方 | 读取方 |
|---|---|---|---|---|
| 变更候选结果 | `results[].status` / change log `status` | `accepted`、`merged`、`rejected`、`needs_review`、`skipped` | `apply_learning_tree_changes` | 测试、调试、审计、Total Agent warning |
| 节点掌握度 | `node.mastery.label` | `weak`、`learning`、`normal`、`mastered` | `compute_mastery_update` | features、课程聚合、Total Agent、学伴 |
| 节点展示状态 | `node.display.growth_stage` / `color_state` | `seed/sprout/branch/fruit`、`weak/growing/stable/mastered` | `compute_display_update` | 前端图展示 |

变更候选状态机：

```text
incoming change
  -> skipped      # client_change_id 已处理过，幂等跳过，只写 change log
  -> needs_review # 低置信度或命中歧义，需要人工/后续策略处理，只写 change log
  -> rejected     # unsupported op、未实现 op、明确无效目标，只写 change log
  -> accepted     # 新建知识节点，写 node/edge/change log
  -> merged       # 命中已有节点并合并，写 node/edge/change log
```

掌握度状态机：

```text
current mastery score
  + signal delta * confidence
  -> clamp 0.0..1.0
  -> score_to_mastery_label
```

展示状态映射固定为：

```text
weak     -> growth_stage=seed,   color_state=weak
learning -> growth_stage=sprout, color_state=growing
normal   -> growth_stage=branch, color_state=stable
mastered -> growth_stage=fruit,  color_state=mastered
```

边界：

- `needs_review`、`rejected`、`skipped` 不写入节点或边，只写 change log。
- `accepted` 表示新节点创建；`merged` 表示归一化 title/alias 命中已有节点并更新。
- `update_mastery` 和 `attach_parent` 当前仍是 rejected，不是未完成的半写状态。
- Learning Plan 的 step 状态只在调用方允许时转成 Study Graph change；Study Graph 不反向修改 Learning Plan。

路径常量位于 `constant.py`：

- `BasePath.STUDY_GRAPH_ROOT = "/study_graph"`

当前已新增 Study Graph 生产数据库表；`study_graph/` manifest 仍作为测试、离线和显式文件后端使用，版本库只保留 `.gitkeep`，具体用户树数据被 `.gitignore` 忽略。

## 1. 影响的文件范围

核心实现：

- `tasks/study_graph_task.py`
  - 学习进度图谱唯一跨模块 task 门户。
  - 暴露真实 Student Agent 编排入口：`run_student_agent(payload)`。
  - 暴露只读完整学习树入口：`get_student_learning_graph(user_id, syllabus_id, include_debug=False)`。
  - 暴露学习树工具层入口。
  - payload 到 changes 的规则转换。
  - 提交变更、读取树、读取摘要特征。
- `tasks/study_graph/student_agent.py`
  - Student Agent 包内实现。
- `tasks/study_graph/service.py`
  - 确定性学习树服务层。
- `tasks/study_graph/contracts.py`
  - ID、根节点、空树、掌握度标签、client change id 等契约函数。
- `tasks/study_graph/storage.py`
  - 数据库 / manifest 双后端存储。
  - `user_id + syllabus_id` 隔离。
- `tasks/study_graph/tree_builder.py`
  - 变更候选标准化。
  - 节点归并、父节点裁决、掌握度更新、展示状态计算。
- `tasks/study_graph/normalizer.py`
  - 知识点标题归一化。
  - 上下文候选排序。
  - payload evidence key 生成。
- `tasks/study_graph/features.py`
  - 树摘要重算。
  - Agent 可消费 features 生成。
- `tasks/common/agent_model.py`
  - 统一构造 OpenAI-compatible pydantic-ai 模型。
  - 处理 DashScope Qwen/QwQ/DeepSeek thinking 与 tool calling 的兼容参数。

测试与文档：

- `tests/test_study_graph_student_payload_flow.py`
- `tests/test_study_graph_agent_choice.py`
- `tests/TEST_REPORT.md`
- `docs/study_graph_dev_doc.md`
- `.gitignore`
- `study_graph/.gitkeep`

## 2. 函数级收口的完整数据流

### 2.1 写路径：总 Agent payload -> Student Agent -> 学习树落盘

模块输入契约：

```json
{
  "dispatch_id": "dispatch:<user_id>:<syllabus_id>:001",
  "source_kind": "total_agent",
  "user_id": 20,
  "syllabus_id": 29,
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
  "parent_candidates": [
    {"title": "HBase RowKey 设计", "child_title": "RowKey 热点"}
  ],
  "source": {"kind": "total_agent", "summary": "total agent dispatch"},
  "timestamp": 1760000000
}
```

完整数据流：

```text
run_student_agent(payload)
  -> pydantic-ai Student Agent
    -> rag_search
    -> get_tree_context
       -> study_graph_task.get_student_learning_tree_context
    -> derive_payload
    -> build_changes
       -> study_graph_task.build_study_graph_changes_from_student_payload
    -> submit_changes
       -> study_graph_task.submit_learning_tree_changes
          -> validate_change_request
          -> create_tree_if_missing / load tree storage
          -> normalize_change_candidates
          -> apply_learning_tree_changes
          -> upsert_node / upsert_edge / append_change_log
          -> recompute_tree_summary / update_summary
    -> read_tree
       -> study_graph_task.get_student_learning_tree
    -> read_features
       -> study_graph_task.get_learning_tree_features
  -> StudentAgentResult
```

模块输出契约：

```json
{
  "success": true,
  "tree_id": "study_tree:20:29",
  "tree": {
    "schema_version": 1,
    "tree_id": "study_tree:20:29",
    "user_id": 20,
    "syllabus_id": 29,
    "subject_title": "大数据概论",
    "title": "大数据概论学习成长树",
    "virtual_root": {"type": "tree_root", "title": "大数据概论"},
    "nodes": [],
    "edges": [],
    "summary": {}
  },
  "features": {
    "tree_id": "study_tree:20:29",
    "learned_topics": [],
    "weak_topics": [],
    "mastered_topics": [],
    "recently_grown": [],
    "stale_topics": [],
    "tree_growth": 0.0,
    "updated_at": 0
  },
  "changes": [],
  "tool_trace": []
}
```

### 2.2 只读路径：读取完整学习树

模块输入契约：

```python
get_student_learning_graph(user_id: int, syllabus_id: int, include_debug: bool = False)
```

完整数据流：

```text
study_graph_task.get_student_learning_graph
  -> study_graph_task.get_student_learning_tree
  -> study_graph_task.get_learning_tree_features
  -> 返回完整 tree + features bundle
```

模块输出契约：

```json
{
  "success": true,
  "user_id": 20,
  "syllabus_id": 29,
  "tree_id": "study_tree:20:29",
  "tree": "<完整 manifest tree>",
  "features": "<摘要特征，不含 success 字段>",
  "debug": {},
  "error_message": "",
  "error_code": ""
}
```

该入口不调用 LLM，不调用 RAG，只读当前持久化学习树。

入口边界：

- `tasks/study_graph_task.py` 是学习进度图谱和 Student Agent 的唯一跨模块 task 门户。
- `tasks/study_graph/` 只放包内实现，外部 API 或其他 Agent 不应直接依赖包内函数。
- 原 `tasks/student_agent_task.py` 已并入 `tasks/study_graph/student_agent.py`，不再保留外层文件。

## 3. 精确到输入输出的函数级收口

### 3.1 `run_student_agent(payload: dict) -> StudentAgentResult`

输入：

- 外部总 Agent 派发给 Student Agent 的学习事件 payload。
- 必填语义字段：`user_id`、`syllabus_id`。
- 推荐携带字段：`subject_title`、`question`、`learning_goal`、`detected_topics`、`events`、`parent_candidates`。

输出：

- `StudentAgentResult`
  - `success`
  - `tree_id`
  - `tree`
  - `features`
  - `changes`
  - `tool_trace`
  - `error_message`
  - `error_code`

输出兼容：

- 真实模型如果把 `tree`、`features`、`changes` 作为 JSON 字符串返回，`StudentAgentResult` 会解析为 dict/list。
- 该容错只处理结构化输出漂移，不改变学习树落盘逻辑。

内部逻辑：

- 构造 `StudentAgentDeps(payload, state)`。
- 真实 Agent 按工具调用完成 RAG、上下文读取、变更候选构造、提交和读回。
- 函数结束时从 `deps.state` 回填 `tree_id/tree/features/changes/tool_trace`。
- 学习路径推荐可以只读 `study_graph` 状态，但推荐 plan 不写入 `study_graph`；只有学习计划 step 状态变化后，才由调用方显式同步进度。

### 3.2 `get_student_learning_graph(user_id, syllabus_id, include_debug=False) -> dict`

输入：

- `user_id`
- `syllabus_id`
- `include_debug`

输出：

- 完整 tree + features bundle。

内部逻辑：

- 调用 `get_student_learning_tree` 读取完整树。
- 调用 `get_learning_tree_features` 读取摘要特征。
- 合并为只读 task 返回，不触发 Agent。

### 3.3 `build_study_graph_changes_from_student_payload(payload: dict) -> list[dict]`

输入：

- Student Agent 或测试工具层传入的学习 payload。

输出：

```json
[
  {
    "op": "upsert_knowledge_node",
    "client_change_id": "total_agent:20:29:upsert_knowledge_node:rowkey_xxx",
    "knowledge": {
      "title": "RowKey 热点",
      "summary": "Student Agent 识别为已触达且薄弱的知识点",
      "aliases": ["RowKey 热点"],
      "node_id": null
    },
    "parent_candidate": {"title": "HBase RowKey 设计", "child_title": "RowKey 热点"},
    "mastery": {"signal": "struggled", "label_hint": "weak"},
    "confidence": 0.78
  }
]
```

内部逻辑：

- 候选标题优先级：
  - `detected_topics.title`
  - `events.topic`
  - `events.meta.knowledge_points`
  - 个人大纲和 RAG 的上下文标题
  - 没有明确知识点时才用 `question/content` 兜底
- `detected_topics` 命中时，confidence 作为主证据，不再被低权重稀释。
- 只有证据分达到阈值才生成 `upsert_knowledge_node`。
- RAG-only 候选不会单独创建节点。
- `parent_candidates` 只作为候选关系，最终是否挂载由工具层裁决。

### 3.4 `submit_learning_tree_changes(...) -> dict`

输入：

```python
submit_learning_tree_changes(
    user_id: int,
    syllabus_id: int,
    changes: list[dict],
    source: dict | None = None,
    timestamp: int | None = None,
    subject_title: str | None = None,
)
```

输出：

```json
{
  "success": true,
  "tree_id": "study_tree:20:29",
  "results": [],
  "created_nodes": [],
  "updated_nodes": [],
  "created_edges": [],
  "summary": {},
  "warnings": []
}
```

内部逻辑：

- 校验 `user_id/syllabus_id/changes`。
- 初始化或读取数据库中的 `study_graph_tree`；显式文件后端下读取 `study_graph/user_{user_id}/syllabus_{syllabus_id}/manifest.json`。
- `subject_title` 用于生成：
  - `subject_title = 大数据概论`
  - `title = 大数据概论学习成长树`
  - `virtual_root.title = 大数据概论`
- 标准化 changes。
- 调用 `apply_learning_tree_changes` 做纯业务裁决。
- 对 accepted/merged 结果落盘节点和边。
- 追加 `change_log.jsonl`。
- 重算 summary。

### 3.5 `apply_learning_tree_changes(input_payload: dict) -> dict`

输入：

- 当前树快照。
- 标准化 changes。
- source。
- now timestamp。

输出：

- `results`
- `write_operations`
- `summary_delta`
- `warnings`

内部逻辑：

- 根据 `normalized_title` 或 alias 判断 create / merge / needs_review。
- 根据 `parent_candidate` 解析父节点。
- 根据 signal 和 confidence 计算 mastery 分数。
- 根据 mastery 分数生成展示状态：
  - `seed/weak`
  - `sprout/growing`
  - `branch/stable`
  - `fruit/mastered`
- 不直接写文件，只返回裁决结果。

### 3.6 `get_student_learning_tree(user_id, syllabus_id, include_debug=False) -> dict`

输入：

- `user_id`
- `syllabus_id`
- `include_debug`

输出：

```json
{
  "success": true,
  "tree": "<完整 manifest tree>",
  "debug": {}
}
```

内部逻辑：

- 如果树不存在，创建空树。
- 生产默认读取数据库 tree；显式文件后端读取完整 manifest。
- 回填 `virtual_root`。

### 3.7 `get_learning_tree_features(user_id, syllabus_id, stale_days=14) -> dict`

输入：

- `user_id`
- `syllabus_id`
- `stale_days`

输出：

```json
{
  "success": true,
  "tree_id": "study_tree:20:29",
  "learned_topics": [],
  "weak_topics": [],
  "mastered_topics": [],
  "recently_grown": [],
  "stale_topics": [],
  "tree_growth": 0.0,
  "updated_at": 0
}
```

内部逻辑：

- 读取数据库 tree 或显式文件后端 manifest。
- 遍历 nodes。
- 根据 mastery label 和更新时间生成 Agent 摘要。

## 4. 测试用例的构建描述

### 4.1 单元测试：`tests/test_study_graph_student_payload_flow.py`

运行命令：

```bash
python -m pytest -q tests/test_study_graph_student_payload_flow.py
```

测试边界：

- 不调用真实 Agent。
- 不调用真实 LLM。
- 不调用真实 RAG。
- 使用工具层构造确定性多轮样例树。

测试 artifact：

```text
tests/artifacts/study_graph/unit_payload_flow/user_900008/syllabus_900020/
```

样例树：

```text
大数据概论
└── HBase RowKey 设计
    └── RowKey 热点
        ├── 预分区策略
        └── 散列前缀
```

核心断言：

- `subject_title = 大数据概论`
- `title = 大数据概论学习成长树`
- `virtual_root.title = 大数据概论`
- 节点数为 4。
- 边数为 3。
- `RowKey 热点` 挂到 `HBase RowKey 设计`。
- `预分区策略` 和 `散列前缀` 挂到 `RowKey 热点`。
- `get_student_learning_graph()` 能返回完整 tree + features bundle。

### 4.2 集成测试：`tests/test_study_graph_agent_choice.py`

运行命令：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_study_graph_agent_choice.py -m llm
```

测试边界：

- 调用真实 Student Agent。
- 需要真实 LLM 配置。
- 创建真实 mock `User / Syllabus / UserSyllabus` 数据库关系。
- RAG 使用 monkeypatch 稳定返回，不验证真实 KnowLion 图谱。

测试 artifact：

```text
tests/artifacts/study_graph/integration_agent_choice/
tests/artifacts/study_graph/integration_multi_payload_tree/
```

用例 1：`test_student_agent_selects_expected_tools`

- 验证真实 Student Agent 调用学习树工具链。
- 要求先调用：
  - `get_student_learning_tree_context`
  - `submit_learning_tree_changes`
- 提交后要求读回：
  - `get_student_learning_tree`
  - `get_learning_tree_features`

用例 2：`test_student_agent_accumulates_multi_payload_tree`

- 连续输入 4 个外部总 Agent payload。
- 每轮都调用真实 `run_student_agent(payload)`。
- 最终同一棵树至少累计多个节点和一条父子边。
- 宽松断言多轮 Agent 建树能力，精确拓扑交给单元测试。

## 5. 新增的持久化内容

### 5.1 生产数据库表

Study Graph 生产默认使用数据库后端，表定义位于 `schemas/agent_runtime_state.py`：

```text
study_graph_tree
study_graph_node
study_graph_edge
study_graph_change_log
```

核心约束：

- `study_graph_tree`：`UNIQUE(user_id, syllabus_id)`
- `study_graph_node`：`UNIQUE(tree_id, normalized_title)`
- `study_graph_edge`：`UNIQUE(tree_id, source_node_id, target_node_id, edge_type)`
- `study_graph_change_log`：`UNIQUE(tree_id, client_change_id)`

实现细节：

- `tasks/study_graph/storage.py` 生产读写必须依赖数据库 app context；没有数据库 app context 时不会静默写入 repo 下的 `study_graph/`。
- `study_graph_tree.manifest_json` 保留完整 tree 快照，便于兼容原 manifest 读取语义。
- `study_graph_node` 和 `study_graph_edge` 保存可查询的节点/边当前态。
- `study_graph_change_log` 保存幂等变更事件，`client_change_id` 用于去重。

### 5.2 显式文件后端 manifest

测试、离线 artifact 必须显式设置 `STUDY_GRAPH_FILE_BACKEND=1` 才使用文件后端：

```text
study_graph/user_{user_id}/syllabus_{syllabus_id}/manifest.json
study_graph/user_{user_id}/syllabus_{syllabus_id}/change_log.jsonl
```

manifest 核心结构：

```json
{
  "schema_version": 1,
  "tree_id": "study_tree:{user_id}:{syllabus_id}",
  "user_id": 20,
  "syllabus_id": 29,
  "subject_title": "大数据概论",
  "title": "大数据概论学习成长树",
  "virtual_root": {},
  "nodes": [],
  "edges": [],
  "summary": {},
  "created_at": 1760000000,
  "updated_at": 1760000000
}
```

`.gitignore` 中忽略真实运行数据：

```gitignore
study_graph/*
!study_graph/.gitkeep
tests/artifacts/
```

版本库只保留：

```text
study_graph/.gitkeep
```

## 6. 文档事实源

`docs/study_graph_dev_doc.md` 是学习成长树模块唯一事实源。旧 `study_graph_tools_small_plan.md` 和 `study_graph_tools_contract.md` 的有效内容已经按真实代码实现融合进本文：

- 每个学生每个大纲一棵个人成长树。
- 只维护已触达知识节点和 `parent_of` 树边。
- Student Agent 只提交变更候选，tool/service 层负责裁决和落盘。
- 生产数据库表、显式文件后端 `manifest.json` / `change_log.jsonl`、只读 features 接口。
- Total Agent 只消费个人 features 和课程聚合摘要，不在推荐阶段写树。

旧阶段文档可删除；如果后续发现旧文档仍有有效事实，应先融合进本文或测试，再删除旧文档。
