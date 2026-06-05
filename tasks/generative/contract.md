# 资源生成真正 Agent 化收口计划

本文档用于收口 `generative` 模块从“确定性编排 + LiteLLM 内容生成器”迁移到“真正工具型资源生成 Agent”的实现计划。

外部模块、API、总 Agent 后续仍只应调用 `tasks/generative_task.py`。包内可以重排，但跨模块门户不变。

## 总体判断

当前资源生成链路已经具备门面、规划、检索、校验、落盘和 manifest 能力：

```text
generative_task
  -> tasks.generative.resource_generation_agent
  -> ResourcePlanningAgent
  -> LLMResourceGenerationAgent
  -> persist_generated_resource
```

但这条链路还不是严格意义上的工具型 Agent：

- `ResourcePlanningAgent` 是确定性编排类，不是 LLM tool-calling Agent。
- `LLMResourceGenerationAgent` 通过 `LitellmMultiModel.call_text_model` 直接生成资源 JSON，不是 pydantic-ai Agent。
- 当前 tool trace 主要来自确定性函数调用，不足以证明“资源生成 Agent 自己选择/调用工具”。

目标是将资源生成主流程收口为真实 Agent：

```text
ResourceGenerationAgent
  -> read_generation_request
  -> read_generation_plan
  -> retrieve_generation_materials
  -> write_generation_draft
  -> generate_resource_payload
  -> persist_generated_resource
```

短期允许旧 `LLMResourceGenerationAgent` 作为兼容工具实现存在，但它不能再作为默认主控 Agent。长期应替换掉 LiteLLM 内容生成器。

## 阶段 1：新增真实资源生成 Agent runtime

### 0. 新增的常量定义

新增文件：

```text
tasks/generative/resource_agent_contracts.py
```

建议常量：

```python
RESOURCE_AGENT_SCHEMA_VERSION = "generative_agent.v1"

RESOURCE_GENERATION_TOOL_ORDER = [
    "read_generation_request",
    "read_generation_plan",
    "retrieve_generation_materials",
    "write_generation_draft",
    "generate_resource_payload",
    "persist_generated_resource",
]

RESOURCE_AGENT_ERROR_MISSING_REQUEST = "missing_request"
RESOURCE_AGENT_ERROR_TOOLCHAIN_INCOMPLETE = "toolchain_incomplete"
RESOURCE_AGENT_ERROR_GENERATION_FAILED = "generation_failed"
RESOURCE_AGENT_ERROR_PERSIST_FAILED = "persist_failed"
```

新增 Pydantic/dataclass 契约：

```python
class ResourceGenerationDeps:
    state: dict

class ResourceGenerationAgentResult(BaseModel):
    success: bool = True
    resource_type: str = ""
    resource: dict | None = None
    generated_content: dict | None = None
    planning_bundle: dict | None = None
    tool_trace: list[str] = []
    error_message: str = ""
    error_code: str = ""
```

### 1. 影响的文件范围

核心新增：

```text
tasks/generative/resource_agent_contracts.py
tasks/generative/resource_agent_tools.py
tasks/generative/resource_agent_runtime.py
```

接入修改：

```text
tasks/generative/resource_generation_agent.py
tasks/generative_task.py
tasks/generative/__init__.py
```

测试：

```text
tests/test_generative_resource_agent_integration.py
tests/test_generative_task.py
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

单资源：

```text
run_single_resource_generation_agent(request_payload, resource_type)
  -> build ResourceGenerationDeps.state
  -> pydantic-ai ResourceGenerationAgent
      -> read_generation_request
      -> read_generation_plan
      -> retrieve_generation_materials
      -> write_generation_draft
      -> generate_resource_payload
      -> persist_generated_resource
  -> ResourceGenerationAgentResult
```

多资源：

```text
run_resource_generation_agent(payload)
  -> normalize_generation_request
  -> for each resource_type
      -> run_single_resource_generation_agent
      -> collect resource / failure / tool_trace
  -> aggregate response
