# 后端测试说明

本文档把测试指令和用例描述分开维护。编号一一对应：`1.a` 的运行命令对应 `2.a` 的用例说明，`1.b` 对应 `2.b`，以此类推。

测试分层原则：

- 集成测试验证 LLM/Agent 是否能承担调度职责。
- `generative_task` 集成测试必须包含真实 Agent + search。
- `learning_profile_task` 集成测试必须包含真实 Agent。
- `study_graph_task` 集成测试必须包含真实 Student Agent。
- `alignment`、`profile_builder`、`storage`、`validation`、`renderers` 等包内低层模块不单独作为集成测试入口；它们通过 task 工具链被间接覆盖，细节由单元测试验证。
- `generative_task` 同时承担资源生成入口和生成结果展示包装入口；manifest 列表/详情包装放在资源生成单元测试包中验证。
- 单元测试只验证各工具自身，不调用真实 Agent，不调用真实搜索。

## 1 快速上手

在 WSL 中进入项目目录并激活环境：

```bash
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
conda activate lianjue
```

### 1.a 全量默认单元回归

```bash
python -m pytest -q
```

### 1.b 集成测试 1 - 用户画像

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py tests/test_profile_personal_syllabus_full_chain.py -m llm --capture=tee-sys -rs
```

### 1.c 集成测试 2 - 资源生成

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 RUN_LLM_TESTS=1 RUN_SEARCH_TESTS=1 SEARCH_TOOL_GRAPH_NAME=RAG python -m pytest -p no:debugging -q tests/test_generative_resource_agent_integration.py -m "llm and search" --capture=tee-sys -rs
```

### 1.d 集成测试 3 - 学习成长树

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_study_graph_agent_choice.py -m llm --capture=tee-sys -rs
```

### 1.e 单元测试包 1 - 学习成长树

```bash
python -m pytest -q tests/test_study_graph_student_payload_flow.py
```

### 1.f 单元测试包 2 - 用户画像

```bash
python -m pytest -q tests/test_learning_profile.py tests/test_learning_profile_toolchain.py tests/test_learning_profile_input_variants.py tests/test_learning_profile_api.py tests/test_profile_personal_syllabus_tools.py tests/test_profile_personal_syllabus_full_chain.py
```

### 1.g 单元测试包 3 - 资源生成

```bash
python -m pytest -q tests/test_generative_task.py tests/test_material_task_generated_resources.py tests/test_material_api_legacy.py -m "not llm and not search"
```

### 1.h 单元测试包 4 - 公共 search tool

```bash
python -m pytest -q tests/test_search_tool.py
```

### 1.i 单元测试包 5 - Search Call

```bash
python -m pytest -q tests/test_search_call.py -m "not llm"
```

### 1.j 单元测试包 6 - Syllabus

```bash
python -m pytest -q tests/test_create_syllabus_draft.py tests/test_build_syllabus.py tests/test_update_syllabus_draft.py tests/test_update_syllabus.py
```

### 1.k 单元测试包 7 - JobChecker

```bash
python -m pytest -q tests/test_job_checker_startup_graph_sync.py
```

### 1.j 单元测试包 7 - 个人推荐路径

```bash
python -m pytest -q tests/test_personal_recommendation_task.py tests/test_personal_recommendation_api.py tests/test_personal_recommendation_agent_choice.py
```

### 1.l 单元测试包 8 - Total Agent

```bash
python -m pytest -q tests/test_total_agent_task.py tests/total_agent/test_process_contract.py
```

### 1.m 单元测试包 9 - Study Graph API

```bash
python -m pytest -q tests/test_study_graph_api.py -m mysql
```

### 1.n 集成测试 3 - 个人推荐路径 Agent 产物

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_personal_recommendation_agent_choice.py -m llm
```

全量 LLM + RAG 功能验证：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py -m llm
```

每周知识点 Agent 破拆真实 LLM + RAG 验证：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1 PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py::test_period_concept_decomposer_real_llm_rag_optional -m llm
```

调试 Agent proposal / RAG evidence 时可额外打开：
```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1 PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG=1 PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG python -m pytest -q tests/test_personal_recommendation_agent_choice.py::test_period_concept_decomposer_real_llm_rag_optional -m llm
```

可选环境变量：

```text
PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME=RAG
PERSONAL_RECOMMENDATION_RAG_QUERY=<query>
PERSONAL_RECOMMENDATION_RAG_TOP_K=5
PERSONAL_RECOMMENDATION_ROUTE_K=10
PERSONAL_RECOMMENDATION_BEAM_WIDTH=8
PERSONAL_RECOMMENDATION_USE_AGENT_DECOMPOSER=1
PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG=1
PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME=RAG
PERSONAL_RECOMMENDATION_DECOMPOSER_TOP_K=5
```

### 1.o 演示学生播种

播种 3 个演示学生（低/中/高进度），全量真实 LLM + RAG + DB：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v
```

只播种中进度学生：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v -k demo_medium
```

产物：
- 画像 → `<CWD>/profiles/<sid>-<uid>.json`
- 学习计划 → `personal_recommendation/learning_plan/user_{uid}/...`
- 学习树 → `study_graph/user_{uid}/...`
- 生成资源 → `generative/user_{uid}/...`
- 摘要 → `tests/artifacts/total_agent/demo_students/summary.json`

播种后在登录页输入用户名 + 密码 `demo123` 即可进入。

每个用户以 `demo_{level}_{uuid}` 命名，多次运行不冲突。

## 2 用例描述

### 2.a 全量默认单元回归

默认回归只验证本地 task 层逻辑、数据结构、持久化路径和工具链编排。真实 Agent、真实 LLM 和真实 KnowLion 图谱检索默认跳过。

`pytest.ini` 中的测试标记：

```ini
[pytest]
testpaths = tests
markers =
    llm: requires a real configured LLM call path and is opt-in
    search: requires a real configured KnowLion graph search path and is opt-in
```

### 2.b 集成测试 1 - 用户画像

目标：验证 `learning_profile_task` 的真实 Agent 能承担调度职责。

覆盖范围：

