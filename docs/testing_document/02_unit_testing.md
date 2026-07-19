# 项目测试文档 - 单元测试

## 2 单元测试

### 2.1 学习计划状态机模块

#### 2.1.1 测试用例与结果分析

##### 单元测试用例 UT-02-001：确认推荐路径并创建活动计划

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-001 |
| 测试单元描述 | 学习计划生命周期中“候选路径确认后创建活动计划”的本地状态机逻辑 |
| 用例目的 | 验证 accept 学习路径后，系统能够创建 active plan，并正确初始化步骤状态 |
| 前提条件 | 已存在 mock 推荐路径；测试使用 mock profile 和 mock learning tree；不依赖真实 LLM/RAG/DB |
| 特殊的规程说明 | 本用例只验证状态机和 manifest 写入，不验证推荐质量 |
| 用例间的依赖关系 | UT-02-002、UT-02-003、UT-02-004 依赖本用例创建的 active plan |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用计划 accept 测试入口 | mock recommendation candidate | 返回 `success=True` | `tests/total_agent/test_plan_lifecycle.py::test_plan_accept_creates_active_plan` 覆盖 | 测试入口明确 |
| 2 | 读取 active plan | user_id、syllabus_id | plan 不为空，状态为 active | 断言 `plan["status"] == active` | 通过 |
| 3 | 检查步骤状态 | 3 个 mock steps | 第 1 步 active，其余 pending | 断言 steps 长度为 3，状态分别为 active/pending/pending | 通过 |

##### 单元测试用例 UT-02-002：完成步骤并推进下一步

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-002 |
| 测试单元描述 | 学习计划步骤完成后的状态更新逻辑 |
| 用例目的 | 验证当前步骤完成后，系统能将下一步骤自动激活 |
| 前提条件 | 已存在 active plan，且至少包含 2 个待学习步骤 |
| 特殊的规程说明 | 完成中间步骤时不应直接完成整个 plan |
| 用例间的依赖关系 | 依赖 UT-02-001 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 提交当前步骤完成 | active step_id、完成反馈 | 当前步骤状态变为 completed | `test_step_completion_updates_status` 覆盖 | 通过 |
| 2 | 查询计划步骤 | plan_id | 下一步骤从 pending 变为 active | 测试断言第 2 步状态变为 active | 通过 |
| 3 | 检查未到达步骤 | 后续 step | 未到达步骤仍保持 pending | 测试断言后续步骤未错误激活 | 通过 |

##### 单元测试用例 UT-02-003：完成最后一步并结束计划

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-003 |
| 测试单元描述 | 学习计划最后一步完成后的自动结束逻辑 |
| 用例目的 | 验证最后一个步骤完成后，plan 状态变为 completed，且不再返回 active plan |
| 前提条件 | 已存在 active plan；当前步骤为最后一个步骤 |
| 特殊的规程说明 | completed plan 是终态，不应被后续 active 查询返回 |
| 用例间的依赖关系 | 依赖 UT-02-001、UT-02-002 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 完成最后一个步骤 | last step_id | 返回 `status=completed` | `test_plan_auto_completes_on_last_step` 覆盖 | 通过 |
| 2 | 查询 active plan | user_id、syllabus_id | 返回 None | 测试断言 active is None | 通过 |
| 3 | 检查事件记录 | plan event log | 包含 plan completed 事件 | 测试断言存在 `EVENT_PLAN_COMPLETED` | 通过 |

##### 单元测试用例 UT-02-004：放弃计划与新计划替换

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-004 |
| 测试单元描述 | 学习计划 abandon 和 supersede 状态处理 |
| 用例目的 | 验证用户放弃计划后无 active plan；接受新计划时旧 active plan 被 superseded |
| 前提条件 | 已存在 active plan |
| 特殊的规程说明 | 已完成计划不应被 supersede；只有 active plan 接受新计划时才产生替换关系 |
| 用例间的依赖关系 | 依赖 UT-02-001 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用 abandon | reason | plan 状态变为 abandoned | `test_plan_abandon` 覆盖 | 通过 |
| 2 | 查询 active plan | user_id、syllabus_id | 返回 None | 测试断言 active is None | 通过 |
| 3 | 接受新推荐路径 | second candidate | 新 plan active，旧 plan superseded | `test_plan_supersede_on_new_accept` 覆盖 | 通过 |
| 4 | 已完成后新建计划 | completed plan + new candidate | 新计划创建成功，无 superseded_plan_id | `test_new_plan_after_completion` 覆盖 | 通过 |

