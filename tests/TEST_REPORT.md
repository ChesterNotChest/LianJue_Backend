# 后端测试说明

## 第一步：开始测试

在 WSL 中进入项目目录并激活环境：

```bash
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
conda activate lianjue
python -m pytest -q
```

当前默认测试应当通过，真实 LLM 调用会默认跳过。

如需验证真实 LLM / Agent 调用链，再显式执行：

```bash
RUN_LLM_TESTS=1 python -m pytest -q -m llm
```

## 当前测试范围

默认 pytest 只收集 `tests/` 目录，配置来自根目录 `pytest.ini`：

```ini
[pytest]
testpaths = tests
markers =
    llm: requires a real configured LLM call path and is opt-in
```

当前保留的自动化测试主要覆盖以下几组：

- 用户画像 Agent 与工具链
- syllabus draft / final 的生成与更新
- JobChecker 启动时的 graph 同步逻辑
- KnowLion `search_call()` 的格式化与 LLM 调用入口

## 用户画像 Agent 测试

### `test_learning_profile.py`

验证 `build_learning_profile()` 在 mock repository / fake agent 下能正确组合用户行为、答题记录、资源使用和上下文工具。

主要覆盖：

- 行为、答题、资源使用信号能进入画像
- 知识点掌握度能根据答题正确率计算
- 概念薄弱点能被识别
- 目标清晰度、情绪状态、风险信号等规则特征能返回
- agent 可以先调用上下文工具，再调用特征计算工具

### `test_learning_profile_toolchain.py`

离线验证用户画像工具链，不调用真实 LLM。

主要覆盖：

- 用户画像模型和 `learning_profile_agent` 可以初始化
- `_tool_normalize_events()` 能归一化行为、答题、资源事件
- `_tool_compute_features()` 能计算画像特征
- `_tool_assemble_profile()` 能组装结构化 profile
- `LearningProfileResult` schema 可正常承载画像结果

### `test_learning_profile_agent_choice.py`

真实 LLM opt-in 测试，默认跳过。

该测试用于证明用户画像子 Agent 不是只跑纯函数，而是由 agent 自己触发工具调用，并最终返回画像。

期望工具调用顺序：

```text
load_history_context
load_personal_syllabus_context
normalize_events
compute_features
assemble_profile
```

运行方式：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_learning_profile_agent_choice.py
```

## Syllabus 相关测试

### `test_create_syllabus_draft.py`

验证 syllabus draft 任务能生成草稿 JSON，并正确绑定 graph / repository 回调。

### `test_build_syllabus.py`

验证 final syllabus 构建逻辑，包括按周内容增强、JSON 持久化和 fake KnowLion 检索隔离。

### `test_update_syllabus_draft.py`

验证 draft JSON 的整包更新逻辑，确保标题、周次内容等字段被正确替换。

### `test_update_syllabus.py`

验证 final syllabus JSON 的整包更新逻辑，确保持久化内容和 day-one 字段保持正确。

这些测试使用 fake / mock 隔离外部依赖，目标是验证 task 层编排、JSON 持久化、参数传递和字段更新，不证明真实数据库、真实 KnowLion 或真实 LLM 可用。

## JobChecker 测试

### `test_job_checker_startup_graph_sync.py`

验证 JobChecker 启动时的 graph 同步逻辑。

主要覆盖：

- 能从不同结构的远端响应中提取 graph 名称
- 只初始化远端缺失的 graph
- 远端 graph 列表读取失败时不会误初始化

这部分测试的是启动前置同步逻辑，不测试 JobChecker 的完整轮询循环。

## Search Call 测试

### `test_search_call.py`

包含两层：

- 默认 unit 测试：mock 检索结果，验证 `search_call()` 会把问题、reasoning paths、paragraphs 组装进 prompt，并调用 `call_text_model(...)`
- `llm` smoke 测试：显式开启时，使用真实模型配置走一次真实 LLM 调用路径

真实 LLM 运行方式：

```bash
RUN_LLM_TESTS=1 python -m pytest -q tests/test_search_call.py -m llm
```

## 关于 mock / fake 的定位

默认测试中的 fake / mock 主要用于隔离外部依赖：

- 不要求 MySQL 在线
- 不要求 AbutionGraph 在线
- 不要求真实 KnowLion 图谱可用
- 不默认调用真实 LLM

默认测试关注的是后端 task 层、工具链、数据结构和持久化逻辑是否正确。

真实外部依赖验证统一放在 `llm` marker 下，并通过 `RUN_LLM_TESTS=1` 显式开启。

## JSON 清理策略

`tests/conftest.py` 会在每个测试前后对以下目录做快照：

- `schedule/syllabus_draft/*.json`
- `schedule/syllabus/*.json`

测试结束后只删除本次测试新增的 JSON 文件，不会删除已有缓存或历史文件。