- 真实模型驱动画像 Agent 触发工具调用。
- Agent 能读取上下文、归一化事件、计算特征、组装画像。
- 画像链路能最终返回结构化结果。
- `test_profile_personal_syllabus_full_chain.py` 还覆盖个人大纲初始化、画像保存和建议回写链路。
- `alignment`、`profile_builder`、`storage` 是画像 Agent 工具链的内部实现模块，本集成测试只检查 Agent 是否能正确调度到这些能力，不逐项断言模块内部算法细节。

测试输入 payload：

- `test_learning_profile_agent_choice.py::test_learning_profile_agent_selects_expected_tools`
  测试开始时在数据库中创建唯一 mock 用户，并复用或创建指向 `tests/fixtures/大数据概论_20260322235507.json` 的真实 `Syllabus` 行，再创建 `UserSyllabus` 绑定关系。测试结束后清理绑定关系和 mock 用户；如果测试创建了大纲行，也一并清理。测试调用入口是 `build_learning_profile(**payload)`：

```json
{
  "user_id": "<测试运行时创建的 mock 用户 ID>",
  "syllabus_id": "<测试运行时创建或复用的大数据概论 Syllabus ID>",
  "dialogue_text": [
    "我最近在学大数据概论，HBase 的 RowKey 热点总是搞不懂。",
    "我希望两周内掌握 HBase 和预分区策略，并多做一点练习。"
  ],
  "learning_goal": "掌握大数据概论中的 HBase RowKey 设计",
  "learning_records": [
    {"event_type": "study_session", "duration_minutes": 42, "started_at": 1759913600, "meta": {"topic": "HBase"}},
    {"event_type": "practice", "duration_minutes": 36, "started_at": 1759996400, "meta": {"topic": "RowKey 设计"}}
  ],
  "answer_records": [
    {"question": "RowKey 如何避免热点？", "correct": false, "answered_at": 1759998200, "time_spent_seconds": 160, "meta": {"knowledge_points": ["RowKey 热点"]}},
    {"question": "HBase 适合什么查询场景？", "correct": true, "answered_at": 1759999000, "time_spent_seconds": 100, "meta": {"knowledge_points": ["HBase"]}},
    {"question": "预分区策略如何缓解热点？", "correct": false, "answered_at": 1759999800, "time_spent_seconds": 180, "meta": {"knowledge_points": ["RowKey 热点"]}}
  ],
  "resource_usage": [
    {"resource_id": "video_hbase_rowkey", "action": "complete", "timestamp": 1759999900, "duration_seconds": 900, "meta": {"knowledge_points": ["RowKey 热点"]}}
  ]
}
```

- `test_profile_personal_syllabus_full_chain.py::test_real_learning_profile_agent_full_chain_integration`
  测试开始时在数据库中创建唯一 mock 用户，并复用或创建指向 `tests/fixtures/大数据概论_20260322235507.json` 的真实 `Syllabus` 行，再创建 `UserSyllabus` 绑定关系。测试结束后统一清理测试创建的数据。测试调用入口是 `build_learning_profile(**payload)`：

```json
{
  "user_id": "<测试运行时创建的 mock 用户 ID>",
  "syllabus_id": "<测试运行时创建或复用的大数据概论 Syllabus ID>",
  "dialogue_text": [
    "我正在学 HBase，RowKey 热点和预分区很容易卡住。",
    "我希望一周内能做出一个合理的 RowKey 设计。"
  ],
  "learning_goal": "掌握 HBase RowKey 设计",
  "answer_records": [
    {"question": "RowKey 如何避免热点？", "correct": false, "answered_at": 1760000000, "time_spent_seconds": 180, "meta": {"knowledge_points": ["RowKey 热点"]}}
  ],
  "resource_usage": [
    {"resource_id": "mindmap_rowkey", "action": "view", "timestamp": 1760000000, "meta": {"title": "RowKey 思维导图"}}
  ]
}
```

测试输出 output：

```json
{
  "profile": "<画像 Agent 生成的结构化画像>",
  "tool_trace": ["load_existing_profile_context", "load_history_context", "load_personal_syllabus_context", "normalize_events", "compute_features", "assemble_profile", "save_or_update_profile"],
  "personal_syllabus_path": "<UserSyllabus.personal_syllabus_path 回写结果>",
  "personal_profile_path": "<UserSyllabus.personal_profile_path 回写结果>",
  "initialized_personal_syllabus": "<由大数据概论 16 周大纲初始化出的个人教学大纲>"
}
```

个人教学大纲通过真实 repository 工具链读取 `Syllabus.syllabus_path` 指向的大数据概论 fixture，初始化为 16 周个人大纲并回写 `personal_syllabus_path`；画像保存回写 `personal_profile_path`。

注意：真实 Agent 工具选择存在轻微波动。如果同一命令重跑通过，通常视为外部模型行为波动，而不是确定性代码回归。

### 2.c 集成测试 2 - 资源生成

目标：验证 agent-x 资源生成链路的真实 Agent 调度能力。该链路必须包含资源生成 Agent、资源编排 Agent 和 search/RAG 检索，并最终落到生成资源持久化工具。

集成边界：

- `generative_task` 是本链路唯一模块间入口，接收总 Agent 传入的资源生成 payload。
- `tasks.generative.resource_generation_agent` 是资源生成 Agent 内部实现，负责调用编排 Agent，并通过 OpenAI-compatible/pydantic-ai 内容 Agent 生成 typed resource JSON；资源内容生成链路不再调用 LiteLLM，也不保留 LiteLLM fallback。
- `tasks.generative.resource_planning_agent` 是资源编排 Agent 内部实现，负责读取/生成 plan、检索材料、整理 draft，作为资源生成 Agent 的工具层依赖。
- `search_tool` 必须由资源编排 Agent 根据 payload 自行调用，测试不允许外部预先指定检索 query。
- `tasks.generative.resource_persistence` 负责确定性的校验、渲染、落盘和 manifest 写入。
- `generative.validation`、`generative.renderers`、`generative.storage` 是生成链路内部实现模块，本集成测试只检查最终生成、校验、渲染和落盘结果。
- `generative_task` 的 manifest 列表/详情包装不在本集成测试中重点验证；它只负责读取 manifest 并包装成前端可渲染 detail，属于单元测试包 3。