#### 2.1.2 测试结果综合分析及建议

学习计划状态机单元测试覆盖了创建、步骤完成、自动完成、放弃、替换和完成后新建计划等关键分支。测试结果表明，计划状态和步骤状态具备明确终态边界，能够支撑前端右上角计划卡片的开始渲染、停止渲染和进度更新。

建议将“无 active plan 时不得读取旧候选路径或旧历史生成计划”作为后续回归断言，防止 Agent 在无计划状态下误报已有计划。

#### 2.1.3 测试经验总结

计划状态测试必须以结构化字段为准，包括 `plan_id`、`status`、`steps.status`、`superseded_plan_id` 和事件类型。自然语言回复只能作为展示结果，不能作为状态正确性的唯一依据。

### 2.2 学习路径推荐模块

#### 2.2.1 测试用例与结果分析

##### 单元测试用例 UT-02-005：生成推荐候选路径

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-005 |
| 测试单元描述 | `personal_recommendation_task` 根据画像、学习树和目标生成候选路径 |
| 用例目的 | 验证推荐任务入口能够返回推荐图、候选路径、最佳路径和规划提示 |
| 前提条件 | 固定 profile/tree fixture 可用；mock 外部依赖 |
| 特殊的规程说明 | 默认单元测试不访问真实 RAG；真实 RAG 由 opt-in 集成测试覆盖 |
| 用例间的依赖关系 | 为功能测试中的“生成学习路径推荐”提供模块依据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用推荐任务入口 | user_id、syllabus_id、learning_goal | 返回 `success=True` | `test_personal_recommendation_task_generates_candidates` 覆盖 | 通过 |
| 2 | 检查 schema | 推荐结果 | `schema_version` 正确，`error_code` 为空 | 测试断言 schema 和 error_code | 通过 |
| 3 | 检查 graph | 推荐图 | nodes、edges 为列表且 nodes 非空 | 测试断言 graph 结构 | 通过 |
| 4 | 检查 candidates | 候选路径列表 | 每条 candidate 包含 path、full_path、actionable_path、context_path、skills 等字段 | 测试逐项断言字段类型 | 通过 |

##### 单元测试用例 UT-02-006：推荐 API 参数校验与快照

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-006 |
| 测试单元描述 | `/api/personal_recommendation` 的参数校验、推荐快照创建、详情和列表读取 |
| 用例目的 | 验证推荐 API 包装层能够正确返回推荐结果，并保存 proposed 快照 |
| 前提条件 | API client 可用；测试数据库或 mock repository 可用 |
| 特殊的规程说明 | API 层只做参数包装和快照管理，推荐算法由 task 层负责 |
| 用例间的依赖关系 | UT-02-007 可依赖本用例生成的 recommendation_id |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | POST 推荐接口 | `/api/personal_recommendation`，包含 user_id/syllabus_id | HTTP 200，`success=True` | `test_personal_recommendation_api_with_syllabus` 覆盖 | 通过 |
| 2 | 缺失 user_id | 空 JSON 或缺失字段 | HTTP 400，`error_code=missing_fields` | `test_personal_recommendation_api_requires_user_id` 覆盖 | 通过 |
| 3 | 读取推荐详情 | `/api/recommendations/{recommendation_id}` | 返回 snapshot 和 recommendation 详情 | `test_recommendation_snapshot_detail_and_list_api` 覆盖 | 通过 |
| 4 | 读取推荐列表 | `/api/recommendations?user_id=...&syllabus_id=...` | 返回快照列表，列表项不携带完整 recommendation | 测试断言列表轻量化 | 通过 |

##### 单元测试用例 UT-02-007：推荐快照确认生成学习计划

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-007 |
| 测试单元描述 | `/api/recommendations/{recommendation_id}/accept` 将候选路径确认为学习计划 |
| 用例目的 | 验证用户选择候选路径后，系统按指定 candidate 创建学习计划 |
| 前提条件 | 已存在 proposed recommendation snapshot |
| 特殊的规程说明 | accept 时必须使用已有快照中的候选路径，不重新生成推荐 |
| 用例间的依赖关系 | 依赖 UT-02-006 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 创建推荐快照 | 推荐请求 | 返回 recommendation_id | API 测试创建快照 | 通过 |
| 2 | 调用 accept 接口 | candidate_index=1 | HTTP 200，`success=True` | `test_recommendation_snapshot_accept_api_creates_plan` 覆盖 | 通过 |
| 3 | 检查快照状态 | accept 返回值 | `snapshot_status=accepted`，`accepted_candidate_index=1` | 测试断言对应字段 | 通过 |
| 4 | 检查计划步骤 | accepted steps | steps 来自指定候选路径 | 测试断言 node_id 为 `["n1", "n3"]` | 通过 |

