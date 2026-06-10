# 2 需求分析

本章采用可追踪需求模型描述系统需求。需求编号分为四类：

| 前缀 | 名称 | 含义 |
| --- | --- | --- |
| RR | Rule Requirement | 规则、约束、安全、边界类需求 |
| IR | Interface Requirement | 外部接口、内部接口、数据交换类需求 |
| SF | System Function | 系统功能需求 |
| US | User Story | 用户故事或业务用例需求 |

用例编号使用 `UC-xxx`。每个核心用例都应能追踪到一个或多个 `SF / IR / RR / US`。

## 2.1 用户角色与业务场景

### 2.1.1 用户角色

| 角色 | 说明 | 核心诉求 |
| --- | --- | --- |
| 学生 | 系统主要使用者 | 获得个性化路径、学习资源、即时答疑和学习反馈 |
| 教师 | 课程组织者和学习观察者 | 了解学生薄弱点、课程共性问题和学习进度 |
| 平台管理员 | 系统维护者 | 管理课程、用户、知识库、模型配置和运行状态 |
| 前端应用 | 后端能力消费方 | 展示学习流程、资源、答疑结果和多 Agent 状态 |
| 外部模型/RAG 服务 | 智能能力提供方 | 提供文本理解、生成、检索和证据支持 |

### 2.1.2 主要业务场景

| 编号 | 场景 | 简述 |
| --- | --- | --- |
| US-001 | 学生输入学习目标并获得学习路径 | 学生以自然语言提出目标，系统读取画像和课程结构，推荐学习路径 |
| US-002 | 学生接受学习计划并开始当前步骤 | 学生确认推荐路径后，系统落盘 active plan 并激活 next task |
| US-003 | 学生生成当前步骤学习资源 | 系统根据当前 step、知识点和画像偏好生成学习资源 |
| US-004 | 学生进行即时学习答疑 | 学生提出概念、策略或练习问题，系统返回结构化回答 |
| US-005 | 学生提交学习反馈并更新状态 | 学生完成资源或练习后提交反馈，系统推进计划并同步成长树 |
| US-006 | 前端展示多 Agent 工作过程 | 前端消费 `tool_status_events` 展示画像、推荐、生成、答疑、成长树同步状态 |

## 2.2 数据需求

系统需要处理静态课程数据、学生动态学习数据、生成资源数据、Agent 运行状态和外部知识库证据。

### 2.2.1 静态数据

| 编号 | 数据项 | 说明 | 来源 |
| --- | --- | --- | --- |
| D-001 | 课程大纲 | 课程章节、周次、知识点、学习目标 | 数据库或课程 JSON |
| D-002 | 初始知识库文档 | 支持 RAG 检索的课程资料、文档、讲义 | KnowLion/RAG 图谱 |
| D-003 | 系统配置 | 模型配置、RAG 配置、数据库配置、路径配置 | `config.json` / 环境变量 |
| D-004 | 资源类型配置 | documents、mindmap、quiz、coding_practice、ppt | 代码常量 |
| D-005 | 测试 fixtures | E2E 和模块测试所需 mock 数据 | `tests/` |

### 2.2.2 动态数据

| 编号 | 数据项 | 说明 | 持久化位置 |
| --- | --- | --- | --- |
| D-101 | 用户消息 | 学习目标、问题、反馈 | API 请求 / 历史记录 |
| D-102 | 学习画像 | 目标、薄弱点、资源偏好、风险信号 | Learning Profile 持久化 |
| D-103 | 个性化学习计划 | active plan、steps、next task、step 状态 | 生产默认数据库；测试/离线可用 learning plan manifest |
| D-104 | 生成资源 | 文档、题库、思维导图、编程练习、PPT 等 | 生产默认数据库 metadata + 文件对象；测试/离线可用 resource manifest / 文件 |
| D-105 | 学生成长树 | 已触达知识节点、父子边、掌握状态 | 生产默认数据库；测试/离线可用 `study_graph/.../manifest.json` |
| D-106 | 成长树 change log | 变更请求、裁决结果、时间戳 | 生产默认数据库事件表；测试/离线可用 `change_log.jsonl` |
| D-107 | Agent 状态事件 | 工具运行过程、成功失败、错误信息 | `tool_status_events` |
| D-108 | RAG 证据摘要 | 检索结果标题、摘要、相关性、warning | 运行时结果 |