```

### 3. 精确到输入输出的函数级收口

#### `build_resource_generation_agent() -> Agent`

职责：

- 构造 pydantic-ai Agent。
- 使用 `tasks.common.agent_model.build_openai_compatible_model(...)` 构造模型。
- 注册资源生成所需工具。
- output type 使用 `ResourceGenerationAgentResult`。

内部逻辑：

- system prompt 明确要求工具顺序。
- Agent 不允许直接编造落盘结果。
- 最终 `resource` 必须来自 `persist_generated_resource` 工具返回。

#### `run_single_resource_generation_agent(request_payload: dict, resource_type: str, *, generation_tool=None, planning_agent=None) -> ResourceGenerationAgentResult`

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
  "resource": {
    "resource_id": "res_xxx",
    "resource_type": "documents",
    "main_files": {}
  },
  "generated_content": {},
  "planning_bundle": {},
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

内部逻辑：

- 初始化 state：

```python
{
    "request": request_payload,
    "resource_type": resource_type,
    "planning_agent": planning_agent,
    "generation_tool": generation_tool,
    "planning_bundle": None,
    "generated_content": None,
    "persisted_resource": None,
    "tool_trace": [],
}
```

- 调用 Agent。
- Agent 返回后，用 state 中的真实工具结果覆盖模型输出中的 `resource`、`generated_content`、`planning_bundle`、`tool_trace`。
- 如果 `persisted_resource` 不存在，返回 structured error。

#### `run_resource_generation_agent(request_payload: dict, *, generation_agent=None, planning_agent=None) -> dict`

职责：

- 保持当前 `generative_task.py` 对外返回结构基本不变。
- 默认调用新的 `run_single_resource_generation_agent`。
- `generation_agent` 参数短期保留兼容测试注入；当传入旧 fake agent 时仍走兼容路径。

输出：

```json
{
  "success": true,
  "request": {},
  "resources": [],
  "resource_count": 3,
  "success_count": 3,
  "failed_count": 0,
  "tool_trace": [],
  "error_message": "",
  "error_code": ""
}
```

内部逻辑：

- `generation_agent is None`：走真实 `ResourceGenerationAgent`。
- `generation_agent is not None`：为保持既有测试，允许走兼容旧接口。
- 聚合每个资源的 `tool_trace`，保留 `planning_trace`。

### 4. 测试用例的构建描述

新增/更新用例：

- `test_resource_generation_agent_runs_real_tool_order_with_mock_generation`
  - 使用 mock generation tool。
  - 断言工具顺序完整。
- `test_resource_generation_agent_persists_from_tool_result`
  - 断言最终 resource 来自 `persist_generated_resource`。
- `test_run_resource_generation_agent_uses_agent_runtime_by_default`
  - 断言默认入口不再直接实例化旧 `LLMResourceGenerationAgent` 作为主控。
- `test_run_resource_generation_agent_keeps_fake_agent_compatibility`
  - 保护已有 fake agent 测试。

默认 CI 不触发真实 LLM/RAG。真实 Agent 测试用 `RUN_LLM_TESTS=1` 手动开启。

## 阶段 2：把旧 LiteLLM 内容生成器降级为兼容工具

### 0. 新增的常量定义

不新增全局常量。

建议在 `resource_agent_tools.py` 内定义内部工具名常量：

```python
TOOL_GENERATE_RESOURCE_PAYLOAD = "generate_resource_payload"
```

### 1. 影响的文件范围

```text
tasks/generative/resource_agent_tools.py
tasks/generative/resource_generation_agent.py
tests/test_generative_resource_agent_integration.py
tests/test_generative_task.py
```

### 2. 函数级收口的完整数据流

```text
tool_generate_resource_payload(state)
  -> read state["request"]
  -> read state["resource_type"]
  -> read state["planning_bundle"]
  -> call legacy content generator adapter
  -> state["generated_content"] = content
  -> return tool result