##### 单元测试用例 UT-02-008：推荐算法边界与 RAG overlay

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-008 |
| 测试单元描述 | 推荐路径图适配、RAG overlay、软剪枝和得分归一化等算法边界 |
| 用例目的 | 验证推荐算法能找到可达路径，过滤不合理边，并保留可执行路径 |
| 前提条件 | 固定推荐图 fixture、mock RAG 结果可用 |
| 特殊的规程说明 | 本用例验证推荐内部确定性逻辑，不验证真实 LLM 工具选择 |
| 用例间的依赖关系 | 与 UT-02-005 共同保证推荐结果结构正确 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 构造推荐图 | 节点、边、目标节点 | graph adapter 能找到路径 | `test_personal_recommendation_graph_adapter_finds_path` 覆盖 | 通过 |
| 2 | 注入 mock RAG | mock_graph、query | RAG 证据进入 route_payload | `test_personal_recommendation_agent_tools_keep_rag_outside_algorithm` 覆盖 | 通过 |
| 3 | 检查 overlay | mock RAG matched nodes | `rag_overlay.enabled=True` 且存在 matched_nodes | `test_personal_recommendation_mock_rag_route_graph_closes` 覆盖 | 通过 |
| 4 | 检查路径输出 | candidate paths | 输出 full_path、actionable_path、context_path | `test_recommendation_outputs_full_and_actionable_paths` 覆盖 | 通过 |

#### 2.2.2 测试结果综合分析及建议

推荐模块单元测试不仅覆盖候选路径生成，还覆盖 API 快照、候选路径确认、路径图算法和 RAG overlay 边界。推荐快照 accept 测试对当前系统很关键，因为它验证了“选择某个具体候选路径”不会重新生成推荐，而是按已有 snapshot 创建计划。

建议持续保留快照状态断言，包括 proposed、accepted、accepted_candidate_index 和 steps 来源，防止后续 Agent 对话入口绕过快照导致状态混乱。

#### 2.2.3 测试经验总结

推荐模块测试需要区分三个层面：算法结果、API 快照、计划确认。算法结果解决“推荐什么”，快照解决“用户看到什么”，accept 解决“用户选择什么”。三者分离后，更容易定位推荐错误、上下文错误和计划状态错误。

### 2.3 学习画像模块

#### 2.3.1 测试用例与结果分析

##### 单元测试用例 UT-02-009：学习画像详情读取

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-009 |
| 测试单元描述 | `/api/learning_profile_detail` 读取已持久化画像 |
| 用例目的 | 验证画像详情接口只读取 persisted profile，不在详情读取时隐式刷新画像 |
| 前提条件 | 已存在 user_id/syllabus_id 对应的持久化画像 |
| 特殊的规程说明 | detail 接口用于展示，refresh 接口用于重建，两者职责分离 |
| 用例间的依赖关系 | UT-02-010 验证 refresh |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | POST 画像详情接口 | `/api/learning_profile_detail`，user_id=5，syllabus_id=21 | HTTP 200 | `test_learning_profile_detail_api_reads_persisted_profile_only` 覆盖 | 通过 |
| 2 | 检查返回标志 | 响应 JSON | `profile_saved=True`，`profile_refreshed=False` | 测试断言对应字段 | 通过 |
| 3 | 缺失参数 | 缺失 user_id 或 syllabus_id | HTTP 400，`error_code=missing_fields` | `test_learning_profile_detail_api_requires_user_id_and_syllabus_id` 覆盖 | 通过 |

