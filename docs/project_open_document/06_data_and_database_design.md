# 6 数据与数据库设计

## 6.1 数据持久化口径

项目开放文档采用生产级数据库口径描述核心业务数据。当前后端已经为学习计划、资源 metadata 和学生成长树提供数据库持久化后端；文件 manifest 或 JSONL 仍保留为兼容后端，其定位是：

- 本地开发和 E2E 测试的轻量存储。
- 显式文件后端或离线运行模式。
- 旧数据导入数据库时的迁移来源。

对外说明时，应以“数据库保存学习画像、学习计划、资源 metadata、成长树和事件日志”为主；在工程事实说明中再补充 manifest 兼容后端和测试 fixture 路径。

## 6.2 数据对象概览

核心数据对象：

- 用户与课程：`user`、`syllabus`、`user_syllabus`。
- 学习画像：profile summary、weak points、preferences、personal syllabus。
- 学习计划：plan、plan step、plan event。
- 资源：resource metadata、resource file、resource validation、resource feedback。
- 成长树：tree、node、edge、change log、features summary。
- Agent 运行：run、tool trace、status event、warnings。
- RAG 证据：evidence summary、query、relevance、source metadata。

待补图：数据库实体关系图 ERD。

## 6.3 用户与课程基础表

当前项目已有用户和课程相关数据库模型。生产数据设计应至少保留：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `user` | 用户基础信息 | `id`, `name`, `role`, `created_at`, `updated_at` |
| `syllabus` | 课程/大纲信息 | `id`, `title`, `subject`, `raw_content`, `created_at`, `updated_at` |
| `user_syllabus` | 用户与课程关系 | `user_id`, `syllabus_id`, `status`, `created_at` |

约束：

- `user_syllabus` 应保证 `UNIQUE(user_id, syllabus_id)`。
- 后续所有个人学习状态都应以 `user_id + syllabus_id` 隔离。

## 6.4 学习画像表

学习画像生产口径建议入库。当前模块级 dev doc 中的 JSON 结构可作为 `profile_json` 的原型。

建议表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `learning_profile` | 学生在某课程下的最新画像 | `profile_id`, `user_id`, `syllabus_id`, `learning_goal`, `risk_level`, `profile_json`, `source`, `created_at`, `updated_at` |
| `learning_profile_event` | 画像构建或更新事件 | `event_id`, `profile_id`, `event_type`, `payload_json`, `created_at` |
| `personal_syllabus` | 个性化教学大纲或学习建议 | `id`, `user_id`, `syllabus_id`, `content_json`, `created_at`, `updated_at` |

建议约束：

- `learning_profile`：`UNIQUE(user_id, syllabus_id)`。
- `profile_json` 保留完整结构，常用字段如 `learning_goal`、`risk_level` 可冗余为列便于查询。

## 6.5 学习计划表

当前学习计划生产后端写入数据库表，并保留 `personal_recommendation/learning_plan/.../manifest.jsonl` 作为测试、离线和显式文件后端。JSONL 事件结构已经映射到事件表，同时维护 plan / step 当前态表便于查询。

当前表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `learning_plan` | 当前或历史学习计划 | `plan_id`, `user_id`, `syllabus_id`, `status`, `source`, `candidate_index`, `path_json`, `created_at`, `updated_at` |
| `learning_plan_step` | 学习计划步骤 | `step_id`, `plan_id`, `node_id`, `title`, `outcomes_json`, `order_index`, `status`, `resource_ids_json`, `created_at`, `updated_at` |
| `learning_plan_event` | append-only 计划事件 | `entry_id`, `plan_id`, `user_id`, `syllabus_id`, `step_id`, `event_type`, `status`, `payload_json`, `created_at` |

约束：

- `learning_plan.user_id` → `user.user_id`（CASCADE）。
- `learning_plan.syllabus_id` → `syllabus.syllabus_id`（SET NULL，可为空）。
- `learning_plan_step.plan_id` → `learning_plan.plan_id`（NO ACTION）。
- `learning_plan_event.plan_id` → `learning_plan.plan_id`（CASCADE）。
- `learning_plan_step` 对同一 `plan_id` 的 `order_index` 唯一。
- 同一 `user_id + syllabus_id` 同时只能有一个 `active` plan，通过业务逻辑保证。

兼容与迁移说明：