默认场景：

- 假用户：`user_id=61`
- 假大纲：`syllabus_id=71`
- 学科：`大数据概论`
- 图名：`RAG`
- 资源类型：`documents`、`mindmap`、`quiz`、`coding_practice`、`ppt`
- 主题：`HBase RowKey 热点规避`
- 学习目标：`掌握大数据概论中的 HBase RowKey 设计与热点规避`
- 个性化薄弱点：`RowKey 热点`、`预分区策略`
- 检索 query：由资源生成 Agent 根据 payload 中的学科、主题、学习目标和薄弱点自行构造。

真实 LLM/Search 主验收使用一个 payload 一次生成全部资源类型：`documents`、`mindmap`、`quiz`、`coding_practice`、`ppt`。这样可以验证总 Agent 交给 `generative_task` 的一次资源生成请求，能完整走通 planning、search、LLM 生成、校验、渲染和落盘。测试 payload：

```json
{
  "user_id": 61,
  "syllabus_id": 71,
  "subject": "大数据概论",
  "question": "我最近在学 HBase，RowKey 热点和预分区策略总是搞不懂，想要一些针对性的学习资源。",
  "topic": "HBase RowKey 热点规避",
  "graph_name": "RAG",
  "resource_types": ["documents", "mindmap", "quiz", "coding_practice", "ppt"],
  "learning_goal": "掌握大数据概论中的 HBase RowKey 设计与热点规避",
  "weak_points": ["RowKey 热点", "预分区策略"],
  "knowledge_items": ["RowKey 热点", "预分区策略"],
  "generation_requirements": {
    "slide_count_target": 8,
    "theme": "academic-rich",
    "style": "study-review"
  }
}
```

该 payload 模拟总 Agent 已经根据用户画像、教学大纲和当前学习意图完成调度决策，并把一组资源生成任务交给 `generative_task`。资源生成 Agent 不接收外部指定的检索 query；检索由资源编排 Agent 根据 question、topic、knowledge_items、weak_points 和 resource_type 自行组织 query 并调用公共 `search_tool`。

RAG token 优化边界：资源编排 Agent 负责检索和 draft；`generate_resource_payload` 在调用内容 Agent 前会把完整 `planning_bundle` 压缩为 compact generation bundle，只保留 `learning_brief`、短证据摘要、必要 plan/draft 字段和工具轨迹。该压缩在真实 runtime 和测试注入 generation agent 的链路中都必须生效，避免把长检索原文直接传给内容 Agent。

测试输出按成功和失败分开看：

```json
{
  "success_results": [
    {"resource_type": "documents", "status": "ready", "validation": {"valid": true}},
    {"resource_type": "mindmap", "status": "ready", "validation": {"valid": true}},
    {"resource_type": "quiz", "status": "ready", "validation": {"valid": true}},
    {"resource_type": "coding_practice", "status": "ready", "validation": {"valid": true}},
    {"resource_type": "ppt", "status": "ready", "validation": {"valid": true}}
  ],
  "failed_results": [
    {
      "resource_type": "<失败的资源类型>",
      "status": "<invalid 或其他状态>",
      "validation": "<校验错误详情>",
      "title": "<生成标题>"
    }
  ]
}
```

正常通过时 `failed_results` 必须为空；如果真实 LLM 生成了字段别名或不合规结构，失败清单会直接暴露对应资源类型和 validation errors。

Documents 验收项：

- 必须生成 `document.json` 和 `document.md`。
- 文档允许比 PPT 更完整、更复杂，但复杂度应体现在学习结构上，例如学习目标、问题背景、核心概念、机制原理、方法步骤、例子/案例、常见误区、自测清单和复习总结。
- section heading 必须清晰且尽量不重复，不能整篇连续使用 `知识点说明`。
- section 可选渲染 `key_points`、`examples`、`pitfalls`、`checklist`、`evidence` 等结构化块，方便前端或人工审查阅读层级。

PPT 严格验收项：

- 必须生成 `ppt.json`、`ppt.md`、`ppt.pptx`。
- `ppt.json.slides` 必须不少于 6 页；默认目标为 8 页。
- 第 1 页必须是标题页/封面页，`slide_role` 必须为 `cover`；标题页只放课件标题、主题、学习目标和阅读导向，不讲具体知识点。
- 每页必须有非空 `title`、`body`、`bullets`、`visual_hint`；`body` 是页面导语/核心判断，建议 35-80 个中文字符，最多 1-2 句。
- 每页 `bullets` 必须为 3-5 条结构化要点，每条尽量具体；`speaker_notes` 可为空，只在必要时补充易错点或注意事项，不能承载正文重点。
- PPT 面向学生自学和复习，不是课堂报告；`visual_hint` 只描述已有占位元素，不主动要求表格、复杂图表、时间线、流程箭头、复杂卡片等新增元素。复杂元素和长文本不可以共存。
- 用 `python-pptx` 回读 `.pptx`，页数必须等于 `ppt.json.slides` 数量。
- `.pptx` 文本必须命中 `HBase`、`RowKey`、`热点`、`预分区` 中至少一个关键词，前几页标题必须能在实际 PPT 文本里找到，并且正文关键词必须实际进入 PPTX 页面文本。
- 测试会把真实生成链路的 storage root 指向 `tests/artifacts/resources_generative_real_search_real_llm_workspace/`；内部继续保留真实 storage 结构，例如 `generative/user_19/<resource_type>/<resource_id>/...`。
- 测试同时写出 `resources_generative_real_search_real_llm_all_resources_result.json` 和 `resources_generative_real_search_real_llm_all_resources_ppt.md`；mindmap 在安装 `mmdc` 时会额外产出 SVG 渲染检查结果。

链路：

```text
payload[]
  -> generative_task
  -> tasks.generative.resource_generation_agent
  -> tasks.generative.resource_planning_agent
      -> read_generation_plan
      -> retrieve_generation_materials
      -> read/write_generation_draft
      -> search_tool 查询 RAG 图
  -> OpenAI-compatible Resource Content Agent 生成 typed resource JSON
  -> tasks.generative.resource_persistence
      -> validation / renderers / storage
      -> 写 manifest，ppt 额外导出 `.pptx`
```