##### 单元测试用例 UT-02-010：学习画像刷新

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-010 |
| 测试单元描述 | `/api/learning_profile_refresh` 调用画像构建链路 |
| 用例目的 | 验证画像刷新接口会调用 `build_learning_profile` 并返回刷新结果 |
| 前提条件 | user_id、syllabus_id 和可选学习记录输入存在 |
| 特殊的规程说明 | refresh 会触发画像重建，应与 detail 读取分离 |
| 用例间的依赖关系 | 可为 Total Agent 画像读取测试提供 persisted profile |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | POST 画像刷新接口 | `/api/learning_profile_refresh` | HTTP 200 | `test_learning_profile_refresh_api_calls_build_learning_profile` 覆盖 | 通过 |
| 2 | 检查刷新标志 | 响应 JSON | `profile_refreshed=True` | 测试断言字段 | 通过 |
| 3 | 缺失 user_id | 仅传 syllabus_id | HTTP 400，`error_code=missing_fields` | `test_learning_profile_refresh_api_requires_user_id` 覆盖 | 通过 |
| 4 | 访问旧接口 | `/api/user_learning_profile` | HTTP 404 | `test_user_learning_profile_api_removed` 覆盖 | 通过 |

##### 单元测试用例 UT-02-011：画像工具链与输入变体

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-011 |
| 测试单元描述 | 用户行为、答题记录、资源使用记录到画像字段的本地构建逻辑 |
| 用例目的 | 验证画像工具链能归一化事件、计算特征、组装画像并处理输入变体 |
| 前提条件 | 学习记录、答题记录、资源使用记录 fixture 可用 |
| 特殊的规程说明 | 单元测试不验证真实 Profile Agent 工具选择 |
| 用例间的依赖关系 | 为画像准确性系统测试提供模块依据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 输入学习行为数据 | dialogue_text、learning_records、answer_records、resource_usage | 能生成结构化画像字段 | `tests/test_learning_profile.py` 覆盖 | 通过 |
| 2 | 执行工具链 | normalize、compute、assemble、save | 工具链完整执行 | `tests/test_learning_profile_toolchain.py` 覆盖 | 通过 |
| 3 | 输入异常变体 | 缺失目标、空行为、非标准时间 | 输出 warning 或降级结果，不崩溃 | `tests/test_learning_profile_input_variants.py` 覆盖 | 通过 |
| 4 | 个人大纲联动 | syllabus fixture | 初始化个人大纲并回写路径 | `test_profile_personal_syllabus_full_chain.py` 覆盖 | opt-in 链路 |

#### 2.3.2 测试结果综合分析及建议

画像模块单元测试明确区分了详情读取、刷新重建、工具链构建和输入变体处理。接口层职责较清晰，detail 不会隐式刷新，refresh 才触发画像构建，这有利于前端控制刷新时机。

建议继续保持旧接口删除的测试断言，避免前端或其他模块继续依赖已废弃入口。

#### 2.3.3 测试经验总结

画像测试应同时验证接口行为和画像字段结构。对于 Agent 消费侧，更重要的是画像能否被稳定读取和归一化，而不是每次自然语言摘要完全一致。

### 2.4 学习资源生成模块

#### 2.4.1 测试用例与结果分析

##### 单元测试用例 UT-02-012：生成全部资源类型并写入 manifest

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-012 |
| 测试单元描述 | documents、mindmap、quiz、coding_practice、ppt 五类资源的本地生成与 manifest 累计 |
| 用例目的 | 验证资源生成 task 能按资源类型分发、校验、落盘并维护 manifest |
| 前提条件 | mock generation agent 可用；临时资源目录可写 |
| 特殊的规程说明 | 默认单元测试不访问真实 LLM 和真实搜索 |
| 用例间的依赖关系 | UT-02-013、UT-02-014 依赖生成资源和 manifest |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 请求五类资源 | resource_types=`documents,mindmap,quiz,coding_practice,ppt` | 五类资源均生成成功 | `test_generate_resource_full_user_chain_persists_all_resource_types` 覆盖 | 通过 |
| 2 | 检查资源状态 | 生成结果列表 | 每个资源 `success=True`、`status=ready` | 测试断言全部 ready | 通过 |
| 3 | 检查 manifest | manifest.json | `resource_count=5`，资源类型顺序正确 | 测试断言 manifest 资源数量和类型 | 通过 |
| 4 | 检查文件路径 | main_files | 每个主文件存在 | 测试逐项检查路径存在 | 通过 |