### 2.2.3 数据词典

| 字段 | 类型 | 说明 | 约束 |
| --- | --- | --- | --- |
| `user_id` | int | 用户 ID | 必须为正整数 |
| `syllabus_id` | int | 课程/大纲 ID | 推荐必填；部分读取场景可为空 |
| `message` | string | 用户自然语言输入 | 非空时用于意图识别 |
| `learning_goal` | string | 学习目标 | 可从 message 或 profile 中提取 |
| `profile_summary` | object | 学习画像摘要 | 包含 weak_points、preferred_formats 等 |
| `active_plan` | object | 当前学习计划 | 包含 plan_id、steps |
| `next_task` | object | 当前或下一学习步骤 | 策略问答和资源生成优先使用 |
| `resource_type` | string | 资源类型 | documents / mindmap / quiz / coding_practice / ppt |
| `study_graph_state` | object | 成长树摘要状态 | weak/mastered/stale/recent 节点 |
| `question_type` | string | 即时答疑问题类型 | concept_explanation / learning_strategy / exercise_help / unknown |
| `tool_status_events` | list | Agent 状态事件 | 前端状态展示使用 |
| `warnings` | list | 结构化 warning | 低相关证据、过滤画像弱点等 |

### 2.2.4 数据采集

数据采集方式包括：

- 用户主动输入学习目标、问题和学习反馈。
- 系统读取历史学习计划、资源使用记录和成长树。
- RAG 检索课程知识库和外部文档片段。
- 资源生成和答疑过程中生成结构化结果。
- 学习反馈同步到 learning plan 和 Study Graph。

## 2.3 功能需求

### 2.3.1 系统功能需求总表

| 编号 | 功能名称 | 描述 | 优先级 | 当前状态 |
| --- | --- | --- | --- | --- |
| SF-001 | 学习画像构建与读取 | 从用户目标、历史事件和课程上下文中构建或读取画像 | 高 | 已实现后端闭环 |
| SF-002 | 个性化路径推荐 | 根据画像、课程结构、RAG 和学习状态生成候选路径 | 高 | 已实现后端闭环 |
| SF-003 | 学习计划接受与激活 | 用户确认路径后落盘 active plan 并激活 next task | 高 | 已实现后端闭环 |
| SF-004 | 当前步骤资源生成 | 根据 next task 生成 documents、quiz、mindmap、coding_practice、ppt | 高 | 已实现后端闭环 |
| SF-005 | 即时学习答疑 | 支持概念解释、学习策略、练习帮助，返回结构化 answer payload | 高 | 已实现后端闭环 |
| SF-006 | 学习反馈记录 | 记录资源完成、得分、错题、跳过等学习反馈 | 高 | 已实现后端闭环 |
| SF-007 | 成长树同步 | 将真实触达的学习事件同步为成长树节点和掌握状态 | 高 | 已实现后端闭环 |
| SF-008 | 课程聚合弱点摘要 | 提供课程/班级层面的聚合 weak signal | 中 | 已实现后端只读能力 |
| SF-009 | 多 Agent 状态展示支持 | 输出 `tool_trace` 和 `tool_status_events` 供前端展示 | 高 | 已实现后端事件 |
| SF-010 | 生产级学习工作台 | 前端展示路径、资源、答疑、成长树和状态流 | 高 | 待补前端升级 |

### 2.3.2 规则与约束需求

| 编号 | 规则 | 描述 | 关联模块 |
| --- | --- | --- | --- |
| RR-001 | 内容安全与防幻觉 | RAG 低相关时必须 warning，不伪装成高质量证据 | QA / RAG |
| RR-002 | QA 不改变学习状态 | 即时答疑不生成资源、不推进 plan、不写 feedback | Total Agent |
| RR-003 | 推荐不写成长树 | 推荐结果只有被真实触达后才进入 Study Graph | Recommendation / Study Graph |
| RR-004 | 成长树只记录真实触达节点 | 不提前铺满完整课程地图，不展示 locked 节点 | Study Graph |
| RR-005 | 结构化输出校验 | answer payload、resource payload 必须 normalize / validate | Total Agent / Resource |
| RR-006 | 用户课程隔离 | 画像、计划、资源、成长树按 `user_id + syllabus_id` 隔离 | 全系统 |
| RR-007 | 聚合隐私边界 | 课程聚合摘要不输出其他学生明细 | Study Graph |
| RR-008 | 文档事实源 | 模块事实以 dev doc 和当前代码为准 | 工程维护 |
| RR-009 | 生产持久化数据库化 | 学习计划、资源 metadata、成长树和事件日志生产默认写入数据库；文件 manifest 只作为测试 fixture、离线运行或显式文件后端 | 数据层 |