### 2.d 集成测试 3 - 学习成长树

目标：验证真实 Student Agent 能根据学习 payload 自行调度学习成长树工具链。

覆盖范围：

- 真实模型驱动 Student Agent 选择学习成长树工具。
- Agent 先读取学习树上下文，再提交学习树变更，最后读回学习树和学习树特征。
- 多轮场景连续提交 4 个外部总 Agent payload，每轮都走真实 `run_student_agent(payload)`，最终同一棵树至少累计多个节点和一条父子边。
- `submit_learning_tree_changes` 仍由工具层负责最终裁决、合并和落盘，Agent 只提交候选。
- 学习树测试产物写入 `tests/artifacts/study_graph/integration_agent_choice/` 和 `tests/artifacts/study_graph/integration_multi_payload_tree/`，不写入真实 `study_graph/` 根目录。该目录被 `.gitignore` 忽略，跑完可直接检查最近一次 manifest。
- 本测试不验证真实 KnowLion 图谱搜索；`search_tool` 使用 monkeypatch 的稳定返回，避免把图谱可用性混入 Student Agent 调度验收。

测试输入 payload：

- `test_study_graph_agent_choice.py::test_student_agent_selects_expected_tools`
  测试开始时在数据库中创建唯一 mock 用户，并复用或创建指向 `tests/fixtures/大数据概论_20260322235507.json` 的真实 `Syllabus` 行，再创建 `UserSyllabus` 绑定关系。测试结束后清理绑定关系和 mock 用户；如果测试创建了大纲行，也一并清理。测试调用入口是 `run_student_agent(payload)`：

```json
{
  "dispatch_id": "dispatch:<user_id>:<syllabus_id>:001",
  "source_kind": "total_agent",
  "user_id": "<测试运行时创建的 mock 用户 ID>",
  "syllabus_id": "<测试运行时创建或复用的大数据概论 Syllabus ID>",
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
  "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
  "events": [{"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": false}],
  "parent_candidates": [],
  "source": {"kind": "total_agent", "summary": "total agent dispatch"},
  "timestamp": 1760000000
}
```

测试断言输出：

```json
{
  "success": true,
  "tree": "<学习成长树读取结果>",
  "features": "<学习成长树特征摘要>",
  "tool_trace_required_prefix": ["get_student_learning_tree_context", "submit_learning_tree_changes"],
  "tool_trace_required_after_submit": ["get_student_learning_tree", "get_learning_tree_features"]
}
```

- `test_study_graph_agent_choice.py::test_student_agent_accumulates_multi_payload_tree`
  该用例连续输入 4 个外部总 Agent payload，分别覆盖 `HBase RowKey 设计`、`RowKey 热点`、`预分区策略`、`散列前缀`。每轮都调用真实 `run_student_agent(payload)`，但 RAG 仍使用 monkeypatch 的稳定返回。测试最终直接读取同一棵学习树：

```json
{
  "success": true,
  "subject_title": "大数据概论",
  "title": "大数据概论学习成长树",
  "min_node_count": 3,
  "min_edge_count": 1,
  "required_topics": ["HBase RowKey 设计", "RowKey 热点"],
  "submit_call_count": ">= payload_count"
}
```

该用例是深度 Agent 集成 smoke，只验证多轮真实 Agent 调度能累计建树；完整拓扑、节点数和边数的确定性断言仍放在单元测试包中。

注意：真实 Student Agent 工具选择存在轻微波动。如果同一命令重跑通过，通常视为外部模型行为波动，而不是确定性代码回归。

### 2.e 单元测试包 1 - 学习成长树

目标：验证学习成长树 payload 到 manifest 存储、树读取和特征读取的本地闭环，不验证真实 Agent 调度。

覆盖文件：

- `test_study_graph_student_payload_flow.py`

覆盖范围：

- `build_study_graph_changes_from_student_payload()` 从学生学习 payload 生成变更候选。
- `submit_learning_tree_changes()` 接收候选并写入 `tests/artifacts/study_graph/unit_payload_flow/user_{user_id}/syllabus_{syllabus_id}/manifest.json`。
- `get_student_learning_tree()` 能读取可渲染的学习成长树。
- `get_learning_tree_features()` 能返回 Agent 可消费的 learned / weak / mastered / recent 摘要。
- `student_agent_task.get_student_learning_graph()` 能作为只读 task 入口返回完整 tree + features bundle，不调用真实 Agent。
- 单元测试使用多轮确定性 payload 生成一棵可检查的样例树：`HBase RowKey 设计 -> RowKey 热点 -> 预分区策略 / 散列前缀`。
- 样例树会保留 `subject_title=大数据概论`，树标题为 `大数据概论学习成长树`，虚拟根标题为 `大数据概论`。
- `user_id + syllabus_id` 是学习树的身份边界，`tree_id` 固定为 `study_tree:{user_id}:{syllabus_id}`。
- 单元测试使用高位 fake id：`user_id=900008`、`syllabus_id=900020`，便于和真实数据区分。

这些测试不调用真实 Agent，不调用真实 LLM，不调用真实搜索。测试开始时会清空对应 `tests/artifacts/study_graph/unit_payload_flow/` 子目录，测试结束后保留最新产物便于人工检查。

### 2.f 单元测试包 2 - 用户画像

目标：验证画像相关工具、规则和持久化逻辑，不验证真实 Agent 调度。

覆盖文件：

- `test_learning_profile.py`
- `test_learning_profile_toolchain.py`
- `test_learning_profile_input_variants.py`
- `test_learning_profile_api.py`
- `test_profile_personal_syllabus_tools.py`
- `test_profile_personal_syllabus_full_chain.py`

覆盖范围：

- 用户行为、答题记录、资源使用信号进入画像。
- 知识点掌握度、概念薄弱点、目标清晰度、情绪状态和风险信号计算。
- 画像工具链的事件归一化、特征计算、画像组装。
- 个人画像保存路径、缓存读取、个人大纲建议更新。
- API 参数解析和默认缓存读取行为。