##### 单元测试用例 UT-02-013：资源列表和详情包装

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-013 |
| 测试单元描述 | 根据 manifest 列出资源，并读取单个资源的前端可渲染详情 |
| 用例目的 | 验证资源列表排序、类型过滤、limit 和 detail 包装 |
| 前提条件 | 已存在资源 manifest 和资源文件 |
| 特殊的规程说明 | 列表/详情只读取文件，不触发资源重新生成 |
| 用例间的依赖关系 | 依赖 UT-02-012 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取资源详情 | resource_id | 返回 content 和 render | `test_get_generated_resource_detail_resolves_repo_relative_paths` 覆盖 | 通过 |
| 2 | 列出资源 | user_id、syllabus_id | 按 created_at 过滤和排序 | `test_list_generated_resources_filters_and_sorts` 覆盖 | 通过 |
| 3 | 按类型分组 | resource_types、limit | 按资源类型返回并应用 limit | `test_list_generated_resources_by_type_applies_limit` 覆盖 | 通过 |
| 4 | 读取渲染包装 | quiz 资源 | 返回 `render.markdown` | `test_get_generated_resource_detail_returns_render_ready_wrapper` 覆盖 | 通过 |

##### 单元测试用例 UT-02-014：资源校验与异常状态

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-014 |
| 测试单元描述 | 资源 payload 校验、非法结构标记和不安全路径拒绝 |
| 用例目的 | 验证资源生成失败或结构不合法时不会写出错误主文件，并在 manifest 中记录 invalid 状态 |
| 前提条件 | validation 模块和临时目录可用 |
| 特殊的规程说明 | invalid 状态也是可追踪结果，不应被误判为系统异常崩溃 |
| 用例间的依赖关系 | 与 UT-02-012 共同覆盖成功和失败路径 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 输入无效 mindmap | 非法 Mermaid | 返回 `status=invalid`，validation errors 非空 | `test_generate_mindmap_marks_invalid_when_mermaid_validation_fails` 覆盖 | 通过 |
| 2 | 输入无效 quiz | 缺失 options | validation 返回 invalid | `test_validate_quiz_payload_rejects_missing_options` 覆盖 | 通过 |
| 3 | 输入无效 document | 缺失 summary | validation 返回 invalid | `test_validate_document_payload_rejects_missing_summary` 覆盖 | 通过 |
| 4 | 输入不安全代码路径 | `../` 或空步骤 | validation 拒绝 unsafe path 和 empty steps | `test_validate_coding_practice_payload_rejects_unsafe_path_and_empty_steps` 覆盖 | 通过 |
| 5 | 输入无效 PPT | 空 slides 或缺字段 | PPT 标记 invalid，manifest 记录错误 | `test_generate_ppt_marks_invalid_when_schema_validation_fails` 覆盖 | 通过 |

#### 2.4.2 测试结果综合分析及建议

资源生成模块单元测试覆盖成功生成、列表详情、渲染包装和失败校验。测试对前端预览很有价值，因为它不仅断言文件存在，还断言 detail 返回 `content` 和 `render`。

建议后续在前端测试中复用这些资源 manifest 样本，验证实际页面能打开文档、PPT、测验和思维导图详情。

#### 2.4.3 测试经验总结

资源生成的单元测试需要同时覆盖 ready 与 invalid 两类状态。对于生成式模块，失败结果只要结构化、可定位、可展示，就比静默失败或返回空白页面更符合工程质量要求。

### 2.5 学习成长树模块

#### 2.5.1 测试用例与结果分析

##### 单元测试用例 UT-02-015：学生学习 payload 生成成长树

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-015 |
| 测试单元描述 | 学生学习 payload 到成长树变更、manifest、features 的本地闭环 |
| 用例目的 | 验证系统能根据学习行为构建知识节点、边和可展示学习成长树 |
| 前提条件 | study graph 临时 artifacts 目录可写 |
| 特殊的规程说明 | 单元测试不调用真实 Student Agent、LLM 和搜索 |
| 用例间的依赖关系 | 为功能测试“查看学习成长树”提供模块依据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 构造学生学习 payload | HBase RowKey、热点、预分区、散列前缀等记录 | 生成 change candidates | `test_student_payload_round_trip_builds_changes_and_tree` 覆盖 | 通过 |
| 2 | 提交成长树变更 | changes | 返回 `success=True` | 测试断言 submit_result success | 通过 |
| 3 | 读取成长树 | user_id、syllabus_id | 标题为“大数据概论学习成长树” | 测试断言 tree title、virtual root | 通过 |
| 4 | 检查节点边 | manifest | 4 个节点、3 条边，父子关系正确 | 测试断言节点包含 RowKey 热点等 | 通过 |
| 5 | 读取 features | features 请求 | learned_topics 包含关键主题 | 测试断言 learned_topics | 通过 |