```

### 3. 精确到输入输出的函数级收口

#### `tool_generate_resource_payload(state: dict) -> dict`

输入 state：

```json
{
  "request": {"resource_type": "quiz"},
  "resource_type": "quiz",
  "planning_bundle": {
    "plan": {},
    "draft": {},
    "retrieval_context": {}
  }
}
```

输出：

```json
{
  "tool": "generate_resource_payload",
  "success": true,
  "resource_type": "quiz",
  "content": {
    "schema_version": "v1",
    "title": "HBase RowKey 设计 习题",
    "questions": []
  },
  "error_message": "",
  "error_code": ""
}
```

内部逻辑：

- 短期允许调用旧 `LLMResourceGenerationAgent.generate_resource_content(...)`。
- 旧生成器只能作为工具内部实现，不再作为资源模块主控。
- 若生成失败，返回 structured error，不抛裸异常给 Agent runtime。
- 工具必须写入：

```python
state["generated_content"] = generated_content
state["tool_trace"].append("generate_resource_payload")
```

#### `LegacyResourcePayloadGenerator`

职责：

- 封装旧 `LLMResourceGenerationAgent`。
- 暴露统一方法：

```python
generate(request_payload: dict, resource_type: str, planning_bundle: dict) -> dict
```

边界：

- 只允许 `resource_agent_tools` 调用。
- 后续阶段删除或替换。

### 4. 测试用例的构建描述

- mock `LegacyResourcePayloadGenerator.generate`，断言工具被调用。
- 断言旧生成器不再被 `run_resource_generation_agent` 直接调用。
- 断言工具失败时单资源返回 `success=false`，多资源聚合 `failed_count` 正确。
- 断言现有资源类型校验仍由 persistence 层执行。

## 阶段 3：将具体资源 JSON 生成迁移到 pydantic-ai structured output

### 0. 新增的常量定义

新增到 `resource_agent_contracts.py`：

```python
RESOURCE_OUTPUT_TOOL_NAMES = {
    "documents": "final_document_resource",
    "mindmap": "final_mindmap_resource",
    "quiz": "final_quiz_resource",
    "coding_practice": "final_coding_practice_resource",
    "ppt": "final_ppt_resource",
}
```

可选新增每类输出 schema model：

```text
DocumentResourcePayload
MindmapResourcePayload
QuizResourcePayload
CodingPracticeResourcePayload
PptResourcePayload
```

### 1. 影响的文件范围

```text
tasks/generative/resource_agent_contracts.py
tasks/generative/resource_agent_tools.py
tasks/generative/resource_agent_runtime.py
tasks/generative/resource_generation_agent.py
tasks/generative/validation.py
tests/test_generative_task.py
tests/test_generative_resource_agent_integration.py
```

### 2. 函数级收口的完整数据流

```text
generate_resource_payload tool
  -> dispatch by resource_type
      -> generate_document_payload
      -> generate_mindmap_payload
      -> generate_quiz_payload
      -> generate_coding_practice_payload
      -> generate_ppt_payload
  -> local normalization
  -> state["generated_content"]
```

### 3. 精确到输入输出的函数级收口

#### `generate_document_payload(request_payload: dict, planning_bundle: dict) -> dict`

输出必须满足：

```python
validate_document_payload(payload)
```

重要逻辑：

- sections 必须是列表。
- 每个 section 至少包含 `heading` 和 `body`。
- 保留现有 `extension_reading`。

#### `generate_mindmap_payload(request_payload: dict, planning_bundle: dict) -> dict`

输出必须满足：

```python
validate_mermaid_text(payload["mermaid"])
```

重要逻辑：

- `mermaid` 必须以 `mindmap`、`flowchart` 或 `graph` 允许前缀开头。
- 默认优先生成 `mindmap`。

#### `generate_quiz_payload(request_payload: dict, planning_bundle: dict) -> dict`

输出必须满足：

```python
validate_quiz_payload(payload)
```

重要逻辑：

- questions 必须是列表。
- 每题必须包含 `id`、`type`、`stem`、`options`、`answer`、`explanation`。

#### `generate_coding_practice_payload(request_payload: dict, planning_bundle: dict) -> dict`

输出必须满足：

```python
validate_coding_practice_payload(payload)
```

重要逻辑：

- `code_files` 必须可落盘。
- `run_guide` 必须包含入口和运行命令。

#### `generate_ppt_payload(request_payload: dict, planning_bundle: dict) -> dict`

输出必须满足：

```python
validate_ppt_payload(payload)
```

重要逻辑：

- slides 必须是列表。
- 第一页应为 cover。
- 保留现有 PPT normalization，避免文字溢出和 renderer 失败。

### 4. 测试用例的构建描述

- 每类资源 mock structured output 测试。
- 每类资源输出漂移测试：模型返回字符串/缺字段时 fallback normalization 生效。
- 每类资源 validation failure 测试。
- PPT 保留 renderer 和 `.pptx` 导出测试。
- 真实 LLM opt-in 测试覆盖 documents/mindmap/quiz/ppt 至少四类。

## 阶段 4：切换默认入口并废弃 LiteLLM 生成器

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
tasks/generative/resource_generation_agent.py
tasks/generative/resource_agent_runtime.py
tasks/generative_task.py
docs/resource_generation_dev_doc.md
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

最终目标：

```text
generative_task
  -> run_resource_generation_agent
      -> ResourceGenerationAgent runtime
          -> resource_agent_tools
          -> validation / persistence / renderers