### 2.3.3 接口需求

| 编号 | 接口需求 | 描述 | 消费方 |
| --- | --- | --- | --- |
| IR-001 | Total Agent 统一入口 | 前端通过统一 payload 调用学习目标、资源、答疑和反馈闭环 | 前端 |
| IR-002 | 结构化 Agent 结果 | 返回 success、intent、result、tool_trace、tool_status_events、suggested_next_action | 前端 |
| IR-003 | 即时答疑 payload | 返回 question_type、text、key_points、next_actions、warnings 等字段 | 前端 |
| IR-004 | 资源生成结果 | 返回 resource_type、resource payload、metadata、persisted resource | 前端 |
| IR-005 | 成长树读取接口 | 返回完整 tree 和 features bundle | 前端 / Total Agent |
| IR-006 | 模型服务接口 | 通过 OpenAI-compatible provider 调用 LLM | 后端 |
| IR-007 | RAG 检索接口 | 通过 search_tool 检索课程知识库证据 | 后端 |
| IR-008 | 状态事件接口 | 以 `tool_status_events` 支持进度展示和错误定位 | 前端 |

## 2.4 非功能需求

### 2.4.1 性能需求

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| NFR-001 | 即时答疑响应可展示 | 即时答疑应优先返回结构化答案，支持前端快速渲染 |
| NFR-002 | 资源生成可追踪 | 资源生成耗时较长时必须有状态事件或进度展示 |
| NFR-003 | 默认测试快速 | 不依赖真实 LLM / RAG / DB 的测试应作为默认回归 |
| NFR-004 | opt-in 测试真实 | 真实 LLM / RAG / DB 通过环境变量开启 |

### 2.4.2 适应性需求

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| NFR-101 | 多课程适配 | 支持不同 `syllabus_id` 的课程上下文 |
| NFR-102 | 多用户隔离 | 支持不同用户独立画像、计划、资源和成长树 |
| NFR-103 | RAG 降级 | 无证据或低相关证据时继续给出可解释降级 |
| NFR-104 | 无计划降级 | 无 active plan 时引导确认学习目标或生成路径 |

### 2.4.3 可维护性需求

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| NFR-201 | 模块事实源统一 | dev doc 是模块唯一事实源 |
| NFR-202 | E2E 入口统一 | Total Agent E2E 统一在 `tests/total_agent/test_total_agent_e2e.py` |
| NFR-203 | 结构化测试 | 关键结果字段可被测试断言 |
| NFR-204 | 文档与代码同步 | 旧 small plan / contract 的有效内容融合进 dev doc 后删除 |

## 2.5 界面需求

前端需要展示的不只是文本回答，还包括学习流程和系统状态。

界面需求：

- UI-001：展示当前学习目标、active plan、next task 和进度。
- UI-002：展示资源卡片和生成状态。
- UI-003：展示答疑结构化结果：`text`、`key_points`、`next_actions`、`warnings`。
- UI-004：展示 Agent 状态流：画像读取、推荐、资源生成、答疑、反馈、成长树同步。
- UI-005：展示成长树节点状态：薄弱、成长、稳定、掌握。
- UI-006：展示降级状态：低相关 RAG、无 active plan、生成失败、同步 warning。

待补图：主学习工作台线框图。

## 2.6 用例规约

