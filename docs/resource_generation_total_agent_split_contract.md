# Resource Generation Task Processor contract

本文档收口“多资源生成”的后端实现边界。业务形态保持轻量：Total Agent 不直接编排多个 Resource Agent；Total Agent 只调用一个大的资源生成任务处理器，由该处理器冻结任务列表、拆分单资源类型请求、调用若干 Resource Agent，并把每个 Resource Agent 的状态事件聚合回 Total Agent 结果，供前端展示 Agent cards / 生成进度。

## 总体边界

- 外部 Total Agent payload 不变，仍可传 `resource_types = ["ppt", "documents", "quiz"]`。
- Total Agent 只调用一次资源生成任务处理器，不在 Agent 推理过程中逐个等待和追加资源类型。
- 资源生成任务处理器负责一次性冻结完整任务列表。
- 资源生成任务处理器内部每个任务只调用一次单类型 Resource Agent。
- Resource Agent 每次只生成被指派的单一资源类型。
- 结构化字段 `resource_types` / `assigned_resource_type` 是资源类型唯一事实源；自然语言 `message/question` 不能新增或覆盖资源类型。
- 执行模式为冻结任务列表后并行执行：必须先冻结全部任务，再把冻结后的单类型任务交给线程池执行，不能边等边追加新任务。
- Resource Agent 的 `tool_status_events` 必须保留并回传。状态回显是前端展示的核心能力，不允许被聚合层吞掉。

## 阶段 1：单类型 Resource Agent 硬约束

### 0. 新增常量定义

新增或复用资源生成 warning code：

```python
RESOURCE_GENERATION_WARNING_TYPE_MISMATCH = "resource_type_mismatch"
RESOURCE_GENERATION_WARNING_NATURAL_LANGUAGE_TYPE_IGNORED = "natural_language_resource_type_ignored"
```

放置位置：

```text
tasks/generative/resource_agent_contracts.py
```

### 1. 影响的文件范围

```text
tasks/generative/resource_generation_agent.py
tasks/generative/resource_agent_tools.py
tasks/generative/resource_agent_contracts.py
tasks/generative_task.py
tests/test_generative_task.py
tests/test_generative_resource_agent_integration.py
docs/resource_generation_dev_doc.md
```

### 2. 函数级收口的完整数据流

```text
single_type_request
  -> normalize_generation_request
     -> resource_types normalized
     -> assigned_resource_type retained
     -> single_type_mode = true
  -> run_single_resource_generation_agent
     -> read_generation_request
     -> read_generation_plan
     -> retrieve_generation_materials
     -> write_generation_draft
     -> generate_resource_payload
     -> persist_generated_resource
  -> validate persisted resource_type == assigned_resource_type
  -> return single resource result with tool_status_events
```

自然语言冲突处理：

```text
request.resource_types = ["quiz"]
request.assigned_resource_type = "quiz"
request.message = "给我文档和小测"

=> only quiz is generated
=> "文档" only remains natural language context, not a resource type decision
=> warning may include natural_language_resource_type_ignored
```

### 3. 精确到输入输出的函数级收口

#### `normalize_generation_request(payload: dict) -> dict`

输入：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "message": "给我一份文档和小测",
  "topic": "HBase RowKey 设计",
  "resource_types": ["quiz"],
  "assigned_resource_type": "quiz"
}
```

输出：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "message": "给我一份文档和小测",
  "topic": "HBase RowKey 设计",
  "resource_types": ["quiz"],
  "assigned_resource_type": "quiz",
  "single_type_mode": true,
  "warnings": ["natural_language_resource_type_ignored"]
}
```

内部逻辑：

- `resource_types` 归一化、去重、保序。
- `assigned_resource_type` 必须在 `resource_types` 内。
- 单类型请求必须满足 `len(resource_types) == 1`。
- 不从 `message/question` 抽取额外资源类型。
- `message/question` 只影响主题、风格、难度、内容侧重点。

#### `generate_resource_payload` 工具

输入：

```json
{
  "resource_types": ["quiz"],
  "assigned_resource_type": "quiz",
  "generation_plan": {},
  "draft": {}
}
```

输出：

```json
{
  "success": true,
  "resource_type": "quiz",
  "resource": {},
  "tool_status_events": []
}
```

内部逻辑：

- 只生成 `assigned_resource_type`。
- 如果模型输出其他资源类型，工具层过滤或纠正。
- 无法纠正时返回失败，并加入 `resource_type_mismatch`。
- 每个工具运行必须继续通过 `emit_status_event` 产生 `tool_status_events`。

