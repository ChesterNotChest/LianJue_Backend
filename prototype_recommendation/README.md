最小可运行的个人推荐Agent原型。

运行方法：

```bash
python prototype_recommendation/run_demo.py
```

包含模块：
- perception.py
- candidate_generator.py
- evaluator.py
- selector_ib_grpo.py
- sample_data.py
- run_demo.py
 - benchmarks/benchmark_perf.py  # 性能基准测试脚本
 - graph_adapter.py  # 提供 `GraphAdapter` 抽象与 `InMemoryGraphAdapter` / `KnowLionGraphAdapter`

基准测试：

```bash
python prototype_recommendation/benchmarks/benchmark_perf.py --nodes 200 --runs 3
```

输出保存到 `prototype_recommendation/benchmarks/results`。

切换数据源：
- `candidate_generator.generate(..., graph_adapter=adapter)` 接受一个 `GraphAdapter` 实例，
	若不提供则使用内存实现。
- 可实现 `KnowLionGraphAdapter` 来对接仓库内的 `KnowLion` 驱动（`knowlion/abution_knowlion_driver.py`）。
