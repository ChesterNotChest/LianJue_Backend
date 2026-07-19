# 项目测试文档 - 功能测试

## 3 功能测试

### 3.1 学生学习路径推荐与计划执行功能

#### 3.1.1 测试用例与结果分析

本节依据学生端“生成学习路径推荐、查看推荐列表、查看推荐详情、采纳推荐路径、查看当前学习计划、提交学习反馈”的业务闭环组织功能测试。功能测试尽量使用现有 API、E2E 和计划生命周期测试作为依据。

##### 功能测试用例 FT-03-001：生成学习路径推荐

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-001 |
| 测试单元描述 | 学生用户输入学习目标后，系统生成学习路径推荐快照 |
| 用例目的 | 验证推荐接口能返回推荐图、候选路径、最佳路径和 proposed 快照 |
| 前提条件 | 学生用户存在；课程大纲存在；推荐服务可调用 |
| 特殊的规程说明 | 推荐结果是候选路径，不应直接变成 active plan |
| 用例间的依赖关系 | FT-03-002、FT-03-003、FT-03-004 依赖本用例返回的 recommendation_id 和 candidates |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用推荐接口 | `POST /api/personal_recommendation`，包含 user_id、syllabus_id、learning_goal | HTTP 200，`success=True` | `test_personal_recommendation_api_with_syllabus` 覆盖 | 对应用例图“生成学习路径推荐” |
| 2 | 检查推荐图 | API 返回 JSON | `graph.nodes`、`graph.edges` 为列表 | 测试断言图结构为 list | 通过 |
| 3 | 检查候选路径 | API 返回 JSON | `candidates` 为列表，`best_path` 存在 | 测试断言 candidates 和 best_path | 通过 |
| 4 | 检查快照状态 | API 返回 JSON | 返回 `recommendation_id`，`snapshot_status=proposed` | 测试断言 proposed 快照 | 通过 |

##### 功能测试用例 FT-03-002：查看推荐列表

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-002 |
| 测试单元描述 | 学生用户查看历史推荐快照列表 |
| 用例目的 | 验证系统能按用户和课程返回推荐列表，列表项保持轻量化 |
| 前提条件 | 已生成至少一个推荐快照 |
| 特殊的规程说明 | 查看列表不应触发重新推荐或 accept |
| 用例间的依赖关系 | 依赖 FT-03-001 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 请求推荐列表 | `GET /api/recommendations?user_id=12345&syllabus_id=29` | HTTP 200，`success=True` | `test_recommendation_snapshot_detail_and_list_api` 覆盖 | 对应用例图“查看推荐列表” |
| 2 | 检查列表内容 | 快照列表 | 返回 snapshots，包含 recommendation_id | 测试断言 snapshots[0].recommendation_id | 通过 |
| 3 | 检查列表轻量化 | snapshots[0] | 列表项不携带完整 recommendation | 测试断言 `"recommendation" not in snapshots[0]` | 防止列表过重 |

##### 功能测试用例 FT-03-003：查看推荐详情

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-003 |
| 测试单元描述 | 学生用户查看某个推荐快照的完整推荐详情 |
| 用例目的 | 验证推荐详情接口能返回推荐图、候选路径和候选路径详情 |
| 前提条件 | 已存在 recommendation_id |
| 特殊的规程说明 | 查看详情不得改变 snapshot_status |
| 用例间的依赖关系 | 依赖 FT-03-001 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 请求推荐详情 | `GET /api/recommendations/{recommendation_id}` | HTTP 200 | `test_recommendation_snapshot_detail_and_list_api` 覆盖 | 对应用例图“查看推荐详情” |
| 2 | 检查推荐内容 | detail JSON | `snapshot.recommendation.graph.nodes` 可读取 | 测试断言 graph node id | 通过 |
| 3 | 检查状态副作用 | recommendation_id | 快照仍为 proposed 或原状态 | 详情读取不触发 accept | 需在功能测试记录中确认 |