- 难度低到中等；现有 JSONL 事件天然映射到 `learning_plan_event`。
- 生产读写必须依赖数据库 app context；`PERSONAL_RECOMMENDATION_ROOT` 或 `LEARNING_PLAN_FILE_BACKEND=1` 仅用于测试、离线和显式文件后端。
- `get_active_learning_plan` 可从事件 replay 得到状态；数据库后端同时维护 `learning_plan` / `learning_plan_step` 当前态表提升查询效率。
- 同一 plan 的事件写入会保证 `created_at` 单调递增，避免同秒事件 replay 顺序漂移。

## 6.6 资源数据表

资源生成生产后端使用数据库保存 resource metadata 和主文件索引，实际 Markdown、JSON、PPTX、SVG 等产物继续保存在文件系统或对象存储中。`generative/user_{user_id}/manifest.json` 和资源目录保留为测试、离线和显式文件后端。

当前表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `generated_resource` | 资源主表 | `resource_id`, `user_id`, `syllabus_id`, `step_id`, `resource_type`, `title`, `topic`, `status`, `validation_json`, `metadata_json`, `created_at`, `updated_at` |
| `generated_resource_file` | 资源文件索引 | `id`, `resource_id`, `file_role`, `path_or_url`, `mime_type`, `created_at` |
| `resource_feedback` | 学生对资源的反馈 | `id`, `resource_id`, `user_id`, `feedback_state`, `score`, `payload_json`, `created_at` |

建议约束：

- `generated_resource.resource_id` 唯一。
- `generated_resource_file` 对同一 `resource_id + file_role` 可唯一。
- 实际大文件、Markdown、PPTX、SVG 等可保留在文件系统或对象存储，数据库保存路径和 metadata。

兼容与迁移说明：

- 难度中等。
- metadata 已可直接入库；实际产物文件不全文入库，只保存对象存储路径或文件路径引用。
- 生产读写必须依赖数据库 app context；`GENERATIVE_FILE_BACKEND=1` 或 `GENERATOR_FILE_BACKEND=1` 仅用于测试、离线和显式文件后端。
- 旧 manifest 的 `resources[]` 可以批量迁入 `generated_resource`，`main_files` 可迁入 `generated_resource_file`。

## 6.7 学生成长树表

学生成长树生产后端使用数据库保存树、节点、边和变更日志，并保留以下文件后端用于测试、离线和显式文件模式：

```text
study_graph/user_{user_id}/syllabus_{syllabus_id}/manifest.json
study_graph/user_{user_id}/syllabus_{syllabus_id}/change_log.jsonl
```

生产口径已拆为树、节点、边、变更日志四类表。

当前表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `study_graph_tree` | 每个学生每门课程一棵成长树 | `tree_id`, `user_id`, `syllabus_id`, `subject_title`, `title`, `summary_json`, `created_at`, `updated_at` |
| `study_graph_node` | 知识节点 | `node_id`, `tree_id`, `type`, `title`, `normalized_title`, `aliases_json`, `summary`, `mastery_label`, `mastery_score`, `display_json`, `source_json`, `first_seen_at`, `last_updated_at` |
| `study_graph_edge` | 树边 | `edge_id`, `tree_id`, `source_node_id`, `target_node_id`, `edge_type`, `created_at`, `updated_at` |
| `study_graph_change_log` | 变更请求和裁决结果 | `id`, `tree_id`, `client_change_id`, `status`, `request_json`, `result_json`, `reason`, `created_at` |

约束：

- `study_graph_tree.user_id` → `user.user_id`（CASCADE）。
- `study_graph_tree.syllabus_id` → `syllabus.syllabus_id`（CASCADE）。
- `study_graph_tree`：`UNIQUE(user_id, syllabus_id)`。
- `study_graph_node.tree_id` → `study_graph_tree.tree_id`（NO ACTION）。
- `study_graph_node`：`UNIQUE(tree_id, normalized_title)`。
- `study_graph_edge.tree_id` → `study_graph_tree.tree_id`（NO ACTION）。
- `study_graph_edge`：`UNIQUE(tree_id, source_node_id, target_node_id, edge_type)`。
- `study_graph_change_log.tree_id` → `study_graph_tree.tree_id`（NO ACTION）。
- `study_graph_change_log`：`UNIQUE(tree_id, client_change_id)`。

兼容与迁移说明：

