# Resource generation single-type small plan

本文档已被 `docs/resource_generation_total_agent_split_contract.md` 和 `docs/resource_generation_dev_doc.md` 收口。当前真实实现已经升级为：Total Agent 只调用一次资源生成任务处理器，处理器先冻结所有单类型任务，再并行调用多个单类型 Resource Agent，并保留每个 Resource Agent 的 `tool_status_events` 用于前端状态回显。本文只保留为历史 small plan，不再作为开发事实源。

本文档用于收口资源生成的轻量并行化方向。核心判断是：暂不拆工具集、不拆多个专属子 Agent，而是由 Total Agent 把多资源需求拆成多个“单类型资源生成请求”，再把每个单一任务指派给现有 Resource Agent。

## 1. 背景判断

当前资源生成 Agent 已经具备多类型资源生成能力，包括：

- `documents`
- `quiz`
- `mindmap`
- `coding_practice`
- `ppt`

问题不在于工具集能力不足，而在于一次请求中同时生成多类资源时，Agent 容易线性处理所有类型，带来：

- 总耗时高。
- 上下文目标混杂。
- 单个资源类型失败可能拖累整体结果。
- 前端难以展示每类资源的独立进度。

因此更小的改法是：工具集不变，Resource Agent 不拆。Total Agent 负责判断需要哪些资源，并把每一种资源作为一个单独任务交给 Resource Agent。Resource Agent 每次只专心完成被指派的单一资源类型。

## 2. 目标

目标能力：

- 多资源需求由 Total Agent 拆成多个单类型请求。
- 每次调用现有 `generate_resources_from_request` 时只传一个 `resource_type`。
- 每个资源类型独立返回成功/失败、状态事件和资源结果。
- 聚合层合并多个单类型结果，形成统一响应。
- 在 Total Agent 工具层的资源任务处理器内并行，不需要修改资源生成工具集。

非目标：

- 不新增 `documents_agent / quiz_agent / ppt_agent` 等专属 Agent。
- 不重写现有 resource tools。
- 不改变单类型资源生成的 schema。
- 不要求 Total Agent 自己多次调用 Resource Agent；并行只发生在资源任务处理器内部。

## 3. 设计原则

```text
Total Agent 多资源请求
  -> decide full resource task list once
  -> freeze resource task list
  -> dispatch one Resource Agent call per resource_type
  -> each request contains exactly one resource_type
  -> call existing Resource Agent for each assigned single task
  -> aggregate resources / failures / status events
```

严禁退化成“边等边派”的串行陷阱：

```text
错误模式：
Total Agent -> 等 ppt 生成完成
Total Agent -> 再决定/请求 documents
Total Agent -> 等 documents 生成完成
Total Agent -> 再决定/请求 quiz

正确模式：
Total Agent -> 一次性决定 [ppt, documents, quiz]
Total Agent -> 冻结三个单类型任务
Total Agent -> 批量派发三个 Resource Agent 调用
Total Agent -> 聚合三个任务的状态和结果
```

当前实现必须满足“先完整拆单，再并行执行”的架构约束，避免 Total Agent 等第一个资源完成后再临时决定第二个资源，从架构上规避串行陷阱。