##### 功能测试用例 FT-03-004：采纳推荐路径

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-004 |
| 测试单元描述 | 学生用户从推荐快照中选择某条候选路径并创建学习计划 |
| 用例目的 | 验证系统按用户指定 candidate_index 创建学习计划，且不会重新生成推荐 |
| 前提条件 | 已存在 proposed recommendation snapshot；候选路径数量大于目标 candidate_index |
| 特殊的规程说明 | candidate_index 必须来自已有快照；按钮操作应直接传递 recommendation_id 与 candidate_index |
| 用例间的依赖关系 | 依赖 FT-03-001、FT-03-003；FT-03-005 依赖本用例创建的计划 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用 accept 接口 | `POST /api/recommendations/{recommendation_id}/accept`，candidate_index=1 | HTTP 200，`success=True` | `test_recommendation_snapshot_accept_api_creates_plan` 覆盖 | 对应用例图“采纳推荐路径” |
| 2 | 检查快照状态 | accept 返回 JSON | `snapshot_status=accepted` | 测试断言 accepted | 通过 |
| 3 | 检查被采纳候选编号 | accept 返回 JSON | `accepted_candidate_index=1` | 测试断言 candidate_index | 防止选错路径 |
| 4 | 检查学习计划步骤 | accept 返回 steps | steps 来自该候选路径 | 测试断言 node_id 为 `["n1", "n3"]` | 通过 |

##### 功能测试用例 FT-03-005：查看并推进当前学习计划

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-005 |
| 测试单元描述 | 学生用户查看当前学习计划，并通过反馈推进学习步骤 |
| 用例目的 | 验证 active plan 查询、当前步骤识别、反馈后步骤推进和计划完成 |
| 前提条件 | 已通过 FT-03-004 创建 active plan |
| 特殊的规程说明 | 无 active plan 时必须返回无计划，不得读取旧候选推荐充当计划 |
| 用例间的依赖关系 | 依赖 FT-03-004；影响 FT-03-011 成长树更新 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 查询 active plan | user_id、syllabus_id | 返回 active plan，首步骤 active | `test_plan_accept_creates_active_plan` 覆盖 | 对应用例图“查看当前学习计划” |
| 2 | 提交学习反馈 | active step 完成反馈 | 当前步骤 completed | `test_step_completion_updates_status` 覆盖 | 对应学习反馈推进 |
| 3 | 查询下一步 | plan_id | 下一步骤 active | 测试断言第 2 步激活 | 通过 |
| 4 | 完成最后一步 | last step feedback | plan completed，active 查询为空 | `test_plan_auto_completes_on_last_step` 覆盖 | 前端应停止展示计划卡片 |
| 5 | 放弃计划 | abandon reason | plan abandoned，active 查询为空 | `test_plan_abandon` 覆盖 | 支持用户主动放弃 |

#### 3.1.2 测试结果综合分析及建议

学生学习路径功能已有明确的 API 和状态机测试支撑。推荐生成、推荐列表、推荐详情和推荐采纳分别对应不同接口，能够形成“生成推荐网 -> 选择某个具体路径 -> 开展计划”的链路。当前最需要在功能验收中强调的是：查看推荐详情不等于采纳，采纳时必须基于已有 recommendation snapshot，不能重新调用推荐 Agent。

建议在人工验收时补充自然语言“第三条”和按钮选择第 3 条的对照测试，确认两种入口最终都携带明确 candidate_index。

#### 3.1.3 测试经验总结

该功能的测试必须围绕 recommendation_id、candidate_index、plan_id 和 step status 展开。只看 Agent 的中文回复容易漏掉实际状态错位。

### 3.2 学习资源生成与查看功能

#### 3.2.1 测试用例与结果分析

本节依据“生成学习资源、查看资源列表、查看资源详情”组织功能测试。测试内容来自资源生成 task、manifest list/detail 包装和真实 Agent + Search 验收入口。

