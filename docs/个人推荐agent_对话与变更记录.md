## 对话与变更记录

日期：2026-05-21

### 一、任务概述
- 用户需求：将候选生成的剪枝与替换规则提前（在生成期做早期剪枝并引入替换算子），并把实现和讨论的对话整理成文档。
- 目标产出：代码实现（早期硬剪枝、早期软剪枝、替换算子）、演示验证、更新设计文档，并将对话内容整理为文档。

### 二、实现变更（代码）
- 文件：prototype_recommendation/candidate_generator.py
  - 修改：在展开阶段加入早期硬剪枝（跳过 S.constraints.blocked_nodes、超时检测）。
  - 修改：将原来的轻量支配剪枝替换为基于实际评估器的早期软剪枝：对部分（部分路径）调用 `evaluator.score` -> `normalize_scores` -> `scalar_scores`，按标量分保留 top-N（上限为 beam_width 的若干倍）。该改动在生成阶段即可剔除低质量部分路径，减少后续评分/Pareto 判定成本。

- 文件：prototype_recommendation/pruning.py
  - 修改：新增 `local_replace_candidates(candidates, learning_tree, S, max_attempts=100)`，实现局部单节点替换策略（尝试同一前驱下的兄弟节点替换以提升简单效率指标），用于生成后、硬剪枝前增加候选多样性和潜在改进。

- 文件：prototype_recommendation/run_demo.py
  - 修改：在生成后、硬剪枝前调用 `local_replace_candidates(...)`，用于演示替换算子的效果流程。

- 文件：docs/个人推荐agent_落地设计.md
  - 修改：加入说明“在生成阶段使用早期软剪枝（调用 Evaluator.score）”的设计决策、权衡与工程建议（缓存、批量化、并行、评分次数上限等）。

### 三、实现要点与设计决策
- 早期硬剪枝：在生成时就过滤 blocked_nodes、超过 `T_max` 或 `max_total_time` 的路径，避免无效扩展。
- 早期软剪枝：在每层生成后对部分路径（部分前缀）调用 `Evaluator.score`，对结果做归一化并计算加权标量分，按标量分截断 beam（保留 top-N）。优点是能在生成阶段去除明显低质量路径；缺点是生成阶段增加评分开销。
- 替换算子：`local_replace_candidates` 用随机化局部替换尝试改善候选，属于轻量启发式，不保证全局最优，但能提升多样性与实用率。
- 权衡建议：把生成阶段评分做批量化与缓存；控制每层评分上限（例如每层最多评分 M 个新路径）；在高并发场景设置 K_max（候选上限）。

### 四、验证与输出
- 我在本地用内存学习树运行了演示脚本：

```bash
python -c "import sys,os; repo=r'c:\\Users\\Lenovo\\Desktop\\基于动态知识图谱的RAG增强大模型辅助专家系统\\LianJue_Backend-main'; sys.path.insert(0, os.path.join(repo,'prototype_recommendation')); import run_demo as d; d.main()"
```

- 演示输出（节选）：

```
start nodes: ['n2', 'n3', 'n4', 'n5']
generated candidates: 4
after hard prune: 4
0 ['n4'] cost 8.0 scores {...}
1 ['n5'] cost 10.0 scores {...}
2 ['n2', 'n4'] cost 12.0 scores {...}

selected paths:
{'path': ['n2', 'n4'], 'cost': 12.0, 'skills': {'ml_basic', 'stats_basic'}}
```

（注：演示使用的是 `InMemoryGraphAdapter` 与本地示例数据，KnowLion 适配器为可插拔实现，需在生产环境验证响应结构并做调整。）

### 五、变更历史（简要）
- 2026-05-21: 添加早期硬剪枝、替换轻量支配剪枝为 evaluator 驱动的早期软剪枝，新增替换算子并在 demo 中集成，更新设计文档。

### 六、下一步建议（可选任务）
- A. 对生成阶段的评分调用做缓存/批量化以降低开销（推荐优先级高）。
- B. 为早期软剪枝添加配置阈值与单元测试覆盖（确保行为可测）。
- C. 在 `InMemoryGraphAdapter` 中添加 children 索引，提高 `expand` 性能（树形子图场景）。
- D. 将早期软剪枝的评分放到异步/并行线程池里并限制每层评分数量。

---

如果你希望我继续执行 A/B/C 中的某一项，我可以马上开始实现并提交对应补丁与测试。 
