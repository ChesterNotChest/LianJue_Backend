# 资源生成真正 Agent 化 small plan

> 临时计划文件。目标是把 `generative` 从“确定性编排 + LiteLLM 内容生成器”改造成真正意义上的工具型资源生成 Agent。外部入口仍保持 `tasks/generative_task.py` 不变。

## 背景判断

当前链路已经有门面和编排层：

```text
generative_task
  -> resource_generation_agent.run_resource_generation_agent
  -> ResourcePlanningAgent
  -> LLMResourceGenerationAgent
  -> persist_generated_resource
```

但 `ResourcePlanningAgent` 目前是确定性工具类，不是 LLM Agent；`LLMResourceGenerationAgent` 通过 `LitellmMultiModel.call_text_model` 直接生成 JSON，也不是工具调度型 Agent。因此当前实现不能充分满足“比赛要求的真正 Agent”。

改造目标不是推翻资源校验、落盘、manifest、renderer，而是把“资源生成决策和工具调用”收口到 pydantic-ai Agent。

## 阶段 1：新增真实资源生成 Agent runtime

### 0. 新增的常量定义

建议新增到 `tasks/generative/resource_agent_contracts.py`：

```python
RESOURCE_GENERATION_TOOL_ORDER = [
    "read_generation_request",
    "read_generation_plan",
    "retrieve_generation_materials",
    "write_generation_draft",
    "generate_resource_payload",
    "persist_generated_resource",
]

RESOURCE_AGENT_SCHEMA_VERSION = "generative_agent.v1"
```

### 1. 影响的文件范围

```text
tasks/generative/resource_agent_contracts.py  # 新增
tasks/generative/resource_agent_tools.py      # 新增
tasks/generative/resource_agent_runtime.py    # 新增
tasks/generative/resource_generation_agent.py
tasks/generative_task.py
tests/test_generative_resource_agent_integration.py
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
run_resource_generation_agent(payload)
  -> normalize_generation_request
  -> for each resource_type
      -> run_single_resource_generation_agent
          -> read_generation_request
          -> read_generation_plan
          -> retrieve_generation_materials
          -> write_generation_draft
          -> generate_resource_payload
          -> persist_generated_resource
  -> aggregate resources / failures / tool_trace
```

### 3. 精确到输入输出的函数级收口

`run_single_resource_generation_agent(request_payload: dict, resource_type: str, *, deps=None) -> ResourceGenerationAgentResult`

输入：

```json
{
  "user_id": 20,
  "syllabus_id": 29,
  "question": "RowKey 如何避免热点？",
  "topic": "HBase RowKey 设计",
  "resource_type": "documents",
  "graph_name": "RAG",
  "knowledge_items": ["RowKey", "热点"],
  "weak_points": ["热点判断"],
  "generation_requirements": {}
}
```

输出：

```json
{
  "success": true,
  "resource_type": "documents",
  "resource": {"resource_id": "res_xxx"},
  "tool_trace": [
    "read_generation_request",
    "read_generation_plan",
    "retrieve_generation_materials",
    "write_generation_draft",
    "generate_resource_payload",
    "persist_generated_resource"
  ],
  "error_message": "",
  "error_code": ""
}
```

重要内部逻辑：

- Agent 必须通过工具完成资源生成，不允许直接编造最终 manifest。
- `generate_resource_payload` 负责生成某一类型的结构化资源 JSON。
- `persist_generated_resource` 继续复用现有校验、落盘、manifest、pptx renderer。
- `ResourceGenerationAgentResult.resource` 必须来自 `persist_generated_resource` 的结果。

### 4. 测试用例的构建描述

- mock LLM/tool 测试：验证工具顺序完整。
- mock search 测试：验证 `retrieve_generation_materials` 进入 draft。
- 单资源 documents 测试：验证生成、校验、落盘。
- 多资源测试：验证每个 resource_type 都有独立 tool trace。
- 默认 CI 不访问真实 LLM/RAG。

## 阶段 2：把旧 LiteLLM 内容生成器降级为兼容工具

### 0. 新增的常量定义

不新增全局常量。

### 1. 影响的文件范围

```text
tasks/generative/resource_generation_agent.py
tasks/generative/resource_agent_tools.py
tests/test_generative_resource_agent_integration.py
```

### 2. 函数级收口的完整数据流

```text
generate_resource_payload tool
  -> temporary legacy adapter
      -> existing _generate_document_content / _generate_quiz_content / ...
  -> generated_content
```

### 3. 精确到输入输出的函数级收口

`tool_generate_resource_payload(state: dict) -> dict`

输入：

