# 测试报告

## 当前保留范围

- 当前自动化测试包含 6 个文件：
  - `test_search_call.py`
  - `test_job_checker_startup_graph_sync.py`
  - `test_create_syllabus_draft.py`
  - `test_build_syllabus.py`
  - `test_update_syllabus_draft.py`
  - `test_update_syllabus.py`
- 不再保留：
  - `material` 工作流测试
  - `process_integration` 调度器流程测试

## 保留理由

### `test_job_checker_startup_graph_sync.py`

- 这份测试建议保留。
- 它测的不是调度器循环本身，而是 `JobChecker` 启动时新增的 graph 对账逻辑。
- 这部分逻辑是单次启动前置动作，边界明确，适合单独测试。

### `syllabus` 相关测试

- 已恢复 `syllabus` 的 task 层测试。
- 这些测试的目标是验证：
  - syllabus draft 的生成
  - final syllabus 的生成
  - draft JSON 的整包更新
  - final JSON 的整包更新

## 关于 fake / mock 的定位

- `fake` / `mock` 的作用，是把 task 层测试和外部依赖剥离开。
- 因此：
  - `syllabus` 这类 task 测试允许使用 fake 的模型、fake 的 KnowLion、fake 的 repository 回调
  - 目的在于验证任务编排、JSON 持久化、参数传递、字段更新是否正确
- 但这类测试不证明：
  - 数据库在线
  - 真实 KnowLion 可连通
  - 真实 LLM 调用可用

## `test_search_call.py` 当前含义

- 当前文件不只是“测 search”。
- 它现在包含两层：
  - 默认 unit 测试：mock 检索结果，并断言 `search_call()` 最终确实调用了 `call_text_model(...)`
  - 可选 `llm` smoke 测试：在显式开启时，使用真实模型配置走一次真实 LLM 调用路径

## 运行方式

- 默认执行：
  - `pytest -q`
- 只在明确需要验证真实 LLM 时执行：
  - `RUN_LLM_TESTS=1 pytest -q -m llm`

## JSON 清理策略

- 当前只对这两个目录做精准清理：
  - `schedule/syllabus_draft/*.json`
  - `schedule/syllabus/*.json`
- 清理方式：
  - 每个测试前后对目录做快照
  - 仅删除本次测试新增的 JSON
  - 不触碰既有缓存和历史文件
