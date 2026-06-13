# 8 部署与运行环境

## 8.1 运行环境

当前后端运行环境以项目实际配置为准。文档编写和测试中使用：

- Python 环境：`conda activate lianjue`
- 数据库：MySQL，测试库名示例 `knowlion`
- RAG：项目 `tasks/common/search_tool.py` 封装
- LLM：OpenAI-compatible provider，通过统一模型构造工具适配

待补表：最终部署环境、Python 版本、依赖安装、数据库版本、模型 provider。

## 8.2 系统配置

配置项包括：

- 模型 provider 和模型名。
- API key。
- RAG graph name。
- 数据库连接。
- 资源持久化路径。
- Study Graph 路径。
- 测试环境开关。

测试开关示例：

```bash
RUN_LLM_TESTS=1
RUN_REAL_RAG_TESTS=1
RUN_DB_TESTS=1
```

## 8.3 部署方案

后端部署建议：

- 使用虚拟环境或容器固定依赖。
- 启动 API 服务。
- 配置 MySQL。
- 配置 RAG 服务和图谱数据。
- 配置模型 provider。
- 配置运行时目录写权限。

前端部署建议：

- 独立构建静态资源。
- 通过 API base URL 接入后端。
- 对长耗时资源生成使用状态事件或轮询/流式机制展示进度。

待补图：部署拓扑图。

## 8.4 外部依赖

外部依赖类型：

- LLM provider。
- RAG / KnowLion 检索服务。
- MySQL。
- 文件存储。
- 前端运行环境。

若使用开源框架或 AI Coding 工具，需要在最终文档显著位置列出名称、来源和许可证。

## 8.5 手机端或移动端说明

当前文档不把“手机端侧部署”作为独立硬要求。若后续前端提供移动端适配，可在本节补充：

- 移动端浏览器兼容性。
- 响应式布局。
- 资源阅读和答题体验。
- 成长树在小屏上的折叠展示。