##### 功能测试用例 FT-03-006：生成多类型学习资源

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-006 |
| 测试单元描述 | 学生用户请求生成 documents、mindmap、quiz、coding_practice、ppt 等学习资源 |
| 用例目的 | 验证资源生成链路能完成 planning、search、LLM 生成、校验、渲染和落盘 |
| 前提条件 | 当前学习任务明确；资源生成工作区可写；真实验收时 RAG 图谱可用 |
| 特殊的规程说明 | 默认回归可使用 mock；发布前可启用 `RUN_LLM_TESTS=1 RUN_SEARCH_TESTS=1` |
| 用例间的依赖关系 | FT-03-007、FT-03-008 依赖本用例生成资源 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 提交资源生成请求 | topic=HBase RowKey 热点规避，resource_types 多类型 | 资源生成任务开始 | `test_generate_resource_full_user_chain_persists_all_resource_types` 覆盖 | 对应用例图“生成学习资源” |
| 2 | 检查生成结果 | 五类资源请求 | 每个资源 `success=True`、`status=ready` | 测试断言全部 ready | 通过 |
| 3 | 检查 manifest | manifest.json | `resource_count=5` | 测试断言 resource_count | 通过 |
| 4 | 真实 Agent + Search 验收 | documents、mindmap、quiz | failed_results 为空，检索 query 包含 RowKey | `test_real_rag_generative_agent_creates_personalized_resource` 覆盖 | opt-in |

##### 功能测试用例 FT-03-007：查看资源列表

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-007 |
| 测试单元描述 | 学生用户查看已生成资源列表 |
| 用例目的 | 验证资源列表能按用户、课程、类型和生成时间返回资源摘要 |
| 前提条件 | manifest 中已有资源记录 |
| 特殊的规程说明 | 查看列表不得触发重新生成 |
| 用例间的依赖关系 | 依赖 FT-03-006 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 请求资源列表 | user_id、syllabus_id | 返回资源列表 | `test_list_generated_resources_filters_and_sorts` 覆盖 | 对应用例图“查看资源列表” |
| 2 | 按类型分组 | resource_types、limit | mindmap、quiz 等分组正确 | `test_list_generated_resources_by_type_applies_limit` 覆盖 | 通过 |
| 3 | 检查排序 | 多条 manifest 记录 | 最新资源优先 | 测试断言资源 ID 顺序 | 通过 |

##### 功能测试用例 FT-03-008：查看资源详情

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-008 |
| 测试单元描述 | 学生用户从资源列表进入资源详情页 |
| 用例目的 | 验证资源详情接口能返回前端可渲染的 content 和 render |
| 前提条件 | 资源文件存在；manifest 中记录 repo-relative 路径 |
| 特殊的规程说明 | 文件缺失或 validation invalid 时应返回明确状态，不能空白成功 |
| 用例间的依赖关系 | 依赖 FT-03-007 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 请求资源详情 | resource_id、resource_type | 返回 detail | `test_get_generated_resource_detail_resolves_repo_relative_paths` 覆盖 | 对应用例图“查看资源详情” |
| 2 | 检查正文内容 | detail JSON | `content` 可读取 | 测试断言 content title | 通过 |
| 3 | 检查渲染包装 | quiz 或 documents | `render.markdown` 存在 | `test_get_generated_resource_detail_returns_render_ready_wrapper` 覆盖 | 支撑前端预览 |

#### 3.2.2 测试结果综合分析及建议

资源功能测试已有明确的生成、列表、详情三段式测试来源。后续前端验收应把“后端资源 ready”和“前端预览可见”分开记录，尤其是 PPT、思维导图和图谱类资源。

#### 3.2.3 测试经验总结

资源功能的验收不能只看资源是否生成，还要检查 manifest、detail、render 和前端展示。对于 invalid 资源，系统应能展示错误原因，而不是隐藏失败。

### 3.3 学习画像与成长树功能

#### 3.3.1 测试用例与结果分析