```

旧路径：

```text
LLMResourceGenerationAgent
  -> LitellmMultiModel.call_text_model
```

只保留为兼容测试或完全删除。

### 3. 精确到输入输出的函数级收口

#### `LLMResourceGenerationAgent`

处理策略：

- 阶段 1-2：保留，但标记为 legacy compatibility。
- 阶段 3 后：不再被默认入口使用。
- 阶段 4：删除或只保留测试辅助替身。

#### `run_resource_generation_agent(request_payload: dict, *, generation_agent=None, planning_agent=None) -> dict`

最终职责：

- 默认使用真实 `ResourceGenerationAgent`。
- `generation_agent` 只作为测试注入或兼容注入。
- 返回结构保持兼容，避免 API/前端联调受影响。

### 4. 测试用例的构建描述

- 默认 task 测试保持通过。
- API 测试保持返回结构不变。
- 真实 LLM+RAG 集成测试产物中必须出现 Agent 工具 trace：

```text
read_generation_request
read_generation_plan
retrieve_generation_materials
write_generation_draft
generate_resource_payload
persist_generated_resource
```

- 删除或改写旧 LiteLLM 直接调用断言。
- `tests/TEST_REPORT.md` 更新真实 Agent 测试命令和产物路径。

## 阶段 5：文档和边界清理

### 0. 新增的常量定义

不新增。

### 1. 影响的文件范围

```text
docs/resource_generation_dev_doc.md
tests/TEST_REPORT.md
tasks/generative/small_plan.md
tasks/generative/contract.md
```

### 2. 函数级收口的完整数据流

```text
dev_doc
  -> 描述真实 Agent 入口
  -> 描述 tool order
  -> 描述 mock / real LLM / real RAG 测试分层
```

### 3. 精确到输入输出的函数级收口

文档必须明确：

- `tasks/generative_task.py` 是唯一跨模块入口。
- `tasks/generative/resource_agent_runtime.py` 是真实 Agent runtime。
- `ResourcePlanningAgent` 是规划工具/编排工具，不再单独宣称为最终 Agent。
- 资源生成 Agent 产物必须经 validation/persistence 才能对外返回。

### 4. 测试用例的构建描述

- 无新增业务测试。
- 只更新测试报告和开发文档。
- 保留 artifact 路径说明，方便前端/API 专职人员查看资源生成结果。

## 推荐落地顺序

建议先实现：

```text
阶段 1：新增真实资源生成 Agent runtime
阶段 2：旧 LiteLLM 内容生成器降级为兼容工具
```

这两步能先满足比赛对 Agent 形态的要求，并且最大限度复用已有五类资源生成、校验、落盘测试。

随后再单独推进：

```text
阶段 3：具体资源 JSON 生成迁移到 pydantic-ai structured output
阶段 4：废弃 LiteLLM 生成器
阶段 5：文档和边界清理
```

阶段 3 以后才是实质去 LiteLLM。不要把阶段 1-2 误认为已经完全去除旧模型调用；阶段 1-2 的目标是先让资源生成链路成为真正工具型 Agent。