### 4. 测试用例的构建描述

```text
test_single_type_resource_request_generates_only_assigned_type
test_resource_agent_ignores_natural_language_resource_type_conflict
test_resource_generation_rejects_unassigned_resource_type_output
test_single_type_resource_result_keeps_tool_status_events
```

核心断言：

- `resource_types=["quiz"]` 只产生 quiz。
- `message="给我文档和小测"` 不会生成 documents。
- 非指派类型输出会失败或被过滤。
- 单类型 Resource Agent 返回中包含 `tool_status_events`。

## 阶段 2：资源生成任务处理器

### 0. 新增常量定义

新增任务状态和总体状态：

```python
RESOURCE_TASK_STATUS_PENDING = "pending"
RESOURCE_TASK_STATUS_RUNNING = "running"
RESOURCE_TASK_STATUS_SUCCEEDED = "succeeded"
RESOURCE_TASK_STATUS_FAILED = "failed"

RESOURCE_GENERATION_OVERALL_SUCCEEDED = "succeeded"
RESOURCE_GENERATION_OVERALL_PARTIAL_SUCCESS = "partial_success"
RESOURCE_GENERATION_OVERALL_FAILED = "failed"
```

放置位置：

```text
tasks/total_agent/agent_contracts.py
```

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tasks/total_agent/agent_contracts.py
tests/test_total_agent_task.py
docs/total_agent_dev_doc.md
docs/resource_generation_dev_doc.md
```

### 2. 函数级收口的完整数据流

```text
tool_generate_current_step_resource(state)
  -> get next_task
  -> build_current_step_resource_strategy(state)
  -> _build_resource_request(state, next_task, resource_strategy)
  -> process_resource_generation_request(state, request_payload)
     -> plan_resource_type_tasks(request_payload)
        -> freeze all resource tasks before generation
     -> run_resource_type_tasks(state, frozen_tasks)
        -> call generate_resources_from_request once per single-type task
        -> collect result and tool_status_events per task
     -> aggregate_resource_generation_results(task_results)
  -> return Total Agent tool result
```

架构硬约束：

```text
Total Agent -> process_resource_generation_request once
process_resource_generation_request -> Resource Agent N times
```

禁止：

```text
Total Agent -> Resource Agent ppt
Total Agent waits
Total Agent -> Resource Agent documents
Total Agent waits
Total Agent -> Resource Agent quiz
```

### 3. 精确到输入输出的函数级收口

#### `process_resource_generation_request(state: dict, request_payload: dict) -> dict`

输入：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "topic": "HBase RowKey 设计",
  "resource_types": ["ppt", "documents", "quiz"],
  "difficulty": "targeted",
  "knowledge_items": ["RowKey 热点", "预分区"],
  "message": "给我文档和小测",
  "status_callback": "<callable>"
}
```

输出：

```json
{
  "success": true,
  "overall_status": "partial_success",
  "resource_tasks": [],
  "resources": [],
  "resource_results": {
    "ppt": {},
    "documents": {},
    "quiz": {}
  },
  "failed_resource_types": ["quiz"],
  "tool_status_events": []
}
```

内部逻辑：

- 调用 `plan_resource_type_tasks` 得到完整任务列表。
- 把完整任务列表写入 `state["resource_type_tasks"]`。
- 生成开始前任务列表必须已完整冻结。
- 调用 `run_resource_type_tasks`。
- 调用 `aggregate_resource_generation_results`。
- 合并所有子 Resource Agent 的状态事件。

#### `plan_resource_type_tasks(request_payload: dict) -> list[dict]`

输入：

```json
{
  "resource_types": ["ppt", "documents", "quiz"],
  "message": "给我文档和小测"
}
```

输出：

```json
[
  {
    "task_id": "resource_task:ppt",
    "resource_type": "ppt",
    "status": "pending",
    "request": {
      "resource_types": ["ppt"],
      "assigned_resource_type": "ppt",
      "message": "给我文档和小测"
    }
  },
  {
    "task_id": "resource_task:documents",
    "resource_type": "documents",
    "status": "pending",
    "request": {
      "resource_types": ["documents"],
      "assigned_resource_type": "documents"
    }
  },
  {
    "task_id": "resource_task:quiz",
    "resource_type": "quiz",
    "status": "pending",
    "request": {
      "resource_types": ["quiz"],
      "assigned_resource_type": "quiz"
    }
  }
]
```

内部逻辑：