本节依据“查看个人学习大纲、查看学习成长树、与自演化学生学伴交互”组织功能测试，同时引用画像 detail/refresh 和成长树 payload flow 测试。

##### 功能测试用例 FT-03-009：查看和刷新学习画像

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-009 |
| 测试单元描述 | 学生用户查看画像详情，必要时刷新画像 |
| 用例目的 | 验证画像详情读取和画像刷新职责分离 |
| 前提条件 | 学生已绑定课程；画像文件存在或可由刷新接口生成 |
| 特殊的规程说明 | detail 不隐式刷新；refresh 才调用画像构建链路 |
| 用例间的依赖关系 | 为推荐、资源策略和学伴交互提供画像上下文 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 查看画像详情 | `POST /api/learning_profile_detail` | HTTP 200，`profile_saved=True` | `test_learning_profile_detail_api_reads_persisted_profile_only` 覆盖 | 画像展示 |
| 2 | 检查未刷新 | detail 响应 | `profile_refreshed=False` | 测试断言字段 | 防止查看即重算 |
| 3 | 刷新画像 | `POST /api/learning_profile_refresh` | HTTP 200，`profile_refreshed=True` | `test_learning_profile_refresh_api_calls_build_learning_profile` 覆盖 | 画像更新 |
| 4 | 缺失参数 | 缺 user_id 或 syllabus_id | HTTP 400，`error_code=missing_fields` | 对应 API 参数测试 | 通过 |

##### 功能测试用例 FT-03-010：查看个人学习大纲

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-010 |
| 测试单元描述 | 学生用户查看基于课程大纲初始化的个人学习大纲 |
| 用例目的 | 验证系统能够读取课程大纲 fixture，初始化个人大纲并回写路径 |
| 前提条件 | 学生已绑定课程；`tests/fixtures/大数据概论_20260322235507.json` 可用 |
| 特殊的规程说明 | 个人大纲初始化属于画像全链路的一部分，正式展示应读取持久化路径 |
| 用例间的依赖关系 | 与 FT-03-009 画像刷新相关 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 构建画像全链路 | user_id、syllabus_id、画像输入 | 初始化个人大纲 | `test_profile_personal_syllabus_full_chain.py` 覆盖 | 对应用例图“查看个人学习大纲” |
| 2 | 读取 syllabus fixture | 大数据概论大纲 | 初始化 16 周个人大纲 | TEST_REPORT 记录该行为 | 通过 |
| 3 | 检查回写路径 | UserSyllabus | `personal_syllabus_path`、`personal_profile_path` 回写 | 测试说明记录回写 | 通过 |

##### 功能测试用例 FT-03-011：查看学习成长树

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-011 |
| 测试单元描述 | 学生用户查看学习成长树和学习特征摘要 |
| 用例目的 | 验证成长树能展示知识节点、父子边、学习主题和虚拟根 |
| 前提条件 | 学生成长树 manifest 已存在或可由 payload 初始化 |
| 特殊的规程说明 | 总览接口仅读不写，不应创建学习树或计划数据 |
| 用例间的依赖关系 | 可由 FT-03-005 学习反馈同步更新 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 提交学习 payload | RowKey 热点、预分区策略等学习记录 | 生成成长树变更 | `test_student_payload_round_trip_builds_changes_and_tree` 覆盖 | 对应用例图“查看学习成长树” |
| 2 | 读取成长树 | user_id、syllabus_id | 返回“大数据概论学习成长树” | 测试断言 tree title | 通过 |
| 3 | 检查节点边 | tree manifest | 包含 4 个节点和 3 条边 | 测试断言节点和父子关系 | 通过 |
| 4 | 读取 detail API | `/api/study_graph/detail` | syllabus_id 可选，仅读不写 | `tests/test_study_graph_api.py` 覆盖 | API 展示 |