这些测试使用 fake agent / mock repository，不调用真实 Agent，不调用真实 LLM。

### 2.g 单元测试包 3 - 资源生成

目标：验证资源生成工具本身，不验证真实 Agent 和真实搜索。

覆盖文件：

- `test_generative_task.py`
- `test_material_task_generated_resources.py`
- `test_material_api_legacy.py`

覆盖范围：

- `ensure_generative_workspace()` 创建 `generative/user_{id}`、资源目录和 manifest。
- `generate_mindmap()` 写出 `mindmap.json` 和 `mindmap.mmd`。
- `generate_structured_document()` 写出 `document.json` 和 `document.md`。
- `generate_quiz()` 写出 `quiz.json` 和 `quiz.md`。
- `generate_ppt()` 写出 `ppt.json`、`ppt.md` 和 `ppt.pptx`。
- `generate_resource()` 分发到 `documents`、`mindmap`、`quiz`、`ppt`。
- invalid Mermaid / quiz / document payload 标记为 `invalid`。
- invalid ppt payload 标记为 `invalid`。
- 同一用户连续生成四类资源时，manifest 能累计记录所有资源。
- `generative_task` 能按 `created_at` 列出最新生成资源，并按资源类型分组。
- `generative_task` 能基于 manifest 读取生成资源 detail，返回可直接渲染的 `content` 和 `render`。
- 生成资源 manifest 中的 repo-relative 路径固定按后端根目录解析，不依赖服务启动时的当前工作目录。
- 旧 draft / publish / legacy gen API 口岸返回 deprecated 语义；detail/list API 走新的 generated resource 包装链路。

这些测试使用 fake adapter，不调用真实 Agent，不调用真实图谱。

### 2.h 单元测试包 4 - 公共 search tool

目标：验证 `search_tool()` 包装和结构化返回，不验证真实图谱。

覆盖文件：

- `test_search_tool.py`

覆盖范围：

- 参数校验。
- `classify_list` 去重和清洗。
- `KnowLion.search()` 风格返回值的结构化。
- 保留 `paragraphs`、`reasoning_paths`、`path_scores`。
- 生成 Agent 友好的 `results` 和 `context_text`。
- retriever error 返回结构化失败结果。

这些测试使用 fake retriever，不连接真实 Agent，不连接真实图谱。真实 KnowLion 图谱搜索不在本模块单独 smoke；它只通过资源生成 Agent 集成测试验证。

### 2.i 单元测试包 5 - Search Call

目标：验证 `KnowLion.search_call()` 的 prompt 组装和模型调用入口。

覆盖文件：

- `test_search_call.py`

覆盖范围：

- mock 检索结果。
- 验证用户问题、reasoning paths、paragraphs 会进入 user prompt。
- 验证 `call_text_model(...)` 调用参数。

该单元包不运行 `llm` 标记测试。

### 2.j 单元测试包 6 - Syllabus

目标：验证 syllabus draft / final 的 task 层编排、JSON 持久化、字段更新和 fake 检索隔离。

覆盖文件：

- `test_create_syllabus_draft.py`
- `test_build_syllabus.py`
- `test_update_syllabus_draft.py`
- `test_update_syllabus.py`

覆盖范围：

- syllabus draft 生成草稿 JSON，并绑定 graph / repository 回调。
- final syllabus 按周内容增强、JSON 持久化和 fake KnowLion 检索隔离。
- draft JSON 整包更新。
- final syllabus JSON 整包更新。

这些测试不证明真实数据库、真实 KnowLion 或真实 LLM 可用。

### 2.k 单元测试包 7 - JobChecker

目标：验证 JobChecker 启动时的 graph 同步逻辑。

覆盖文件：

- `test_job_checker_startup_graph_sync.py`

覆盖范围：

- 从不同结构的远端响应中提取 graph 名称。
- 只初始化远端缺失的 graph。
- 远端 graph 列表读取失败时不会误初始化。

### 2.j 单元测试包 7 - 个人推荐路径

目标：验证 `personal_recommendation_task` 的推荐路径编排入口、`tasks.personal_recommendation.agent_tools` / `agent_runtime` 的非 LLM 工具边界和 `/api/personal_recommendation` 包装层，确保 agent-x 迁移后的推荐链路与其他 task 入口一致。

覆盖文件：

- `test_personal_recommendation_task.py`
- `test_personal_recommendation_api.py`
- `test_personal_recommendation_agent_choice.py` 中的非 `llm` 用例

覆盖范围：

- `run_recommendation_route()` 作为统一 task 入口，串联 profile、learning tree、候选生成、硬剪枝、软剪枝、评分和选择。
- 缺少 `user_id` 时返回结构化错误。
- `InMemoryGraphAdapter` 能支撑推荐候选生成并读取图节点。
- `/api/personal_recommendation` 只做 API 参数包装，实际推荐链路交给 `personal_recommendation_task`。
- API 可基于 syllabus JSON 构造学习树并返回 `candidates` / `selected`。
- Agent 工具边界验证 RAG/多路检索归 `tasks.personal_recommendation.agent_tools`，剪枝、评分和路径选择归 `personal_recommendation_task`。
- mock RAG 闭环验证 `rag_context -> run_recommendation_route -> graph/candidates/selected/best_path` 可形成前端可渲染的推荐图。
- 闭环测试断言 `best_path` 来自候选路径，且路径节点、路径边都存在于返回的 `graph.nodes` / `graph.edges` 中。

这些测试不调用真实 LLM，也不连接真实知识库；它们验证推荐 agent-x 已具备与其他 agent 一致的 task 入口、API 包装边界和 Agent 工具分层。

测试产物：

```text
tests/artifacts/personal_recommendation/mock_rag_route_graph_closure/route_result.json
```

该产物保留 mock RAG 输入、工具返回、推荐摘要和完整 `recommendation` 结果，可直接检查前端推荐图的数据质量。

### 2.l 单元测试包 8 - Total Agent

