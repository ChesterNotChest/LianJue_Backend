# Learning Path Recommendation Experiments

This directory contains experiment and benchmark scripts for the learning path recommendation route.

The production implementation lives under:

```text
tasks/personal_recommendation/
tasks/personal_recommendation_task.py
```

## Performance Benchmark

Run from the backend repository root:

```bash
python experiments/learning_path_recommendation/benchmarks/benchmark_perf.py --nodes 200 --runs 3
```

Default outputs are written to:

```text
experiments/learning_path_recommendation/benchmarks/results/
```

The benchmark uses synthetic DAG learning trees and the task-level recommendation modules. It is not part of the default pytest regression suite.