- 只从结构化 `resource_types` 读取目标类型。
- 去重并保持顺序。
- 每个任务复制基础 payload。
- 每个任务把 `resource_types` 改成单元素列表。
- 每个任务写入 `assigned_resource_type`。
- 不读取任何生成结果。
- 不根据自然语言新增资源类型。

### 4. 测试用例的构建描述

```text
test_resource_processor_plans_tasks_from_structured_resource_types
test_resource_processor_freezes_all_tasks_before_first_generation_call
test_resource_processor_does_not_use_message_to_add_resource_types
test_total_agent_calls_resource_processor_once
```

核心断言：

- 输入 `["ppt", "documents", "quiz"]` 会形成三个任务。
- 每个任务的 `resource_types` 长度为 1。
- `message` 中出现额外资源词不会增加任务。
- `tool_generate_current_step_resource` 只调用一次 `process_resource_generation_request`。

## 阶段 3：执行、聚合与状态回显

### 0. 新增常量定义

本阶段复用阶段 2 的任务状态和总体状态常量。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
tests/test_total_agent_task.py
docs/total_agent_dev_doc.md
```

### 2. 函数级收口的完整数据流

```text
frozen resource_tasks
  -> run_resource_type_tasks
     -> ThreadPoolExecutor submits every frozen task:
          set task.status = running
          call generate_resources_from_request(task.request)
          collect resources
          collect resource_result.tool_status_events
          annotate every event with task_id/resource_type if missing
          set task.status = succeeded/failed
  -> aggregate_resource_generation_results
     -> resources flat list
     -> resource_results by type
     -> failed_resource_types
     -> tool_status_events merged in execution order
     -> overall_status
```

### 3. 精确到输入输出的函数级收口

#### `run_resource_type_tasks(state: dict, tasks: list[dict]) -> dict`

输入：

```json
[
  {"task_id": "resource_task:ppt", "resource_type": "ppt", "request": {"resource_types": ["ppt"]}},
  {"task_id": "resource_task:documents", "resource_type": "documents", "request": {"resource_types": ["documents"]}},
  {"task_id": "resource_task:quiz", "resource_type": "quiz", "request": {"resource_types": ["quiz"]}}
]
```

输出：

```json
{
  "success": true,
  "overall_status": "partial_success",
  "resources": [],
  "resource_results": {
    "ppt": {"success": true, "resources": [], "tool_status_events": []},
    "documents": {"success": true, "resources": [], "tool_status_events": []},
    "quiz": {"success": false, "error_code": "generation_failed", "tool_status_events": []}
  },
  "resource_tasks": [],
  "failed_resource_types": ["quiz"],
  "tool_status_events": []
}
```

内部逻辑：

- 对每个 task 并行调用 `generate_resources_from_request(task["request"])`。
- 如果当前线程存在 Flask app context，执行器必须把 app context 显式带入子线程，保证 SQL 持久化不因为并行丢失上下文。
- 每个 task 独立 try/except。
- 成功资源进入全局 `resources`。
- 失败只进入对应 `resource_results[type]` 和 `failed_resource_types`。
- `tool_status_events` 必须从每个 Resource Agent result 中提取。
- 每个事件必须保留或补充：
  - `agent = "resource_agent"`
  - `stage`
  - `status`
  - `payload.resource_type`
  - `payload.task_id`
- `_extend_status_events(state, task_events)` 必须把子 Agent 状态合并回 Total Agent 状态。
- 如果某个结果返回了非指派类型资源，过滤该资源，并给该 task 追加 warning。

成功判定：

```text
all succeeded -> success=true, overall_status=succeeded
some succeeded -> success=true, overall_status=partial_success
none succeeded -> success=false, overall_status=failed
```

#### `aggregate_resource_generation_results(task_results: list[dict]) -> dict`

内部逻辑：

- 聚合资源列表。
- 聚合 status events。
- 聚合 warnings。
- 生成 `failed_resource_types`。
- 保留每个 resource type 的原始结果摘要。
- 不压扁掉 per-resource-type 的 `tool_status_events`。

### 4. 测试用例的构建描述

```text
test_resource_processor_calls_generation_once_per_type
test_resource_processor_aggregate_all_success
test_resource_processor_partial_failure_keeps_successful_resources
test_resource_processor_all_failed_returns_failure
test_resource_processor_filters_unassigned_resource_type_from_single_task_result
test_resource_processor_preserves_resource_agent_status_events
test_resource_processor_annotates_status_events_with_resource_type_and_task_id
```

测试构造：

- monkeypatch `generate_resources_from_request`，记录每次 request。
- 对 `quiz` 模拟失败，对其他类型模拟成功。
- 每个 fake result 返回不同的 `tool_status_events`。

核心断言：

- 调用次数等于资源类型数。
- 每次 request `resource_types` 长度为 1。
- `resources` 包含成功资源。
- `failed_resource_types == ["quiz"]`。
- 部分成功时 `success is True`。
- 聚合结果的 `tool_status_events` 包含每个 Resource Agent 的状态事件。
- 每个状态事件可被前端按 `resource_type/task_id` 分组展示。

## 阶段 4：Total Agent 返回结构与前端契约

### 0. 新增常量定义

本阶段不新增常量。

### 1. 影响的文件范围

```text
tasks/total_agent/agent_tools.py
docs/total_agent_dev_doc.md
docs/resource_generation_dev_doc.md
docs/project_open_document/07_interface_and_frontend_design.md
tests/test_total_agent_task.py
tests/total_agent/test_total_agent_e2e.py
```

### 2. 函数级收口的完整数据流

```text
tool_generate_current_step_resource
  -> process_resource_generation_request
  -> result includes:
       resources
       resource_results
       resource_tasks
       failed_resource_types
       overall_status
       tool_status_events
  -> Total Agent final result
  -> frontend renders resource cards and Resource Agent status cards
