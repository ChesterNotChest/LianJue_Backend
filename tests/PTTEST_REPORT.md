# PTTEST 测试报告

## 1. 目标

本次在 tests 目录新增 pttest 文件，覆盖两类测试：

- 单元测试：验证远程地址判定逻辑。
- 集成测试：真实连接远程 Abution 图数据库服务并拉取图列表。

## 2. 新增与修改文件

- tests/pttest.py
- pytest.ini

## 3. 配置说明

### 3.1 运行开关

- RUN_REMOTE_DB_TESTS=1
  - 启用远程数据库集成测试。
  - 未设置时，集成测试会自动 skip。

### 3.2 图名称配置

- PTTEST_GRAPH_NAME
  - 可选，默认值为 RAG。
  - 用于初始化 KnowLion 时指定 graph_name。

### 3.3 配置来源

集成测试使用 config.json 中 ABUTION_CONFIG：

- abution_url: 远程服务地址（本次实跑为 play.edgerunners.cn:30453）
- username/password: 由现有配置提供
- use_ssl/allow_self_signed: 按现有配置生效

## 4. 实际执行命令

在项目根目录下执行：

```powershell
Set-Location "c:/Users/Lenovo/Desktop/基于动态知识图谱的RAG增强大模型辅助专家系统/LianJue_Backend-main"
$env:RUN_REMOTE_DB_TESTS="1"
c:/Users/Lenovo/Desktop/基于动态知识图谱的RAG增强大模型辅助专家系统/.venv/Scripts/python.exe -m pytest -q tests/pttest.py -m "remote_db or not remote_db" -s
```

## 5. 实际结果

- 总体：2 passed, 2 warnings
- 总耗时：5.56s

### 5.1 单元测试

- test_pttest_unit_remote_url_detection
- 结果：通过

### 5.2 集成测试（远程数据库）

- test_pttest_integration_remote_graph_list
- 结果：通过
- 关键遥测：
  - abution_url: play.edgerunners.cn:30453
  - graph_name: RAG
  - payload_type: list
  - graph_count: 2
  - elapsed_ms: 520.48

## 6. 警告说明

本次 pytest 输出包含 2 条第三方依赖 deprecation warning（pandoc/importlib.resources）。

- 不影响 pttest 功能正确性。
- 如需清理，可在后续统一升级相关依赖版本。

## 7. 可复现与扩展建议

- 复现：保持 config.json 中 ABUTION_CONFIG 可用，并设置 RUN_REMOTE_DB_TESTS=1。
- 扩展：可增加远程图 schema 拉取、指定图读写 smoke case、失败重试与延迟阈值断言。

## 8. 实际路径选择过程与结果补充

以下为本次真实执行 `prototype_recommendation/run_demo.py` 的原始结果，用于说明“最终路径是如何产生的”。

### 8.1 客户展示版推荐路径

基于远程图服务检索到的真实主题，可以给客户直接展示为：

- 推荐路径：监督学习 -> 机器学习
- 节点说明：
  - 监督学习：通过训练数据学习一个能够预测结果的模型。
  - 机器学习：人工智能的重要分支，包含监督学习、无监督学习、强化学习等方法。



### 8.2 真实输出摘要

- start nodes: ['n2', 'n3', 'n4', 'n5']
- generated candidates: 4
- after hard prune: 4
- 候选评分（节选）:
  - path ['n4'], cost 8.0, scores {E: 0.12499998437500197, D: 2.6666666666666665, R: 1.0, P: 0.5}
  - path ['n5'], cost 10.0, scores {E: 0.09999999000000101, D: 3.6666666666666665, R: 1.0, P: 0.5}
  - path ['n2', 'n4'], cost 12.0, scores {E: 0.16666665277777895, D: 2.1666666666666665, R: 0.6666666666666666, P: 0.5}
- selected paths:
  - {'path': ['n2', 'n4'], 'cost': 12.0, 'skills': {'stats_basic', 'ml_basic'}}

### 8.3 过程解释（对应输出）

1. 先从用户状态推导起始节点（start nodes）。
2. 候选生成器产出 4 条候选路径（generated candidates）。
3. 经过硬剪枝后仍保留 4 条（after hard prune）。
4. 对候选路径按 E/D/R/P 四维指标打分。
5. 选择器在约束与权重下给出最终路径：['n2', 'n4']。

### 8.4 与远程数据库测试的关系

- 第 5 章中的 pttest 集成测试，验证的是“已真实连接远程 Abution 图数据库并可读图列表”。
- 本节 run_demo 展示的是“推荐算法路径生成与选择逻辑”的真实运行结果（使用示例学习图数据）。
- 两者共同说明：远程图服务连通性已验证，算法链路也可实际跑通并产出最终路径。

## 9. 个性化推荐接口（最小可用原型）

- 新增接口：`POST /api/personal_recommendation`
- 功能：接受 `user_id`（可选 `syllabus_id`、`goals`），从用户画像构建决策上下文并在示例学习图上生成候选路径与最终选中路径。
- 实现位置：[`blueprint/learning_api.py`](blueprint/learning_api.py#L1)
- 说明：该接口使用已有的 `get_or_build_learning_profile` 拉取/构造 `user_profile`，再调用 `tasks.personal_recommendation` 的 `generate_state` + `generate` + 剪枝/评分/选择流水线输出结果。当前为最小可用原型并依赖 `tasks/personal_recommendation/sample_data.py` 作为学习图数据源。