### 2.6.1 UC-001 构建或读取学习画像

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 构建或读取学习画像 |
| 功能简述 | 系统根据用户、课程、历史学习事件和学习目标读取或构建学生画像。 |
| 用例编号 | UC-001 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、Learning Profile 模块 |
| 前置条件 | 用户已登录；存在 `user_id`；推荐存在 `syllabus_id`；系统可读取历史学习上下文。 |
| 后置条件 | 返回 `profile_summary`；若已有画像则优先读取；若允许构建则生成或更新画像。 |
| 涉众利益 | 学生获得个性化推荐基础；推荐和资源生成获得学生状态；教师可理解学生薄弱点。 |
| 基本路径 | 1. 用户输入学习目标或进入学习流程；2. Total Agent 请求上下文；3. Learning Profile 读取已保存画像；4. 若缺失且策略允许，则调用画像构建工具；5. 返回标准化 `profile_summary`。 |
| 扩展路径 | 画像不存在时返回 `profile_not_found` warning；构建失败时使用空画像降级；缺少 `syllabus_id` 时不读取持久画像。 |
| 字段列表 | `user_id`, `syllabus_id`, `learning_goal`, `profile_summary`, `weak_points`, `preferred_formats`, `profile_source`, `warnings` |
| 设计规则 | 画像只作为策略依据；无关长句不得直接进入用户回答；画像读取失败不得阻断所有流程。 |
| 未解决的问题 | 前端画像解释视图和用户可编辑机制待设计。 |
| 备注 | 对应 `docs/learning_profile_dev_doc.md`。 |

### 2.6.2 UC-002 推荐个性化学习路径

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 推荐个性化学习路径 |
| 功能简述 | 学生提出学习目标后，系统结合画像、课程结构、RAG 和成长树状态生成候选学习路径。 |
| 用例编号 | UC-002 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、Personal Recommendation 模块、RAG 检索服务 |
| 前置条件 | 存在 `user_id`；存在课程大纲或 learning tree；用户输入学习目标或系统已有 `learning_goal`。 |
| 后置条件 | 返回推荐结果、候选路径、`best_path` 或澄清建议。 |
| 涉众利益 | 学生获得清晰学习顺序；平台能把目标转成可执行 plan；教师可间接看到路径推荐依据。 |
| 基本路径 | 1. 学生输入学习目标；2. Total Agent 判断为路径推荐意图；3. 推荐模块读取画像和课程树；4. 构建推荐图；5. 生成、剪枝和评分候选路径；6. 返回 `best_path` 和候选解释。 |
| 扩展路径 | RAG overlay 低质量时过滤噪声边；没有可用路径时返回 `ask_goal_clarification`；缺少课程树时返回错误。 |
| 字段列表 | `learning_goal`, `profile`, `learning_tree`, `study_graph_state`, `candidates`, `selected`, `best_path`, `planning_hints` |
| 设计规则 | 推荐阶段只读成长树，不写成长树；低质量字符级 RAG 边不得进入有效推荐图。 |
| 未解决的问题 | 推荐解释在前端如何可视化仍待设计。 |
| 备注 | 对应 `docs/personal_recommendation_dev_doc.md`。 |

### 2.6.3 UC-003 接受学习计划并激活当前步骤

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 接受学习计划并激活当前步骤 |
| 功能简述 | 学生确认推荐路径后，系统将候选路径落盘为 active learning plan，并激活当前学习步骤。 |
| 用例编号 | UC-003 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、Personal Recommendation 模块 |
| 前置条件 | 已存在推荐结果；推荐结果包含可接受候选路径；学生确认或 `auto_accept=true`。 |
| 后置条件 | 生成 active plan；返回当前 `next_task`；后续可生成资源。 |
| 涉众利益 | 学生获得可执行学习计划；系统获得当前 step 作为资源生成和策略答疑依据。 |
| 基本路径 | 1. 学生确认推荐路径；2. Total Agent 识别接受意图；3. 调用 `accept_recommendation_path`；4. 落盘 learning plan；5. 激活第一个 active step；6. 返回 `next_task`。 |
| 扩展路径 | 用户未确认时返回等待确认；推荐结果缺失时返回 `missing_recommendation_result`；无可用 step 时返回 `no_next_task`。 |
| 字段列表 | `recommendation_result`, `candidate_index`, `auto_accept`, `plan_id`, `steps`, `next_task`, `metrics` |
| 设计规则 | 接受计划不自动生成资源；后续资源生成由明确意图触发。 |
| 未解决的问题 | 前端候选路径对比和确认交互待设计。 |
| 备注 | 是学习路径闭环进入资源闭环的关键节点。 |

