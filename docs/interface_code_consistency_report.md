**接口-代码一致性清单**

概述：对比项目中文档与代码实现，核对主要模块的路由、任务入口与返回字段；优先关注学习画像、学习路径推荐、资源生成、学习成长树四个模块。

**总体结论**: 核心调用链（路由 -> blueprint -> tasks -> 实现）与文档一致；主要差异为少数接口文件归属和蓝图层对响应做了外层包装（返回字段更具体）。当前已补上总 Agent 的 HTTP 蓝图，建议同步更新文档示例响应以便前端对接。

**检查项（按模块）**

- **学习画像 (User Profile)**: 路由: `POST /api/user_learning_profile`。
  - **实现文件**: [blueprint/user_api.py](blueprint/user_api.py#L320-L380)
  - **任务入口**: `tasks.learning_profile_task.get_or_build_learning_profile`（见 [tasks/learning_profile_task.py](tasks/learning_profile_task.py#L1-L200)）
  - **一致性**: 逻辑与文档一致（文档期望以 task 层为画像入口）。
  - **差异**: 文档将该接口归入 `learning_api`，实际实现位于 `user_api.py`；蓝图对返回做了标准包装（包含 `success/profile/profile_path/profile_saved/profile_refreshed`）。


- **学习路径推荐 (Personal Recommendation & Syllabus)**:
  - **路由**: `/api/learning_init_personal_syllabus`, `/api/learning_personal_syllabus_detail`, `/api/personal_recommendation`。
  - **实现文件**: [blueprint/learning_api.py](blueprint/learning_api.py#L1-L240)
  - **任务入口**: `tasks.learning_profile_task` 中的相关方法与 `tasks.personal_recommendation_task.run_recommendation_route_from_payload`（见 [tasks/personal_recommendation_task.py](tasks/personal_recommendation_task.py#L1-L200)）
  - **一致性**: 路由与 task 对应一致，输入字段（user_id、syllabus_id、refresh 等）与文档契约匹配。
  - **差异**: 无重大差异。蓝图对响应进行了统一外层包装（`success`、`error_message` 等）。
  - **建议**: 在文档中加入蓝图层的包装示例，明确 `success` 字段与错误码格式。

- **资源生成 (Generative Resource)**:
  - **路由**: `/api/generative_generate`, `/api/generative_list`, `/api/generative_detail`。
  - **实现文件**: [blueprint/generative_api.py](blueprint/generative_api.py#L1-L260)
  - **任务入口**: `tasks.generative_task.run_resource_generation_agent`、`tasks.generative_task.list_generated_resources`、`tasks.generative_task.get_generated_resource_detail`（见 [tasks/generative_task.py](tasks/generative_task.py#L1-L320)）。
  - **一致性**: 文档期望的资源类型、manifest 与生成流程与 task 层实现一致。
  - **差异**: 蓝图在响应中加入了具体的包装字段（如 `resources/resource_count`、`success` 等），并返回了带 `render` 的渲染内容（markdown/mermaid）——文档较抽象未逐字段列出。
  - **建议**: 把文档的示例响应扩写为与蓝图返回一致，特别是 `render`、`main_files`、`validation` 等字段的结构说明。

- **学习成长树 (Study Graph)**:
  - **路由**: `GET /api/study_graph/detail`, `GET /api/study_graph/features`, `POST /api/study_graph/agent_run`。
  - **实现文件**: [blueprint/study_graph_api.py](blueprint/study_graph_api.py#L1-L160)
  - **任务入口**: `tasks.study_graph_task`（见 [tasks/study_graph_task.py](tasks/study_graph_task.py#L1-L200)）
  - **一致性**: 已实现并在 `app` 中注册；三条路由通过测试客户端返回 200，任务调用链与文档描述一致（rag_search → get_tree_context → derive_payload → build_changes → submit_changes）。
  - **差异**: 返回有轻微外层包装（`success` / `error_message`），文档示例可补充真实返回字段。
  - **建议**: 在文档里补充 `agent_run` 的请求示例与成功/失败的返回示例。

- **总 Agent (Orchestration)**:
  - **路由**: `GET /api/total_agent/detail`, `POST /api/total_agent/run`, `POST /api/total_agent/agent_run`。
  - **实现文件**: [blueprint/total_agent_api.py](blueprint/total_agent_api.py#L1-L200)
  - **任务入口**: `tasks.total_agent_task.run_total_agent`、`tasks.total_agent_task.run_total_agent_agent`、`tasks.total_agent_task.get_total_agent`（见 [tasks/total_agent_task.py](tasks/total_agent_task.py#L1-L120)）
  - **一致性**: 调度链与文档一致；蓝图只做轻量参数解析和结果转发，不改变总 agent 的决策逻辑。
  - **差异**: `detail` 接口返回的是 agent 元信息而非可执行对象；这与 HTTP 可序列化约束一致。
  - **建议**: 文档中补充总 Agent 的输入示例、`tool_trace` 与 `tool_status_events` 示例，方便前端调试。