```json
{
  "request": {"resource_type": "quiz"},
  "planning_bundle": {"plan": {}, "draft": {}, "retrieval_context": {}}
}
```

输出：

```json
{
  "tool": "generate_resource_payload",
  "success": true,
  "resource_type": "quiz",
  "content": {"schema_version": "v1", "questions": []}
}
```

重要内部逻辑：

- 短期可以复用旧 `LLMResourceGenerationAgent.generate_resource_content`，但只能作为工具实现，不再作为模块主 Agent。
- Agent runtime 负责决定调用工具顺序和最终输出。
- 后续阶段会替换掉这个兼容工具中的 LiteLLM 调用。

### 4. 测试用例的构建描述

- 断言外部入口不直接实例化旧 `LLMResourceGenerationAgent` 作为主控。
- 断言旧生成器只在 `generate_resource_payload` tool 内部被调用。
- 断言现有资源校验和落盘测试保持通过。

## 阶段 3：替换具体资源生成为 pydantic-ai / OpenAI-compatible Agent 输出

### 0. 新增的常量定义

建议新增每类资源的 output tool 名：

```python
RESOURCE_OUTPUT_TOOL_NAMES = {
    "documents": "final_document_resource",
    "mindmap": "final_mindmap_resource",
    "quiz": "final_quiz_resource",
    "coding_practice": "final_coding_practice_resource",
    "ppt": "final_ppt_resource",
}
```

### 1. 影响的文件范围

```text
tasks/generative/resource_agent_contracts.py
tasks/generative/resource_agent_runtime.py
tasks/generative/resource_agent_tools.py
tasks/generative/resource_generation_agent.py
tests/test_generative_task.py
tests/test_generative_resource_agent_integration.py
```

### 2. 函数级收口的完整数据流

```text
generate_resource_payload tool
  -> dispatch resource_type
  -> pydantic-ai structured output
  -> local normalization
  -> validation
```

### 3. 精确到输入输出的函数级收口

`generate_document_payload(request: dict, planning_bundle: dict) -> dict`

输出必须满足现有 `validate_document_payload`。

`generate_mindmap_payload(request: dict, planning_bundle: dict) -> dict`

输出必须满足现有 `validate_mermaid_text` 和 mindmap schema。

`generate_quiz_payload(request: dict, planning_bundle: dict) -> dict`

输出必须满足 quiz schema。

`generate_coding_practice_payload(request: dict, planning_bundle: dict) -> dict`

输出必须满足 coding practice schema。

`generate_ppt_payload(request: dict, planning_bundle: dict) -> dict`

输出必须满足 ppt schema，并继续交给 renderer 产出 `.pptx`。

重要内部逻辑：

- 模型构造统一使用 `tasks.common.agent_model.build_openai_compatible_model`。
- DashScope/Qwen thinking 兼容统一由模型构造层处理。
- 各资源类型保留现有 fallback normalization，避免模型轻微漂移导致整条链路失败。

### 4. 测试用例的构建描述

- 每类资源真实 LLM opt-in 测试。
- 每类资源 mock 输出漂移测试。
- 每类资源 schema 校验失败测试。
- PPT 继续保留 renderer/pptx 导出测试。

## 阶段 4：废弃 LiteLLM 生成器入口

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tasks/generative/resource_generation_agent.py
tasks/generative_task.py
tests/test_generative_task.py
docs/resource_generation_dev_doc.md
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
generative_task
  -> resource_agent_runtime
  -> resource_agent_tools
  -> persistence / renderers
```

### 3. 精确到输入输出的函数级收口

旧 `LLMResourceGenerationAgent`：

- 先标记为兼容层。
- 所有生产入口不再默认实例化它。
- 测试只保留少量兼容测试，后续可删除。

新默认入口：

```python
run_resource_generation_agent(request_payload: dict, *, generation_agent=None, planning_agent=None) -> dict
```

内部默认调用真实 `ResourceGenerationAgent`。

### 4. 测试用例的构建描述

- 默认 generative task 测试仍全部通过。
- 真实 LLM+RAG 测试验证工具 trace 包含资源 Agent 工具链。
- `tests/TEST_REPORT.md` 更新命令和产物路径。

## 推荐优先级

建议先做：

```text
阶段 1：新增真实资源生成 Agent runtime
阶段 2：把旧 LiteLLM 生成器降级为兼容工具
```

这两步能先满足“真正 Agent 化”的结构要求，同时不立刻重写五类资源生成 prompt 和 schema normalization。

阶段 3 和阶段 4 是去 LiteLLM 的实质迁移，适合单独做一轮严格测试后再合入。