目标：验证正式 `tasks.total_agent_task` 的 deterministic 调度、learning plan 状态机、上下文继承和资源生成请求边界；同时保留 `tests/total_agent` 前置闭环契约作为回归基线。该单元测试包不访问真实 LLM/RAG/DB。

覆盖文件：

- `tests/test_total_agent_task.py`
- `tests/total_agent/test_process_contract.py`

默认链路：

```text
recommendation_result fixture
  -> wait_user_acceptance
  -> explicit confirmation / auto_accept=true
  -> accept learning_plan
  -> continue current step
  -> generate current step resource request
  -> record feedback
  -> activate next step
```

覆盖范围：

- 推荐成功后只返回候选和 `wait_user_acceptance`，不隐式创建 plan。
- 用户确认或 `auto_accept=true` 时才执行 `accept_learning_plan`。
- 已有 active plan 时，”继续学习”走 history-driven 当前 step，不重新随机推荐。
- 反馈完成或跳过当前 step 后激活下一个 pending step。
- `load_total_context` 读取 active plan、next task、持久化画像摘要和学习成长树摘要；读取失败只返回 warning，不伪造画像。
- `generate_current_step_resource` 先构建 `resource_strategy`，再调用资源生成入口；单元测试通过 monkeypatch 隔离真实资源生成。

测试侧前置闭环：

```text
fixed recommendation_result fixture
  -> accept learning_plan
  -> record first step completed
  -> get next task

run_recommendation_route_from_payload
  -> accept learning_plan
  -> record first step completed
  -> get next task

multi-turn deterministic router
  -> recommend / continue / completed / skip
  -> preserve active_plan_id and current step state
```

mock profile / mock study graph / mock resource result 只存在于测试侧契约和 monkeypatch 中。正式 `tasks/total_agent` 链路通过 `learning_profile_task` 读取真实持久化画像；读取失败只返回空 `profile_summary` 和 warning，不在 runtime 内伪造 profile。资源生成测试通过 monkeypatch `generate_resources_from_request` 完成，不通过 payload 注入 mock result。

测试产物：

```text
tests/artifacts/total_agent/total_agent_deterministic_result.json
tests/artifacts/total_agent/total_agent_persisted_profile_read_result.json
tests/artifacts/total_agent/total_agent_profile_strategy_result.json
tests/artifacts/total_agent/process_contract/
```

`total_agent_deterministic_result.json` 同时保留两种对照场景：无持久化画像时 `profile_source=none`，以及测试侧通过 `learning_profile_task` 注入持久化画像时 `profile_source=persisted_profile`。后者应能看到资源策略从默认 `documents` 变为 `documents + quiz`，并把 `difficulty` 标记为 `targeted`。

`total_agent_persisted_profile_read_result.json` 验证画像存储层保存后的 profile 能通过正式 `load_profile_summary -> get_persisted_learning_profile` 读取回来，属于单元级持久化边界检查，不调用真实 Profile Agent。

### 2.m 单元测试包 9 - Study Graph API

目标：验证 `/api/study_graph/detail` 端点的 `syllabus_id` 可选化行为。

覆盖文件：

- `test_study_graph_api.py`

覆盖范围：

- 缺失 `user_id` 时返回 400 + `missing_user_id`。
- 有 `user_id` 但无 `syllabus_id` 时返回 200 + 终身学习总览（`tree.type=student`、`tree.syllabi` 列表）。
- 总览接口仅读不写，不创建任何学习树或计划数据。

这些测试标记 `@pytest.mark.mysql`，在 CI 中默认跳过；设置 `RUN_DB_TESTS=1` 后随全量回归运行。

### 2.k 集成测试 3 - 个人推荐路径 Agent

目标：验证 `personal_recommendation_task.run_personal_recommendation_agent` 背后的真实 LLM 工具选择能力。该测试模拟总 Agent 传入的推荐 payload，mock RAG/多路检索结果，并使用固定 profile/tree fixture 跑真实推荐算法链路，重点验证路径推荐 Agent 会自行调度工具并完成推荐闭环。

覆盖文件：

- `test_personal_recommendation_agent_choice.py`

覆盖范围：

- 真实模型驱动路径推荐 Agent 触发工具调用。
- Agent 按预期调用：
  - `load_request_context`
  - `search_recommendation_context`
  - `run_recommendation_route`
- `test_personal_recommendation_agent_selects_expected_tools` 使用真实 LLM 和 mock RAG，验证 Agent 工具选择稳定性。
- `test_personal_recommendation_agent_real_rag_optional` 使用真实 LLM 和真实 RAG，验证真实检索上下文能进入推荐闭环。
- `test_personal_recommendation_mock_agent_accepts_learning_plan` 使用 mock 工具链，默认验证推荐路径可被 accept 并写入 `manifest.jsonl`。
- `run_recommendation_route` 是剪枝、评分和路径选择工具，测试中使用固定 profile/tree fixture 跑真实推荐算法。
- 输出包含 `graph`、`rag_overlay`、`candidates`、`selected` 和 `best_path`。

个人推荐 Agent 默认回归只运行 mock 集成链路：流程包含工具编排、推荐生成、路径 accept 和 `manifest.jsonl` 写入，但不访问真实 LLM / RAG。真实 LLM 工具选择测试仍通过 `RUN_LLM_TESTS=1` 手动开启；真实 LLM + RAG 全量功能验证仍通过 `RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1` 手动开启。

测试层面默认图名为 `RAG`，与资源生成 Agent 的真实检索集成测试保持一致；`PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME` 只用于临时覆盖。

测试产物：

```text
tests/artifacts/personal_recommendation/mock_agent_learning_plan/mock_agent_learning_plan_result.json
tests/artifacts/personal_recommendation/mock_agent_learning_plan/learning_plan/user_12345/syllabus_20/manifest.jsonl
tests/artifacts/personal_recommendation/agent_choice/agent_choice_result.json
tests/artifacts/personal_recommendation/agent_choice_real_rag/agent_choice_real_rag_result.json
```

该产物保留总 Agent 模拟 payload、工具调用顺序、每个工具返回、推荐摘要、最终 `PersonalRecommendationResult`，以及 mock accept 链路的学习计划 manifest。

### 2.o 演示学生播种