### 2.6.4 UC-004 生成当前步骤学习资源

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 生成当前步骤学习资源 |
| 功能简述 | 系统根据当前 `next_task`、画像偏好、薄弱点和资源策略生成对应学习资源。 |
| 用例编号 | UC-004 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、Resource Generation 模块、RAG 检索服务、LLM 服务 |
| 前置条件 | 存在 active plan 和 `next_task`；用户请求继续学习、生成资料、生成练习或系统进入资源生成流程。 |
| 后置条件 | 返回生成资源、资源 metadata、生成状态和持久化结果。 |
| 涉众利益 | 学生获得贴合当前步骤的学习资料；平台沉淀可复用资源；教师可复查资源质量。 |
| 基本路径 | 1. 学生请求当前步骤资源；2. Total Agent 读取 `next_task`；3. 构建资源策略；4. Resource Generation Agent 读取请求和材料；5. 生成资源 payload；6. 持久化资源；7. 返回资源结果。 |
| 扩展路径 | 无 `next_task` 时返回 `no_next_task`；资源生成失败时返回错误和状态事件；已有可复用资源时可走复用策略。 |
| 字段列表 | `next_task`, `resource_types`, `knowledge_items`, `difficulty`, `resource_strategy`, `resources`, `resource_id`, `tool_status_events` |
| 设计规则 | 资源生成不直接推进学习计划；完成资源后的反馈由 UC-006 处理。 |
| 未解决的问题 | 前端对不同 resource type 的展示组件仍需完善。 |
| 备注 | 对应 `docs/resource_generation_dev_doc.md`。 |

### 2.6.5 UC-005 即时学习答疑

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 即时学习答疑 |
| 功能简述 | 学生提出概念、策略或练习问题，系统返回结构化回答和下一步动作建议。 |
| 用例编号 | UC-005 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、RAG 检索服务、LLM 服务 |
| 前置条件 | 用户已登录；存在 `user_id` 和 `syllabus_id`；可选存在 active plan、conversation history 和 RAG graph。 |
| 后置条件 | 返回 answer payload；不推进学习计划；不生成资源；不写学习反馈。 |
| 涉众利益 | 学生获得即时解释或学习策略；前端获得可展示结构化结果；测试可断言 QA 行为。 |
| 基本路径 | 1. 学生输入问题；2. Total Agent 加载上下文；3. 构建 session context；4. 分类问题类型；5. 检索并评分 evidence；6. 根据问题类型构建回答；7. 返回 `answer` 和 `next_actions`。 |
| 扩展路径 | RAG 低相关时返回 `low_relevance_evidence`；无 active plan 时建议确认目标或生成路径；显式 `question_type_hint` 可覆盖自动分类。 |
| 字段列表 | `question_type`, `text`, `key_points`, `evidence_used`, `plan_reference`, `relevant_weak_points`, `filtered_weak_points`, `next_actions`, `confidence`, `tone`, `warnings` |
| 设计规则 | 答疑不生成资源、不推进计划、不写反馈；低相关证据必须 warning；`tone_style` 只影响文本表达，不影响结构化决策。 |
| 未解决的问题 | 前端如何展示 warning、evidence_used 和 answer tone 待 UI 定稿。 |
| 备注 | 对应 `docs/total_agent_dev_doc.md` 的 QA 闭环。 |

### 2.6.6 UC-006 记录学习反馈并同步成长树

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 记录学习反馈并同步成长树 |
| 功能简述 | 学生完成资源、练习或学习步骤后提交反馈，系统记录学习事件、更新 plan step 状态，并同步 Study Graph。 |
| 用例编号 | UC-006 |
| 执行者 | 学生 |
| 参与系统/服务 | Total Agent、Personal Recommendation 模块、Study Graph 模块 |
| 前置条件 | 存在 active plan；存在当前 step；用户提交完成、得分、错题、跳过或其他反馈。 |
| 后置条件 | 学习计划状态和学习事件被持久化；必要时激活下一步；Study Graph 更新或返回同步 warning。 |
| 涉众利益 | 学生学习状态被记录；后续推荐和资源策略更贴合真实进度；教师可看到成长树变化。 |
| 基本路径 | 1. 学生提交学习反馈；2. Total Agent 判断为反馈意图；3. 记录学习计划事件；4. 更新 step 状态；5. 激活下一 pending step；6. 同步 Study Graph；7. 返回 next task 和 metrics。 |
| 扩展路径 | Study Graph sync 失败时不回滚 learning plan，但写入 warning/status event；无 active plan 时返回错误；跳过步骤时不同步为掌握。 |
| 字段列表 | `plan_id`, `step_id`, `status`, `event_entry`, `updated_step`, `activated_step`, `study_graph_sync`, `next_task`, `metrics` |
| 设计规则 | 只有真实触达或反馈事件才能写 Study Graph；推荐结果不直接进入成长树。 |
| 未解决的问题 | 反馈粒度和前端评分/错题输入格式可继续细化。 |
| 备注 | 对应 `docs/study_graph_dev_doc.md` 和推荐模块 step 状态更新。 |