##### 单元测试用例 UT-02-016：成长树重复变更与合并

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-016 |
| 测试单元描述 | 成长树变更去重、重复 client_change_id 跳过和掌握度合并 |
| 用例目的 | 验证重复上报不会产生重复日志，同一节点后续学习能累积 mastery |
| 前提条件 | 已存在成长树或可初始化成长树 |
| 特殊的规程说明 | 去重依据 client_change_id；合并时保留 first_seen_at 并更新 last_updated_at |
| 用例间的依赖关系 | 与 UT-02-015 共同覆盖成长树写入质量 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 提交相同 client_change_id | duplicate change | 第二次提交结果为 skipped | `test_submit_learning_tree_changes_skips_duplicate_client_change_id` 覆盖 | 通过 |
| 2 | 检查 change_log | change_log.jsonl | 日志只保留一条 | 测试断言 log_lines 长度为 1 | 通过 |
| 3 | 提交同一知识点新学习记录 | same topic with new mastery | 结果为 merged | `test_submit_learning_tree_changes_merge_preserves_first_seen_and_accumulates_mastery` 覆盖 | 通过 |
| 4 | 检查时间和 mastery | node | first_seen_at 保持，last_updated_at 更新，score 增加 | 测试逐项断言 | 通过 |

#### 2.5.2 测试结果综合分析及建议

学习成长树单元测试覆盖了 payload 转换、树读取、特征读取、变更去重和掌握度合并。该模块的本地闭环较完整，能够支持前端成长树展示和 Total Agent 读取弱点信号。

建议后续增加前端局部刷新测试，验证成长树更新后页面节点状态、边和统计摘要同步刷新。

#### 2.5.3 测试经验总结

成长树测试需要关注“同一个知识点多次出现”的合并语义。简单追加节点会造成成长树膨胀，必须通过去重和合并保持学习轨迹可读。

### 2.6 教学内容与运维支撑模块

#### 2.6.1 测试用例与结果分析

##### 单元测试用例 UT-02-017：教学文件上传安全

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-017 |
| 测试单元描述 | 日历/教学文件上传时的唯一路径生成和清理安全 |
| 用例目的 | 验证上传文件不会覆盖已有文件，清理逻辑只删除本次创建且未引用的文件 |
| 前提条件 | 临时文件目录可写；mock repository 可用 |
| 特殊的规程说明 | 文件测试必须避免删除真实项目数据 |
| 用例间的依赖关系 | 为管理员文件上传功能提供安全依据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 上传同名文件 | 已存在 original_path | 生成唯一新路径，不覆盖旧文件 | `test_calendar_upload_uses_unique_path_when_original_exists` 覆盖 | 通过 |
| 2 | 无 bytes 时复制已有源文件 | source path | 复制到唯一路径，旧文件不变 | `test_calendar_upload_without_bytes_copies_existing_source_to_unique_path` 覆盖 | 通过 |
| 3 | 清理未引用文件 | uploaded_path | 只删除本次创建且未引用文件 | `test_calendar_cleanup_only_deletes_created_unreferenced_file` 覆盖 | 通过 |
| 4 | 清理复用文件 | reused path | 不删除已有复用文件 | `test_calendar_cleanup_skips_reused_file` 覆盖 | 通过 |

##### 单元测试用例 UT-02-018：教学大纲更新与 JobChecker

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-018 |
| 测试单元描述 | 教学大纲 JSON 替换、day_one 持久化和 JobChecker 启动图同步 |
| 用例目的 | 验证管理员教学内容维护和后台任务启动逻辑 |
| 前提条件 | syllabus JSON payload 可用；JobChecker 配置可用 |
| 特殊的规程说明 | 大纲更新需保证文件内容和数据库字段一致 |
| 用例间的依赖关系 | 与管理员教学大纲管理、Job 管理功能相关 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 更新教学大纲 JSON | new_syllabus payload | 替换文件并持久化 day_one | `test_update_syllabus_json_replaces_file_and_persists_day_one` 覆盖 | 通过 |
| 2 | 检查 day_one | `2026-03-02` | 数据库保存日期字段 | 测试断言 day_one 格式 | 通过 |
| 3 | 启动 JobChecker | startup graph sync | 图同步逻辑可被触发 | `test_job_checker_startup_graph_sync.py` 覆盖 | 通过 |
| 4 | 检查异常隔离 | mock 环境 | 不污染真实图谱和正式大纲 | 测试使用 monkeypatch/fixture 隔离 | 通过 |