目标：生成 3 个有真实学习数据的持久化演示学生（低/中/高进度），供前端登录页选择并展示完整平台能力。

覆盖文件：

- `tests/total_agent/test_seed_demo_students.py`

覆盖范围：

- 画像：低/中/高三级不同的 `profile_input_records`，通过真实 LLM Agent 构建并持久化到 `<CWD>/profiles/`
- 学习计划（中/高）：真实推荐 Agent → deterministic fallback → snapshot → accept，落 `manifest.jsonl`
- 学习树（中/高）：`submit_learning_tree_changes` 写入批次变更（Medium 5 batches / High 9 batches）
- 生成资源（中/高）：`generate_resources_from_request` 产出 documents/mindmap
- Summary 输出：`tests/artifacts/total_agent/demo_students/summary.json`

不可 monkeypatch，所有数据落到生产路径。多次运行不冲突（`demo_{level}_{uuid}` 命名）。

播种后使用方式：

- 前端登录页输入用户名 + 密码 `demo123`
- 或调用 `GET /api/demo_students` 获取最新学生列表

## 3 生成文件说明

`tests/test_generative_task.py` 里大多数测试都会 monkeypatch：

```python
monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)
```

因此测试生成的 JSON / Markdown / Mermaid 文件会写到 pytest 的临时目录，而不是仓库里的 `generative/` 目录。这样做是为了避免测试污染真实项目数据。

对于 `ppt` 资源，测试还会在临时目录写出真实的 `ppt.pptx` 文件，并用 `python-pptx` 回读页数和标题；标题断言按 slide 文本查找，不依赖固定 shape 索引。当前 PPT 契约收敛为学生复习材料，只填充标题区、导语区、要点区等已有占位，不再要求流程卡片、表格等复杂版式。

如果需要检查测试产物，可以在测试里临时打印：

```python
print(result["json_path"])
print(tmp_path)
```

或者写一个不 monkeypatch `_get_backend_root()` 的手动脚本。正式自动化测试不建议把生成文件留在仓库目录。

## 4 JSON 清理策略

`tests/conftest.py` 会在每个测试前后对以下目录做快照：

- `schedule/syllabus_draft/*.json`
- `schedule/syllabus/*.json`

测试结束后只删除本次测试新增的 JSON 文件，不会删除已有缓存或历史文件。

## 5 Total Agent

Total Agent 的默认单元验收命令和用例说明已归入 `1.l / 2.l`。本节只保留可人工检查的探究产物和 opt-in 入口，避免和单元测试包重复。

真实 LLM 工具选择 opt-in：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_total_agent_agent_choice.py -m llm --capture=tee-sys -rs
```

真实 Profile Agent -> Total Agent 画像读取 opt-in：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_total_agent_agent_choice.py::test_total_agent_reads_real_profile_agent_output_for_resource_strategy -m llm --capture=tee-sys -rs
```

Total Agent E2E 统一主入口：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

统一入口职责并集：

- 默认 deep-state fixture E2E：深画像、学习记录树、active plan、当前资源、资源策略、即时答疑、反馈推进和 clarification。
- 真实 Profile Agent 状态夹具 opt-in。
- 大型端到端 opt-in：真实 DB、Profile Agent、Recommendation Agent/RAG、Resource Agent、study graph sync。
- 深状态 + 全真实 Agents opt-in。
- 深状态 + 真实 RAG 即时答疑 opt-in。

统一大型 opt-in：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

可拆分复现：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py::test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db -m "llm and search and mysql" --capture=tee-sys -rs
```

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py::test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph -m "llm and search and mysql" --capture=tee-sys -rs
```

```bash
RUN_LLM_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py::test_e2e_state_fixture_real_profile_agent_optional -m "llm and mysql" --capture=tee-sys -rs
```

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_real_deep_state_all_agents -m "llm and search and mysql" --capture=tee-sys -rs
```

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_real_deep_state_answer_learning_question -m "llm and search and mysql" --capture=tee-sys -rs
```

说明：`tests/total_agent/e2e_cases_*.py` 只承载场景实现，不作为用户/CI 回归入口；不保留旧 E2E 入口回退。

最近一次阶段收口通过记录：

```text
模型：config.json / MODEL_CONFIGS.text = openai/qwen3.5-27b
结果：1 passed
用户：user_id=76
课程：syllabus_id=29
continue intent：generate_current_step_resource
feedback intent：record_learning_feedback
资源策略：profile_source=persisted_profile, resource_types=[documents, quiz, mindmap], difficulty=targeted
学习计划：feedback 后 current_step_index=1，下一步 HBase RowKey 设计 active
学习记录树：12 nodes / 7 edges，2 mastered，9 weak，feedback 已同步到 HBase 基础节点
```

关键产物：

```text
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/real_deep_state_all_agents_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/student_state_fixture_result.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/profiles/29-76.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/learning_plan/learning_plan/user_76/syllabus_29/manifest.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/manifest.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/study_graph/user_76/syllabus_29/change_log.jsonl
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/documents/documents-20260604181856-f7ce0b/document.md
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/documents/documents-20260604181856-f7ce0b/document.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/quiz/quiz-20260604182424-04ee82/quiz.json
tests/artifacts/total_agent/e2e_real_deep_state/all_agents/generative_workspace/generative/user_76/mindmap/mindmap-20260604182520-1339b8/mindmap.mmd
tests/artifacts/total_agent/e2e_real_deep_state/answer_learning_question_real_rag/real_deep_state_answer_learning_question_result.json
```

人工抽查结论：

- 链路有效：真实 Profile Agent 持久化画像，Total Agent 读取 persisted profile 和 study graph weak signal 后生成 targeted 资源策略。
- 资源有效：documents / quiz / mindmap 均 validation=true，内容围绕 HBase 基础、RowKey 热点、加盐前缀、预分区和 Region 划分展开。
- 反馈有效：record_learning_feedback 后 learning plan 推进到下一步，study graph change log 写入 learning_plan 同步事件。
- 已修补：Profile Agent 的 `concept_gaps` 已增加短语化过滤，避免长课程句子进入画像薄弱点；quiz markdown renderer 已清理模型自带的 `A.` / `B.` 选项前缀，避免出现 `A. A.`。