### 2.6.7 UC-007 展示多 Agent 流程状态

| 项目 | 内容 |
| --- | --- |
| 用例名称 | 展示多 Agent 流程状态 |
| 功能简述 | 前端基于后端 `tool_status_events` 展示各 Agent 和工具阶段的运行状态。 |
| 用例编号 | UC-007 |
| 执行者 | 学生、前端应用 |
| 参与系统/服务 | Total Agent |
| 前置条件 | 后端返回 `tool_status_events`；前端具备状态流展示组件。 |
| 后置条件 | 用户可以看到画像读取、推荐、资源生成、答疑、反馈和成长树同步过程。 |
| 涉众利益 | 学生理解系统为何给出建议；评审能看到多 Agent 协同；开发者能定位运行阶段。 |
| 基本路径 | 1. 用户触发学习流程；2. 后端每个工具阶段 emit status event；3. 前端按 agent/stage/status 聚合；4. 展示 running/succeeded/failed；5. 在主结果旁展示关键摘要。 |
| 扩展路径 | 工具失败时展示 error_code 和 error_message；长耗时生成时持续展示进度；无事件时退化为普通结果展示。 |
| 字段列表 | `agent`, `stage`, `status`, `message`, `payload`, `error_code`, `tool_trace` |
| 设计规则 | 状态展示不得替代最终业务结果；错误状态必须可见；长耗时任务不得长时间白屏。 |
| 未解决的问题 | Agent card 视觉设计和移动端折叠方式待定。 |
| 备注 | 该用例是后续生产级前端演示的关键。 |

## 2.7 需求追踪矩阵

| 用例 | 用户故事 | 系统功能 | 接口需求 | 规则需求 |
| --- | --- | --- | --- | --- |
| UC-001 | US-001 | SF-001 | IR-001, IR-002 | RR-006, RR-008 |
| UC-002 | US-001 | SF-002 | IR-001, IR-002, IR-007 | RR-003, RR-006 |
| UC-003 | US-002 | SF-003 | IR-001, IR-002 | RR-006 |
| UC-004 | US-003 | SF-004 | IR-001, IR-002, IR-004, IR-008 | RR-005, RR-006 |
| UC-005 | US-004 | SF-005 | IR-001, IR-002, IR-003, IR-007, IR-008 | RR-001, RR-002, RR-005 |
| UC-006 | US-005 | SF-006, SF-007 | IR-001, IR-002, IR-005, IR-008 | RR-003, RR-004, RR-006, RR-007 |
| UC-007 | US-006 | SF-009, SF-010 | IR-002, IR-008 | RR-005 |

## 2.8 未解决问题清单

| 编号 | 问题 | 当前处理 | 后续动作 |
| --- | --- | --- | --- |
| OPEN-001 | 前端生产级学习工作台尚未定稿 | 已定义 UI 需求 | 输出线框图和组件拆分 |
| OPEN-002 | Agent 状态流视觉形态待定 | 后端已有 `tool_status_events` | 设计 Agent cards |
| OPEN-003 | 资源详情页按类型展示待完善 | 后端已有资源类型 | 设计 documents/quiz/mindmap/coding/ppt 组件 |
| OPEN-004 | warning 和 evidence 展示方式待定 | 后端已有结构化 warning | 前端定义降级提示规范 |
| OPEN-005 | 成长树可视化布局待定 | 后端已有 tree/features | 选择树图或层级图组件 |