##### 功能测试用例 FT-03-012：与自演化学生学伴交互

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-012 |
| 测试单元描述 | 学生用户基于当前计划、画像和成长树进行即时问答或学习支持交互 |
| 用例目的 | 验证学伴交互能读取上下文并回答学习问题，同时不误推进计划 |
| 前提条件 | 学生存在深状态夹具：画像、学习树、active plan 和当前资源 |
| 特殊的规程说明 | 即时答疑场景不应生成资源、不应推进计划、不应写 feedback |
| 用例间的依赖关系 | 依赖画像、成长树和当前计划上下文 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 用户提出学习问题 | deep-state fixture + 学习问题 | Total Agent 识别为 answer_learning_question | `test_total_agent_e2e_answer_learning_question_learning_strategy` 覆盖 | 对应用例图“与自演化学生学伴交互” |
| 2 | 读取上下文 | profile、study graph、active plan、current resources | 回复利用 active plan、next task、weak points | TEST_REPORT 记录 E2E 收口矩阵 | 通过 |
| 3 | 检查副作用 | 即时答疑结果 | 不推进 active plan，不生成资源，不写 feedback | E2E 场景说明明确断言 | 通过 |

#### 3.3.2 测试结果综合分析及建议

画像、个人大纲、成长树和学伴交互均已有可引用的测试入口。该部分功能验收的重点是共享上下文是否一致：同一 user_id/syllabus_id 下的画像、个人大纲、成长树和当前计划应相互匹配。

建议后续增加前端刷新测试，验证画像刷新、成长树变更、计划推进后页面状态同步更新。

#### 3.3.3 测试经验总结

个性化功能测试应区分“读取上下文”和“写入状态”。学伴即时答疑通常只读上下文，不应误写计划或反馈；只有用户明确选择路径、提交反馈或请求资源时，才应进入写操作。

### 3.4 管理端教学内容与运维功能

#### 3.4.1 测试用例与结果分析

本节依据管理员用例组织功能测试，覆盖上传/查看文件、教学大纲管理、图谱与 Job 管理、totalAgent 定义与运行状态查看。

##### 功能测试用例 FT-03-013：上传并查看下载文件

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-013 |
| 测试单元描述 | 管理员上传教学文件并查看下载入口 |
| 用例目的 | 验证文件上传不会覆盖已有文件，下载读取能定位正确文件 |
| 前提条件 | 管理员已登录；文件目录可写 |
| 特殊的规程说明 | 文件路径必须经过安全处理，测试不允许污染真实数据 |
| 用例间的依赖关系 | 教学大纲生成和教学材料发布可依赖上传文件 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 上传同名文件 | calendar file | 生成唯一文件路径，不覆盖原文件 | `test_calendar_upload_uses_unique_path_when_original_exists` 覆盖 | 对应用例图“上传文件” |
| 2 | 从已有源文件复制上传 | source path | 复制到唯一新路径 | `test_calendar_upload_without_bytes_copies_existing_source_to_unique_path` 覆盖 | 通过 |
| 3 | 查看下载文件 | file_id 或 path | 能读取上传文件内容 | 文件安全测试保留 path 断言 | 对应用例图“查看下载文件” |
| 4 | 清理文件 | unreferenced uploaded file | 只删除本次创建未引用文件 | cleanup 测试覆盖 | 防止误删 |

##### 功能测试用例 FT-03-014：教学大纲管理

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-014 |
| 测试单元描述 | 管理员创建、构建、更新和发布教学大纲 |
| 用例目的 | 验证教学大纲文件、数据库记录和 day_one 字段保持一致 |
| 前提条件 | 管理员已登录；大纲 JSON payload 可用；数据库连接可用 |
| 特殊的规程说明 | 草稿和终稿状态应分离；更新大纲不应破坏已绑定学生数据 |
| 用例间的依赖关系 | 学生个人大纲、推荐路径和资源生成依赖大纲数据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 创建大纲草稿 | draft payload | 草稿 JSON 写入 | `test_create_syllabus_draft.py` 覆盖 | 对应用例图“教学大纲管理” |
| 2 | 构建正式大纲 | draft 或课程文件 | 正式 syllabus 生成 | `test_build_syllabus.py` 覆盖 | 通过 |
| 3 | 更新大纲 | new_syllabus JSON，day_one=2026-03-02 | 文件替换，day_one 持久化 | `test_update_syllabus_json_replaces_file_and_persists_day_one` 覆盖 | 通过 |
| 4 | 更新草稿或发布材料 | draft/final 状态 | 状态和文件一致 | `test_update_syllabus_draft.py`、`test_update_syllabus.py` 覆盖 | 对应用例图“发布教学材料草稿/终稿” |

