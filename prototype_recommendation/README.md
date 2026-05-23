最小可运行的个人推荐Agent原型。

运行方法：

```bash
python prototype_recommendation/run_demo.py
```

包含模块：
 - benchmarks/benchmark_perf.py  # 性能基准测试脚本
 - graph_adapter.py  # 提供 `GraphAdapter` 抽象与 `InMemoryGraphAdapter` / `KnowLionGraphAdapter`

基准测试：

```bash
python prototype_recommendation/benchmarks/benchmark_perf.py --nodes 200 --runs 3
```

输出保存到 `prototype_recommendation/benchmarks/results`。

 运行方法：

 示例已迁移至 `tasks/personal_recommendation`，请参见项目中的演示和测试：

 `tasks/personal_recommendation/sample_data.py` 与 `tests/personal_recommendation` 包含示例数据与集成测试。
 
 切换数据源：已集成到 `tasks/personal_recommendation/graph_adapter.py`，默认使用内存实现。
 如需对接 KnowLion，请使用 `tasks/personal_recommendation/graph_adapter.KnowLionGraphAdapter`。