如果希望在终端实时观察前端可复用的工具状态流，可打开 tee 输出：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

### 5.1 流式输出

Total Agent 支持 `stream=True` 模式，LLM E2E 已接入 `run_total_agent_stream()`，配合 `--capture=tee-sys` 终端实时显示 LLM 逐 token 文本 + 工具状态。CI 由默认回归覆盖 mock 管道测试。前端可通过 SSE（`/api/total_agent/agent_run?stream=true`）消费。

可选探究用例：

```bash
python -m pytest -q tests/total_agent/test_context_strategy_contract.py
```

`tests/total_agent/test_context_strategy_contract.py` 是上下文策略的前置样本，用于观察 profile / study graph / resource strategy 的契约形态；正式 Total Agent 单元验收以 `tests/test_total_agent_task.py` 为准。

测试产物：

```text
tests/artifacts/total_agent/total_agent_deterministic_result.json
tests/artifacts/total_agent/total_agent_profile_strategy_result.json
tests/artifacts/total_agent/context_strategy_contract/context_strategy_contract_result.json
tests/artifacts/total_agent/agent_choice_continue/agent_choice_continue_result.json
tests/artifacts/total_agent/real_profile_to_total_agent/real_profile_to_total_agent_result.json
tests/artifacts/total_agent/process_contract/
tests/artifacts/total_agent/e2e/
tests/artifacts/total_agent/e2e_amend/
tests/artifacts/total_agent/e2e_real_deep_state/
```

`real_profile_to_total_agent_result.json` 是窄集成产物：先用真实 Profile Agent 生成并持久化画像，再让正式 Total Agent 读取该画像并构建资源策略。该测试仍通过 monkeypatch 隔离真实资源生成，避免把资源质量问题混入画像读取验证。

`e2e_amend/` 是 Total Agent 黑盒补充验收产物目录，覆盖深学生状态夹具、profile-driven continue、study graph weak/stale continue、feedback 推进 plan + study graph、以及 no-force clarification 场景。默认 amend 场景不访问真实 LLM/RAG/DB，但状态不是浅 mock：画像由 `learning_profile` 真实工具链根据 `dialogue_text / learning_records / answer_records / resource_usage` 生成并持久化，学习记录树由 `study_graph_task.submit_learning_tree_changes` 多批次写入形成 10+ 节点、6+ 边和 weak/mastered/recent/stale 状态分布，学习计划通过推荐路径 accept 生成。artifact 同时保留原始画像输入记录、最终 persisted profile、learning plan manifest、study graph manifest/change log、当前资源和 Total Agent 决策结果，便于检查“真实格式状态 -> 总 Agent 决策”的闭环。

E2E amend 的稳定场景输入固化在 `tests/fixtures/total_agent/deep_student_state.json`。该 fixture 只保存测试语料和场景定义，包括 profile 原始输入记录、study graph change batches、推荐路径、当前资源模板和学生消息；不保存运行后生成的 persisted profile、learning plan manifest、study graph manifest/change log 或 Total Agent result。运行产物仍写入 `tests/artifacts/` 并由 `.gitignore` 豁免。

画像字段边界：真实 Profile Agent 产物保留画像层字段，例如 `resource_preference`、`concept_gaps`、`bottleneck_topics` 和 `knowledge_mastery`。Total Agent 不要求画像原生保存 `documents / quiz / mindmap`，而是在 `normalize_profile_summary` 中把 `resource_preference` 归一化成资源生成支持的 `resource_types`，再进入 `resource_strategy`。

Total Agent E2E 收口矩阵：

- `tests/total_agent/test_total_agent_e2e.py` 是统一 E2E 主入口；`tests/total_agent/e2e_cases_*.py` 只承载场景实现，不作为用户/CI 回归入口。
- `tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_answer_learning_question_learning_strategy` 回答“深画像、深学习记录树、active plan 和当前资源进入 Total Agent 后，策略型即时答疑是否能利用 active plan / next task / weak points，且不推进 plan、不生成资源”。
- `tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_real_deep_state_answer_learning_question` 回答“同一个深学生状态在真实 Total Agent + 真实 RAG 下是否能完成即时答疑闭环”。该场景断言 intent 为 `answer_learning_question`，保留 answer/evidence，不推进 active plan、不生成资源、不写 feedback。
- `tests/total_agent/test_total_agent_e2e.py::test_e2e_state_fixture_real_profile_agent_optional` 回答“真实 Profile Agent 生成的画像是否能作为 E2E 状态夹具被保存和读取”。它不替代全链路资源生成。
- `tests/total_agent/test_total_agent_e2e.py::test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db` 回答“真实 DB、真实 Profile Agent、真实推荐 Agent/RAG 是否能对自然语言目标给出可用推荐；如果真实 RAG/目标对齐没有产出路径，则应稳定落到 `ask_goal_clarification` 而不是测试崩溃”。该场景更偏真实入口可用性，成功资源闭环由 aligned graph 场景保底。
- `tests/total_agent/test_total_agent_e2e.py::test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph` 回答“在语义对齐的推荐图下，确定性推荐路径 + 真实 Profile/资源生成/DB/study graph 是否能稳定走到 resource generation 和 feedback/study graph”。该场景用于降低自然语言目标和真实 RAG overlay 波动导致的偶然失败。
- `tests/total_agent/test_total_agent_e2e.py::test_total_agent_e2e_real_deep_state_all_agents` 回答“同一个深学生状态在真实 Profile Agent、真实 Total Agent、真实资源生成 Agent、真实 DB、真实 study graph sync 下是否能完成继续学习资源生成和反馈推进闭环”。该场景已有 active plan，因此不强制重新触发推荐；真实推荐/RAG 仍由大型 E2E 覆盖。该用例会在终端输出简短状态行，例如 `profile agent: building deep profile`、`material agent: material generated`、`study graph: feedback synced to learning tree`，并把同一组 `tool_status_events` 写入 artifact，供前端工具调用状态展示参考。该用例成本高、外部波动大，适合作为最终发布前验收，不适合默认 CI。