单类型请求示例：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "topic": "HBase RowKey 设计",
  "resource_types": ["quiz"],
  "difficulty": "targeted",
  "knowledge_items": ["RowKey 热点", "预分区"]
}
```

聚合结果示例：

```json
{
  "success": true,
  "overall_status": "partial_success",
  "resources": [],
  "resource_results": {
    "documents": {"success": true, "resources": []},
    "quiz": {"success": true, "resources": []},
    "mindmap": {"success": false, "error_code": "generation_failed"}
  },
  "failed_resource_types": ["mindmap"],
  "tool_status_events": []
}
```

## 4. 阶段计划

### 阶段 1：单类型请求约束

目标：

- 明确 Resource Agent 接收单类型请求时只生成该类型资源。
- 当 `resource_types` 长度为 1 时，现有行为保持稳定。
- 加测试防止单类型请求意外生成其他类型资源。

影响文件：

- `tasks/generative_task.py`
- `tasks/generative/*`
- `tests/test_generative_*`
- `docs/resource_generation_dev_doc.md`

测试：

```text
test_generate_resource_single_type_documents_only
test_generate_resource_single_type_quiz_only
test_generate_resource_single_type_mindmap_only
```

### 阶段 2：Total Agent 拆单调用

目标：

- 在 Total Agent 资源生成工具中新增两段式逻辑：
  - `plan_resource_type_tasks`：一次性冻结所有单类型任务。
  - `run_resource_type_tasks`：执行这些已冻结任务。

```python
plan_resource_type_tasks(request_payload: dict) -> list[dict]
run_resource_type_tasks(state: dict, tasks: list[dict]) -> dict
```

行为：

- 读取 `resource_types`。
- 去重、归一化。
- 先为每个 resource type 构造一个单类型 payload，并形成完整任务列表。
- 任务列表创建完成后，才开始执行 Resource Agent 调用。
- 对每个单类型 payload 调用现有 `generate_resources_from_request(single_payload)`。
- 聚合结果。

影响文件：

- `tasks/total_agent/agent_tools.py`
- `tests/test_total_agent_*`
- `tasks/generative_task.py` 只在确有必要时补单类型约束，不引入新的调度层。

测试：

```text
test_total_agent_splits_multi_resource_request_by_type
test_total_agent_freezes_all_resource_tasks_before_first_generation_call
test_total_agent_keeps_single_type_resource_request_behavior
test_total_agent_multi_resource_returns_partial_success
```

### 阶段 3：Total Agent 接入

目标：

- Total Agent 需要多类资源时，不再把多类型一次性交给 Resource Agent。
- 改为先一次性拆成多个单类型任务，再批量指派给 Resource Agent。
- `tool_generate_current_step_resource` 返回聚合后的资源结果。

边界：

- `suggested_next_action` 不变。
- `resources` 字段继续保留扁平资源列表，兼容前端。
- 新增 `resource_results` 和 `failed_resource_types` 作为扩展字段。

测试：

```text
test_total_agent_generate_multi_resource_uses_split_requests
test_total_agent_does_not_wait_first_resource_before_planning_remaining_tasks
test_total_agent_multi_resource_partial_failure_keeps_successful_resources
```

### 阶段 4：并发执行层

目标：

- `run_resource_type_tasks` 负责并行执行冻结后的单类型任务。
- 并行执行只发生在处理器内部，不改变 Total Agent 外部 payload。

可选实现：

- `ThreadPoolExecutor`
- `asyncio.gather`
- 后台 job queue

约束：

- 每个单类型请求独立写资源目录。
- manifest / DB 写入必须避免覆盖。
- status events 必须保留 resource type 维度。
- 决策层不得依赖任一单类型生成结果来决定剩余资源类型。
- 只有重试逻辑可以针对失败 resource type 单独再次调用。

测试：

```text
test_parallel_resource_generation_preserves_all_results
test_parallel_resource_generation_does_not_duplicate_manifest_entries
```

## 5. 前端展示影响

前端可按资源类型展示状态：

```text
documents: succeeded
quiz: running / succeeded
mindmap: failed, retry available
ppt: queued
```

接口返回应支持：

- 已成功生成的资源立即展示。
- 失败类型可单独重试。
- 不因为某个类型失败隐藏其他成功资源。

## 6. 验收标准

- 单类型请求只生成单一资源类型。
- 多类型请求可被拆成多个单类型调用。
- Total Agent 必须先冻结完整资源任务列表，再执行任何生成调用。
- 聚合结果保留 `resources` 兼容字段。
- 聚合结果新增 `resource_results` 和 `failed_resource_types`。
- 单类型失败不影响其他类型资源入库和返回。
- Resource Agent 工具集保持不变。
- 实现完成并同步 `resource_generation_dev_doc.md` 后，可删除本文。
