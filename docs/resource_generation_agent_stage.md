# Resource Generation Agent Stage

## 1. 定位

当前阶段不实现总 agent 的复杂编排。总 agent 未来只需下发一个固定 payload，资源内部流程由资源生成 agent 自己完成。

当前收口链路：

`固定 payload -> 资源生成 agent -> 资源编排 agent -> 文件读写 tool`

当前对外入口：

`HTTP API -> 资源生成 agent -> 资源编排 agent -> 文件读写 tool`

职责边界：

- 总 agent：只下发请求，不进入资源内部流程
- 资源生成 agent：组织生成流程，调用编排 agent 和文件读写 tool
- 资源编排 agent：做计划、检索、草稿
- 文件读写 tool：做落盘、校验、索引更新

## 2. 当前代码

核心文件：

- `LianJue_Backend/blueprint/generative_api.py`
- `LianJue_Backend/tasks/resource_generation_agent_task.py`
- `LianJue_Backend/tasks/resource_planning_agent_task.py`
- `LianJue_Backend/tasks/generative_task.py`

当前实现与代码一致：

- `POST /api/generative_generate` 是最小生成入口
- `POST /api/generative_list` / `POST /api/generative_detail` 是结果读取入口
- `run_resource_generation_agent(...)` 是资源生成主入口
- `run_resource_planning_agent(...)` 是资源编排入口
- `persist_generated_resource(...)` 是统一文件持久化入口

资源生成 agent 当前会先归一化固定 payload，再按 `resource_types` 逐个生成资源。每个资源生成时：

1. 调用资源编排 agent
2. 读取或写入 plan
3. 检索资料
4. 读取或写入 draft
5. 生成结构化内容
6. 调用文件读写 tool 落盘

## 3. 资源编排 agent 的原子 tool

当前原子工作已经拆清楚：

- `read_generation_plan`
- `write_generation_plan`
- `retrieve_generation_materials`
- `read_generation_draft`
- `write_generation_draft`

这几个原子工作目前在 `resource_planning_agent_task.py` 内部实现，后续如果改成更显式的 tool 注册形式，也应保持这五类能力不变。

## 4. 文件读写 tool 收口

`generative_task.py` 当前已承担纯 tool 角色，负责：

- 持久化 `documents`
- 持久化 `mindmap`
- 持久化 `quiz`
- 持久化 `coding_practice`
- 持久化 `ppt`
- 更新 `manifest.json`
- 执行本地校验

与各资源类型契约的关系：

- 具体字段约束仍以 `LianJue_Backend/docs/generative_*_contract.md` 为准
- 本文档不重复逐类字段细节
- 当前阶段只关心资源生成链是否闭环

## 5. 当前完成度

已完成：

- 最小生成 API
- 结果 list/detail API
- 资源生成 agent 主入口
- 资源编排 agent 主入口
- 统一文件持久化 tool
- 固定 payload 的全流程测试
- 旧 `generative_task` 回归测试保持通过

当前全链路已验证资源类型：

- `documents`
- `mindmap`
- `quiz`
- `coding_practice`
- `ppt`

## 6. 测试

当前测试文件：

- `LianJue_Backend/tests/test_resource_planning_agent_integration.py`
- `LianJue_Backend/tests/test_generative_api.py`
- `LianJue_Backend/tests/test_resource_generation_agent_task.py`
- `LianJue_Backend/tests/test_generative_task.py`

测试意义：

- `test_resource_planning_agent_integration.py`
  验证资源编排 agent 自己层级的集成行为
  验证 plan / retrieval / draft 的单轮与多轮行为

- `test_generative_api.py`
  验证 HTTP API 能触发整条生成链
  验证 generate / list / detail 三个口

- `test_resource_generation_agent_task.py`
  验证固定 payload 下的资源生成全流程
  验证资源编排 agent 的原子 tool 顺序
  验证部分失败时的聚合收口

- `test_generative_task.py`
  验证各资源类型的文件写入、校验和 manifest 逻辑

当前已验证结果：

- 资源编排 agent 集成测试 + 资源生成 API 测试 + 资源生成 agent 全流程测试：`9 passed`
- `generative_task` 非 LLM/非 search 回归：`24 passed, 1 deselected`

当前测试的文件落盘方式：

- 资源生成链测试会真实生成文件
- 但都写入 `pytest` 提供的临时目录 `tmp_path`
- 不写入项目正式 `generative/` 目录
- 测试结束后这些临时文件不会作为正式结果保留

当前这些测试是否依赖数据库：

- 不依赖数据库持久化
- 不会因为“数据库开着”而把生成结果写入数据库
- 主要验证的是 agent/tool/file system 这条链

## 7. 固定 payload 收口

当前资源生成总输入以固定 payload 为准，核心字段是：

- `user_id`
- `question`
- `resource_types`

可选增强字段：

- `syllabus_id`
- `topic`
- `selected_weeks`
- `knowledge_items`
- `weak_points`
- `learning_goal`
- `retrieval_context`

这一层的原则是：

- 总 agent 只传请求
- 资源生成 agent 自己决定如何调用资源编排 agent

## 8. 下一步收口计划

下一步建议按顺序推进：

1. 把资源编排 agent 的 tool 调用形式再显式化
2. 再决定是否接审核 agent
3. 再补真实 LLM / 真实 search 集成测试
4. 最后再接总 agent

不建议当前阶段做的事：

- 让总 agent 介入资源内部编排
- 一次性接入路径 agent、审核 agent、前端新页面
- 把资源生成链重新塞回旧学生端实验逻辑