##### 功能测试用例 FT-03-015：查看图谱列表并创建图谱

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-015 |
| 测试单元描述 | 管理员查看图谱列表、创建图谱并为 RAG/推荐提供图谱基础 |
| 用例目的 | 验证图谱管理能力可支撑后续检索和推荐 |
| 前提条件 | 管理员已登录；图数据库服务可用 |
| 特殊的规程说明 | 创建图谱需检查名称冲突和服务可用性 |
| 用例间的依赖关系 | RAG、推荐路径、资源生成依赖图谱 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 查看图谱列表 | 管理员身份 | 返回图谱名称、状态和可用性 | RAG/KnowLion 相关测试使用 graph_name=RAG | 对应用例图“查看图谱列表” |
| 2 | 创建图谱 | graph_name、数据源 | 图谱创建或返回明确错误 | 现有测试主要通过 RAG/资源生成间接覆盖 | 对应用例图“创建图谱” |
| 3 | 检索联动 | graph_name=RAG | search tool 能返回结构化结果 | `tests/test_search_tool.py`、资源生成真实 Search 覆盖 | 间接验证 |

##### 功能测试用例 FT-03-016：Job 管理与 totalAgent 运行状态查看

| 项目 | 内容 |
| --- | --- |
| 用例编号 | FT-03-016 |
| 测试单元描述 | 管理员启动 JobChecker、查看 totalAgent 定义和 SSE 运行状态 |
| 用例目的 | 验证后台运维入口和 Agent 状态可观测性 |
| 前提条件 | 管理员已登录；JobChecker 配置存在；Total Agent 可运行 |
| 特殊的规程说明 | Job 重复启动应幂等或返回明确状态；SSE 只用于状态展示 |
| 用例间的依赖关系 | 前端 Agent 操作状态展示依赖 totalAgent 状态事件 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 启动 JobChecker | Job 启动请求 | JobChecker 启动或返回已运行状态 | `test_job_checker_startup_graph_sync.py` 覆盖 | 对应用例图“Job管理/启动服务JobChecker” |
| 2 | 查看 totalAgent 定义 | 管理员请求 | 返回 Agent 定义和工具配置摘要 | TEST_REPORT 记录 Total Agent 测试入口 | 对应用例图“查看totalAgent定义” |
| 3 | 启动流式运行 | `stream=True` 或 SSE 入口 | 前端可接收工具状态事件 | TEST_REPORT 记录 `run_total_agent_stream()` 和 SSE 能力 | 对应用例图“totalAgent同步/SSE运行” |
| 4 | 检查状态与业务分离 | tool_status_events + 业务结果 | 状态事件不替代业务字段判断 | process contract 测试覆盖 | 通过 |

#### 3.4.2 测试结果综合分析及建议

管理端功能测试中，教学大纲和文件上传已有较明确的测试依据；图谱创建目前更多通过 RAG、search tool 和资源生成真实检索链路间接覆盖。若后续要形成更完整的管理端验收，应补充独立的图谱创建 API 测试、管理员权限测试和异常文件类型测试。

#### 3.4.3 测试经验总结

管理端测试的重点是“维护操作不污染主数据”。教学文件、教学大纲和 Job 操作会影响学生端推荐、资源生成和图谱检索，因此测试中必须使用隔离路径、临时数据和明确的清理策略。