#### 2.6.2 测试结果综合分析及建议

教学内容与运维支撑模块的单元测试重点验证文件安全、教学大纲持久化和后台 Job 启动。文件路径安全测试对管理员上传功能尤其重要，可以降低覆盖旧文件和误删真实文件的风险。

建议后续补充非法文件类型、超大文件、重复 Job 启动和图谱服务不可用等异常测试。

#### 2.6.3 测试经验总结

运维支撑模块的测试应优先保证“不污染真实数据”。涉及文件和 Job 的测试应使用临时目录、mock repository 和明确的清理断言。

### 2.7 Total Agent 上下文与资源策略模块

#### 2.7.1 测试用例与结果分析

##### 单元测试用例 UT-02-019：Total Agent 上下文加载与资源策略

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-019 |
| 测试单元描述 | Total Agent 读取 active plan、next task、画像摘要、成长树摘要并构建资源策略 |
| 用例目的 | 验证总调度在确定性测试中能正确区分无画像、持久化画像和当前计划状态 |
| 前提条件 | mock profile、mock study graph、mock resource result 可用 |
| 特殊的规程说明 | 本用例不访问真实 LLM/RAG/DB；资源生成通过 monkeypatch 隔离 |
| 用例间的依赖关系 | 与学习计划、画像和资源生成模块共同构成总调度基础 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 加载无画像上下文 | user_id、syllabus_id | profile_source=none，返回默认策略 | `tests/test_total_agent_task.py` 覆盖 | 通过 |
| 2 | 注入持久化画像 | persisted profile | profile_source=persisted_profile | `total_agent_deterministic_result.json` 记录两种对照场景 | 通过 |
| 3 | 构建资源策略 | 当前步骤、薄弱点、资源偏好 | resource_types 从默认 documents 调整为 documents + quiz 等 targeted 策略 | 测试产物记录 `difficulty=targeted` | 通过 |
| 4 | 调用资源生成入口 | generate_current_step_resource | 先构建 resource_strategy，再调用资源生成 | TEST_REPORT 记录边界 | 通过 |

##### 单元测试用例 UT-02-020：Total Agent 工具状态与流程契约

| 项目 | 内容 |
| --- | --- |
| 用例编号 | UT-02-020 |
| 测试单元描述 | Total Agent 工具调用流程、状态事件和前端可消费契约 |
| 用例目的 | 验证工具执行状态可用于前端展示，不影响业务结果 |
| 前提条件 | Total Agent process contract 测试样本可用 |
| 特殊的规程说明 | 状态事件用于观测，不应替代业务字段判断 |
| 用例间的依赖关系 | 前端 Agent 操作状态展示依赖本契约 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 执行 process contract 测试 | 工具状态事件 | 事件包含工具开始、完成、失败等状态 | `tests/total_agent/test_process_contract.py` 覆盖 | 通过 |
| 2 | 检查前端消费字段 | tool_status_events | 前端可展示工具名称、状态和时间 | TEST_REPORT 记录 SSE/stream 状态能力 | 通过 |
| 3 | 检查业务字段 | Agent 结果 | 工具状态不改变 plan/resource/profile 判断 | 单元测试按结构化结果断言 | 通过 |

#### 2.7.2 测试结果综合分析及建议

Total Agent 上下文与流程契约测试覆盖了当前系统最容易出现误判的区域。测试要求正式链路通过 learning_profile_task 读取真实持久化画像，读取失败时只返回空摘要和 warning，不在 runtime 内伪造 profile。

建议把“第一句话必须先加载当前上下文再做业务判断”的行为纳入后续 E2E 或提示词回归测试，但在单元层仍以结构化工具返回值为主。

#### 2.7.3 测试经验总结

Total Agent 测试的核心是控制历史上下文污染和状态误判。工具状态、对话文本和结构化业务状态必须分层验证，避免把展示层事件误当作业务事实。