```

### 3. 精确到输入输出的函数级收口

`tool_generate_current_step_resource` 返回：

```json
{
  "tool": "generate_current_step_resource",
  "success": true,
  "resource_strategy": {"resource_types": ["ppt", "documents", "quiz"]},
  "resource_tasks": [],
  "generation_result": {},
  "resources": [],
  "resource_results": {
    "ppt": {},
    "documents": {},
    "quiz": {}
  },
  "failed_resource_types": [],
  "overall_status": "succeeded",
  "tool_status_events": [],
  "suggested_next_action": "record_learning_feedback"
}
```

兼容要求：

- `resources` 继续作为扁平列表返回。
- `generation_result` 继续存在，值为处理器聚合结果。
- 新增字段不能破坏旧测试。
- `tool_status_events` 必须包含 Resource Agent 子事件，前端可按 `payload.resource_type` 展示多资源生成进度。

前端展示字段：

- `resources`：展示成功资源。
- `resource_results`：按类型展示成功/失败详情。
- `failed_resource_types`：展示重试入口。
- `overall_status`：展示整体状态。
- `tool_status_events`：展示生成 Agent 的阶段状态。

### 4. 测试用例的构建描述

```text
test_total_agent_resource_tool_returns_processor_fields
test_total_agent_resource_tool_keeps_flat_resources
test_total_agent_resource_tool_exposes_resource_agent_status_events
test_total_agent_resource_tool_keeps_suggested_next_action
```

验收标准：

- Total Agent 结果能展示资源列表。
- Total Agent 结果能展示每个资源类型的状态。
- 前端不需要解析自然语言判断资源生成阶段。
- 子 Resource Agent 的 `read_generation_request/read_generation_plan/retrieve_generation_materials/write_generation_draft/generate_resource_payload/persist_generated_resource` 状态仍可显示。

## 阶段 5：回归与文档收口

### 0. 新增常量定义

本阶段不新增常量。

### 1. 影响的文件范围

```text
docs/resource_generation_dev_doc.md
docs/total_agent_dev_doc.md
docs/project_open_document/07_interface_and_frontend_design.md
tests/TEST_REPORT.md
```

### 2. 函数级收口的完整数据流

```text
pytest
  -> generative unit/integration
  -> total_agent task tests
  -> total_agent E2E mock regression
  -> docs updated
```

### 3. 精确到输入输出的函数级收口

回归命令：

```bash
python -m pytest -q tests/test_total_agent_task.py tests/test_generative_task.py tests/test_generative_resource_agent_integration.py -rs
```

E2E 回归：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

### 4. 测试用例的构建描述

验收标准：

- 外部 Total Agent payload 不变。
- Total Agent 只调用一次资源生成任务处理器。
- 任务处理器先冻结完整任务列表。
- 多类型需求触发多次单类型 Resource Agent 调用。
- 每次 Resource Agent 调用只生成指定类型。
- 自然语言 message 不能扩展资源类型。
- 部分失败仍返回成功资源。
- `resources` 兼容保留。
- Resource Agent 的 `tool_status_events` 聚合回 Total Agent 结果。
- 状态事件带有 `resource_type/task_id`，前端可分组展示。
- 实现完成并同步 dev docs 后，可删除本 contract 和旧 small plan。
