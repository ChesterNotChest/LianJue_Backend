# 项目开放文档

本文档组用于整理“基于大模型的个性化资源生成与学习多智能体系统”的项目开放文档。内容面向评审、开源读者、产品接入方和后续维护者，目标是用一套项目级文档说明系统背景、功能、架构、核心算法、接口、部署、测试与创新价值。

本文档组不替代模块级 dev doc。模块级事实源仍为：

- `docs/learning_profile_dev_doc.md`
- `docs/personal_recommendation_dev_doc.md`
- `docs/resource_generation_dev_doc.md`
- `docs/study_graph_dev_doc.md`
- `docs/total_agent_dev_doc.md`

本文档组引用这些 dev doc 的当前实现事实，并把它们组织成对外可读的项目说明。

## 文档目录

| 章节 | 文件 | 内容 |
| --- | --- | --- |
| 0 | `00_revision_history.md` | 文档版本、修订记录、事实源约束 |
| 1 | `01_project_overview.md` | 项目背景、定位、方案、目标与价值 |
| 2 | `02_requirements_analysis.md` | 数据、功能、性能、界面、接口与安全需求 |
| 3 | `03_system_architecture.md` | 总体架构、处理流程、多 Agent 协同结构 |
| 4 | `04_core_algorithms_and_agents.md` | 核心算法、Agent 机制、RAG、推荐、生成、成长树 |
| 5 | `05_function_design.md` | 各功能模块的输入、输出、逻辑与边界 |
| 6 | `06_data_and_database_design.md` | 数据结构、持久化目录、数据库与迁移建议 |
| 7 | `07_interface_and_frontend_design.md` | API 对齐、前端交互、演示界面与状态流 |
| 8 | `08_deployment_and_runtime.md` | 运行环境、配置、部署、模型与外部依赖 |
| 9 | `09_innovation_and_value.md` | 技术创新、功能创新、应用价值 |
| — | `tests/TEST_REPORT.md` | 测试体系、E2E 回归、验收标准（独立维护） |

## 写作原则

- 以当前真实实现为准，不以旧 small plan 或 contract 为准。
- 能确定的能力用“已实现”；未完成但计划进入演示的能力用“待补”；没有代码支撑的能力不写成已实现。
- 项目开放文档偏对外叙述，模块 dev doc 偏工程事实和函数级契约。
- 所有图示位置先保留 `待补图`，后续再补架构图、流程图、界面图和数据流图。

