# 9 测试与验收

## 9.1 测试体系

系统测试分为：

- 单元测试：验证工具函数、schema、策略判断、过滤逻辑。
- 模块集成测试：验证真实 Agent 或模块工具链。
- 默认 E2E：不依赖真实 LLM / RAG / DB，验证后端闭环。
- opt-in E2E：开启真实 LLM / RAG / DB，验证真实环境表现。

## 9.2 Total Agent E2E 入口

统一 E2E 入口：

```bash
python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "not llm and not mysql and not search" --capture=tee-sys -rs
```

真实 opt-in 回归：

```bash
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 python -m pytest -q tests/total_agent/test_total_agent_e2e.py -m "llm and search and mysql" --capture=tee-sys -rs
```

## 9.3 关键验收标准

后端闭环验收：

- 能读取画像或构建画像。
- 能推荐学习路径并接受为 active plan。
- 能读取 next task 并生成资源。
- 能记录学习反馈并推进 plan。
- 能同步 Study Graph 或记录同步 warning。
- 能回答概念型和策略型学习问题。

前端演示验收：

- 能展示多 Agent 状态流。
- 能展示当前学习步骤和资源。
- 能展示结构化答疑结果和下一步动作。
- 能展示成长树变化。
- 能自然处理低相关 RAG、无 active plan、生成中和错误状态。

## 9.4 测试报告

测试命令和最近结果应维护在：

```text
tests/TEST_REPORT.md
```

最终提交前需要补充：

- 默认测试结果。
- opt-in 测试结果。
- 失败项说明和是否为环境问题。
- 关键 artifacts 路径。

## 9.5 验收材料

建议提交材料：

- 项目开放文档。
- 模块 dev doc。
- 测试报告。
- 演示 PPT。
- 7 分钟以内演示视频。
- 运行说明。
- 模型、开源依赖和 AI Coding 工具说明。