- 难度中等。
- manifest 中 `nodes`、`edges`、`summary` 映射清晰，数据库表中同时保留 `manifest_json` 兼容快照。
- `change_log.jsonl` 已具备幂等键 `client_change_id`，适合迁入事件表。
- 生产读写必须依赖数据库 app context；`STUDY_GRAPH_FILE_BACKEND=1` 仅用于测试、离线和显式文件后端。

## 6.8 Agent 运行状态表

为了支持生产级前端展示和问题排查，建议将关键 Agent 运行记录入库。

建议表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `agent_run` | 一次 Total Agent 或专项 Agent 调用 | `run_id`, `user_id`, `syllabus_id`, `intent`, `success`, `suggested_next_action`, `error_code`, `error_message`, `created_at`, `updated_at` |
| `agent_tool_event` | 工具状态事件 | `event_id`, `run_id`, `agent`, `stage`, `status`, `message`, `payload_json`, `created_at` |
| `agent_warning` | 结构化 warning | `id`, `run_id`, `warning_code`, `payload_json`, `created_at` |

建议约束：

- `agent_run.run_id` 唯一。
- `agent_tool_event` 按 `run_id + created_at` 查询，用于前端状态流。

迁移难度评估：

- 难度低。
- 当前 `tool_status_events` 已是结构化列表，可直接写入事件表。

## 6.9 RAG 证据与查询记录

RAG 证据可不作为长期业务主数据，但生产环境建议保留轻量调用记录，用于可解释性和调试。

建议表：

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `rag_query_log` | RAG 查询记录 | `id`, `run_id`, `query`, `graph_name`, `top_k`, `created_at` |
| `rag_evidence_log` | RAG 证据摘要 | `id`, `query_log_id`, `title`, `source`, `summary`, `score`, `relevance`, `created_at` |

约束：

- 不保存过长原文。
- 只保存轻量摘要和 source metadata。
- 涉及隐私或版权内容时应保留可清理策略。

## 6.10 当前实现与生产数据库的关系

| 数据 | 当前实现 | 生产目标 | 兼容说明 |
| --- | --- | --- | --- |
| 学习画像 | JSON/模块持久化 | `learning_profile` + event | 保留 JSON 字段并抽常用列 |
| 学习计划 | DB 后端 + JSONL manifest 文件后端 | plan + step + event 表 | 生产默认 DB；manifest 仅测试/离线/显式文件后端 |
| 生成资源 | DB metadata 后端 + manifest 文件后端 + 文件目录 | resource metadata 表 + 文件对象存储 | 生产默认 DB metadata；文件内容留对象存储或文件系统 |
| 成长树 | DB 后端 + manifest/change_log 文件后端 | tree + node + edge + change_log 表 | 生产默认 DB；manifest 仅测试/离线/显式文件后端 |
| Agent 状态 | run result 内列表 | agent_run + agent_tool_event | 调用结束后批量写入 |
| RAG 证据 | 运行时 result | query/evidence log | 保留轻量摘要即可 |
| 旧材料 | 已从后端运行时清退 | 无 | `material` / `syllabusmaterials` 属于旧 syllabus_material 流程，无保留价值；真实 MySQL 备份后可 drop |

Manifest 扫描结论：

- 已纳入本轮生产数据库化的 manifest：learning plan `manifest.jsonl`、generative resource `manifest.json`、study graph `manifest.json` / `change_log.jsonl`。
- 测试目录下的 manifest / JSONL 是 fixture 或 artifact，不作为生产持久化事实源。
- `profiles/` 和 `schedule/student_alt` 当前属于学习画像与个性化大纲的文件型实现，是否入库应跟随 Learning Profile / Personal Syllabus 模块单独收口，不混入本轮 runtime state 迁移。
- `pdfs`、`markdowns`、`triples`、`knowledge` 等路径属于课程资料导入、RAG 中间产物或知识库构建结果，不等同于用户运行态 manifest。

## 6.11 数据安全与隐私边界

课程聚合摘要只输出聚合统计、弱节点摘要和最小可用诊断，不输出其他学生明细。个人成长树、学习画像、学习计划、资源反馈应按 `user_id + syllabus_id` 隔离。

生产数据库需要补充：

- 用户权限校验。
- 课程访问控制。
- 个人学习数据脱敏导出。
- 运行日志清理策略。
- RAG 证据和生成资源的内容安全审查记录。

