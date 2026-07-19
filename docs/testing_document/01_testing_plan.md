# 项目测试文档

## 1 测试计划

### 1.1 测试策略与目标

本测试文档面向学习平台后端、Agent 调度链路、学习路径推荐、学习画像、学习资源生成、学习成长树、RAG 检索增强与管理端内容维护等能力，采用“单元测试、功能测试、系统测试”分层组织。测试重点放在业务闭环是否稳定、关键模块边界是否清晰、数据产物是否可追溯，以及真实 LLM/RAG/数据库链路在发布前是否具备可验收依据。

测试策略如下：

| 测试层级 | 测试目的 | 主要方法 | 执行特点 |
| --- | --- | --- | --- |
| 单元测试 | 验证任务入口、工具函数、数据结构、状态机和持久化边界的正确性 | 使用 pytest、mock、fixture、临时目录和契约断言 | 默认可自动化执行，不依赖真实 LLM/RAG |
| 功能测试 | 验证学生用户和管理员在典型业务流程中的功能完整性 | 使用 API 调用、Agent 工具链、测试数据和产物检查 | 覆盖端到端业务行为，必要时启用真实 Agent |
| 系统测试 | 验证 RAG、画像准确性、真实链路可用性和关键性能指标 | 使用 experiments 目录中的评测数据、人工抽查和发布前验收 | 用于质量评估和发布判断 |
| 回归测试 | 验证关键链路修改后未破坏已有行为 | 默认 pytest 回归、Total Agent E2E、计划生命周期 smoke | 重点覆盖学习计划、资源生成、画像读取和反馈推进 |

测试目标如下：

| 编号 | 测试目标 | 验收关注点 |
| --- | --- | --- |
| T-01 | 验证学习路径推荐与计划确认链路 | 能生成候选路径，能按用户选择激活计划，计划状态与步骤状态一致 |
| T-02 | 验证 Total Agent 上下文读取与调度链路 | 能正确读取画像、学习树、学习计划和当前资源，不产生错误计划判断 |
| T-03 | 验证学习画像生成与持久化链路 | 能根据学习记录、答题记录、资源使用和目标信息生成结构化画像 |
| T-04 | 验证学习资源生成链路 | 能生成文档、PPT、思维导图、测验、编程练习等资源，并完成校验与落盘 |
| T-05 | 验证学习成长树更新链路 | 能根据学习行为、计划反馈和资源使用同步成长树状态 |
| T-06 | 验证 RAG 检索增强效果 | 检索精确率、召回率、响应耗时和幻觉率满足阶段性要求 |
| T-07 | 验证管理端内容与运维能力 | 教学大纲、图谱、文件、Job 和 Agent 定义可被管理员维护 |
| T-08 | 验证异常处理能力 | 对缺失上下文、无活跃计划、无候选路径、文件缺失、LLM 波动等情况给出稳定结果 |

### 1.2 测试范围

#### 1.2.1 测试对象范围

| 范围类别 | 覆盖对象 | 说明 |
| --- | --- | --- |
| 学生端学习闭环 | 学习路径推荐、计划确认、当前任务、学习反馈、资源生成、资源查看、成长树查看 | 覆盖学生用户主流程 |
| 管理端内容运维 | 文件上传下载、图谱列表、图谱创建、教学大纲管理、Job 管理、totalAgent 定义查看 | 覆盖管理员核心维护操作 |
| Agent 调度 | Total Agent、Profile Agent、Recommendation Agent、Resource Agent、Study Graph Agent | 覆盖工具选择、上下文读取、产物写入和状态推进 |
| 数据持久化 | MySQL、国产时序动态图数据库、文件管理目录、manifest 文件 | 覆盖结构化数据、图谱数据和资源文件 |
| RAG 能力 | 检索精确率、召回率、检索耗时、幻觉率 | 使用 experiments/RAG/eval_outputs 现有评测数据 |
| 画像质量 | 基础画像、边界样本、人工复核、产物可用性 | 使用 experiments/user_analize/outputs 现有评测数据 |

#### 1.2.2 不纳入本轮重点测试的范围

| 不纳入范围 | 原因 | 后续建议 |
| --- | --- | --- |
| 大规模并发压测 | 当前系统测试数据主要覆盖功能正确性和单请求性能 | 发布前可增加 Locust/JMeter 压测 |
| 长周期生产数据漂移评估 | 需要连续真实用户数据 | 上线后按周生成画像漂移报告 |
| 前端视觉像素级验收 | 本文档定位为测试文档，前端表现层另行验收 | 前端可补充截图回归与 Playwright 用例 |
| 第三方 LLM 服务 SLA 验证 | 外部模型延迟和稳定性存在不可控因素 | 通过重试、降级和日志观测控制风险 |

### 1.3 测试环境

#### 1.3.1 软件环境

| 环境项 | 配置 |
| --- | --- |
| 操作系统 | Windows + WSL |
| Python 环境 | WSL conda 环境 `lianjue` |
| 后端测试框架 | pytest |
| Agent 框架 | PydanticAI 及 OpenAI-compatible 模型调用链路 |
| 数据库 | MySQL |
| 图数据库 | 国产时序动态图数据库/KnowLion 图谱检索服务 |
| 文件管理 | 本地文件管理目录、资源 manifest、测试 artifacts |
| 前端相关 | Node/Vite/浏览器环境，用于功能联调和展示验证 |
| RAG 图谱名称 | RAG |

#### 1.3.2 测试数据与产物目录

| 数据类型 | 路径 | 用途 |
| --- | --- | --- |
| 测试说明 | `tests/TEST_REPORT.md` | 测试命令、用例边界、集成入口和阶段验收记录 |
| 测试代码 | `tests/` | 单元测试、集成测试、E2E 测试 |
| RAG 评测数据 | `experiments/RAG/eval_outputs/` | 检索性能、精确率、召回率、幻觉率分析 |
| 画像评测数据 | `experiments/user_analize/outputs/` | 画像准确性、边界样本、人工复核分析 |
| 测试产物 | `tests/artifacts/` | E2E 运行结果、资源生成结果、计划和成长树产物 |
| 教学大纲 fixture | `tests/fixtures/大数据概论_20260322235507.json` | 大数据概论课程测试样本 |

#### 1.3.3 典型执行命令

| 测试类型 | 命令 |
| --- | --- |
| 默认单元回归 | `python -m pytest -q` |
| 学习画像真实 Agent 验证 | `RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py tests/test_profile_personal_syllabus_full_chain.py -m llm --capture=tee-sys -rs` |
| 资源生成真实 Agent + Search 验证 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 RUN_LLM_TESTS=1 RUN_SEARCH_TESTS=1 SEARCH_TOOL_GRAPH_NAME=RAG python -m pytest -p no:debugging -q tests/test_generative_resource_agent_integration.py -m "llm and search" --capture=tee-sys -rs` |
| 学习成长树真实 Agent 验证 | `RUN_LLM_TESTS=1 python -m pytest -q tests/test_study_graph_agent_choice.py -m llm --capture=tee-sys -rs` |
| 推荐路径 Agent 验证 | `RUN_LLM_TESTS=1 python -m pytest -q tests/test_personal_recommendation_agent_choice.py -m llm` |
| Total Agent E2E 默认入口 | `python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs` |
| Total Agent 发布前真实链路验收 | `RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs` |
| 计划生命周期 smoke 测试 | `pytest tests/total_agent/test_plan_lifecycle.py -v` |
