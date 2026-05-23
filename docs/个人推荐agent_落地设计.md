**架构概览**
- **学生感知层 (Perception)**: 使用学习树（Learning Tree）+ 用户画像（多维指标）构建学生当前状态向量 `S`。
- **候选路径生成层 (Candidate Generation)**: 基于知识图谱/学习树的图遍历（BFS/DFS/A*）生成候选学习路径集合 `P = {p1,p2,...}`。
- **多目标评估与择优层 (Evaluation & Selection)**: 对每条路径计算多目标得分向量，使用 IB-GRPO（带信息束约束的 GRPO）进行排序与剪枝，输出最终推荐路径。

**数据模型**
- 学习树节点 `Node`:
  - id, title, difficulty, prerequisites (list[node_id]), learning_time_est, outcomes (skills)
- 用户画像 `UserProfile`:
  - knowledge_levels: {skill: level}
  - preferences: {time_per_day, preferred_formats, risk_aversion}
  - constraints: {deadline, max_total_time}
- 学生状态向量 `S`：将 `knowledge_levels` 与学习树映射为向量（可用稀疏向量/embedding）

**候选路径生成（图谱遍历）**
- 输入：起点集合 `start_nodes`（根据 S 与未掌握 outcomes），目标：达到目标技能节点集合或满足学习目标。
- 算法：带启发式的有界A*或受限BFS
  - 启发函数 h(p) = 预计剩余学习时间或与目标技能差距的估计
  - 限制：路径长度 L_max、累计学习时长 T_max、节点重复阈值
- 输出：候选路径集合 `P`（每条路径含节点序列、估计cost、覆盖技能）

        - 已实现产出说明：
          - Graph Adapter（图适配器）产出：可插拔的图查询层，使上层生成器和评估器无需关心底层图服务实现。
            - 使用逻辑：抽象图查询接口，运行时可切换 InMemory（本地字典）或 KnowLion（远端服务）。
            - 产出：稳定的邻居/先修/产出/成本查询能力，供生成与评估模块调用。
          - Candidate Generation（候选生成）产出：候选学习路径集合（每条含节点序列、累计成本、覆盖技能）。
            - 使用算法：Beam + 启发式（f = g + w*h），并支持向前/向后扩展模式。
            - 关键逻辑：早期硬剪枝（用户屏蔽、时间预算、去环）用于快速剪掉不可行路径；早期软剪枝（在生成阶段用多目标评分的标量分截断束）用于削减低质量前缀。
            - 产出格式：List[PathItem]，每项包含 `path`, `cost`, `skills`，用于后续评分与选择。
          - Evaluator（评估器）产出：每条候选的多目标指标向量（E/D/R/P）及归一化/标量化结果。
            - 使用算法/逻辑：基于路径覆盖的新技能数、平均难度与用户能力差、未满足先修比率、偏好匹配度计算向量；提供归一化与加权合成为标量分的工具。
            - 产出：原始向量 `{'E','D','R','P'}`、归一化向量和标量分，供软剪枝与 Selector 使用。
          - Pruning & Replacement（剪枝与替换）产出：合规过滤后的候选集与替换增强候选。
            - 使用逻辑：先执行硬剪枝（剔除违反硬约束的路径），然后可执行替换算子尝试局部替换以增加多样性与改进候选质量，最后基于 Pareto 做软剪枝以去除被支配解。
            - 产出：经过替换和软剪枝后的候选池，准备提交给 Selector。
          - Selector / Policy（选择器/策略）产出：最终推荐路径列表（多样性与合规性校验通过），并伴随可解释的评分与选择理由。
            - 使用算法：IB-GRPO（信息束 + 随机化贪婪 + Pareto 前沿 + 多样性剪枝）实现多目标择优与多样性保留。
            - 关键逻辑：在输出前强制执行硬约束、动态松弛 IB 阈值以保证可用池、暴露 hook 供人工覆写并记录审计日志。
            - 产出：最终 Top-N 推荐路径及选择元数据（归一化分、标量分、多样性指标、决策理由）。
          - Demo & Tests（演示与验证）产出：可运行的流程示例与基础测试用例，用于验证端到端流程与适配器正确性。
            - 使用逻辑：提供示例数据、运行脚本打印流程输出，并有集成测试验证关键路径可达与适配器统计。
            - 产出：示例控制台输出与测试断言，便于团队复现与验证。
      - 返回值：`incr_read` 无返回；`get_stats()` 返回统计字典（如 `{'node_reads': int}`）。

- `prototype_recommendation/candidate_generator.py`（已实现）
  - 说明：核心函数 `generate(start_nodes, goals, learning_tree, S, L_max=6, T_max=100, K=20, beam_width=6, expand_mode='forward', heuristic_weight=1.0, graph_adapter=None)`。
  - 参数与行为要点：
    - `start_nodes` / `goals`：入口节点与目标技能集合。
    - `S`：学生状态向量（包含 `knowledge`, `constraints`, 可选 `weights_override`）。
    - `beam_width`：每层保留束宽（控制搜索分支）
    - `heuristic_weight`：f = g + heuristic_weight * h，用于平衡代价与启发式估计。
    - `graph_adapter`：可注入 `GraphAdapter` 实现以切换到 KnowLion 服务。
  - 已实现特性：
    - 早期硬剪枝：展开时跳过 `S['constraints']['blocked_nodes']`、跳过超过 `T_max` 或 `max_total_time` 的路径、避免重复节点环路（`seen` 集）。
    - 早期软剪枝：在每一层把新生成的部分路径批量送入 `Evaluator.score`，再调用 `normalize_scores` 与 `scalar_scores` 计算标量分，并按标量分截断保留 top-N（配置 cap），从而在生成阶段削减低质量前缀。
    - 返回格式：列表，每项为 `{'path': [...node ids...], 'cost': total_cost, 'skills': set(outcomes)}`。
  - 注意事项：评分在生成阶段会带来额外开销，已为 `S` 支持 `weights_override` 以临时覆写权重用于软剪枝实验。
  - 具体函数实现与接口（中文说明）：
    - `generate(start_nodes, goals, learning_tree, S, L_max=6, T_max=100, K=20, beam_width=6, expand_mode='forward', heuristic_weight=1.0, graph_adapter=None)`
      - 输入参数：
        - `start_nodes`：起始节点 id 列表（List[str]）
        - `goals`：目标技能或目标节点 id 列表（List[str]）
        - `learning_tree`：学习树数据结构（dict，节点 id -> 节点属性）
        - `S`：学生状态字典（包含 `knowledge`, `constraints`, 可选 `weights_override`）
        - `L_max`：路径最大长度（int）
        - `T_max`：路径最大累计时间/成本（float）
        - `K`：期望返回的候选数上限（int）
        - `beam_width`：束宽（int）
        - `expand_mode`：展开方向（'forward' 或 'backward'）
        - `heuristic_weight`：启发式权重（float）
        - `graph_adapter`：可选的 `GraphAdapter` 实例，用于查询图数据
      - 返回值：候选路径列表（List[Dict]），每个字典格式：`{'path': List[str], 'cost': float, 'skills': Set[str]}`。
    - 内部重要行为说明：
      - 在每层对新生成前缀批量调用 `evaluator.score`，并按 `scalar_scores` 截断 `beam`，用于早期软剪枝。
      - `S` 中的 `weights_override` 若存在，会传递给 `evaluator.scalar_scores` 用于临时改变权重。

- `prototype_recommendation/evaluator.py`（已实现）
  - 说明：实现多目标评分与归一化工具，主要接口：
    - `score(path_item, S, learning_tree) -> dict`：返回原始指标字典 `{'E':..., 'D':..., 'R':..., 'P':...}`。
    - `normalize_scores(list_of_score_dicts) -> list_of_norm_dicts`：把每个维度归一化到 [0,1]（并对 D、R 做反向变换）。
    - `scalar_scores(norm_scores, weights=None) -> list_of_scalars`：按权重合成标量分。默认权重在文件顶部 `DEFAULT_WEIGHTS` 可配置。
  - 指标定义（当前实现）：
    - `E`: 新技能覆盖数 / 预计学习时间（效率，越大越好）
    - `D`: 路径平均难度 - 用户平均水平（差值为正表示过难，需反向处理）
    - `R`: 路径中未满足先修比例（越低越好，同样被反向处理）
    - `P`: 偏好契合度（占位，当前简单实现为默认值，可接入偏好匹配逻辑）
  - 具体函数实现与接口（中文说明）：
    - `score(path_item, S, learning_tree)`
      - 输入参数：
        - `path_item`：候选路径字典，含 `path`（节点 id 列表）、`cost`、`skills` 等
        - `S`：学生状态字典
        - `learning_tree`：学习树字典
      - 返回值：原始指标字典 `{'E': float, 'D': float, 'R': float, 'P': float}`。
    - `normalize_scores(score_dicts)`
      - 输入参数：候选的原始指标列表（List[Dict])
      - 返回值：归一化后的指标列表（List[Dict]，每项值在 [0,1]）。
    - `scalar_scores(norm_scores, weights=None)`
      - 输入参数：归一化指标列表，及可选权重字典 `weights`（例如 `{'E':0.4,'D':0.2,'R':0.2,'P':0.2}`）
      - 返回值：标量分列表（List[float]），顺序与输入 `norm_scores` 对应。

- `prototype_recommendation/pruning.py`（已实现）
  - 说明：提供后处理与替换算子：
    - `hard_prune(candidates, S)`: 基于用户硬约束（`max_total_time`, `deadline`, `blocked_nodes`）直接去除不合规候选。
    - `soft_prune_by_dominance(candidates, raw_scores)`: 基于 Pareto 非劣关系剔除被严格支配的候选（多目标软剪枝）。
    - `local_replace_candidates(candidates, learning_tree, S, max_attempts=100)`: 局部替换启发式：随机选择候选和路径位置、查找同一前驱下的“兄弟”节点进行单点替换，评估简单收益（如新增未掌握技能数 / 新成本），若改进则加入候选池以增加多样性与潜在解质量。
  - 参数调优点：`max_attempts`、替换采样策略、替换接受阈值（可改为更精确的 `evaluator.score` 比较）。
  - 具体函数实现与接口（中文说明）：
    - `hard_prune(candidates, S)`
      - 输入参数：
        - `candidates`：候选路径列表（List[Dict]）
        - `S`：学生状态字典（含约束）
      - 返回值：过滤后的候选列表（List[Dict]），剔除不满足硬约束的项。
    - `soft_prune_by_dominance(candidates, raw_scores)`
      - 输入参数：
        - `candidates`：候选路径列表
        - `raw_scores`：与之对应的原始指标字典列表（List[Dict])
      - 返回值：经 Pareto 剔除后的候选列表（List[Dict]）。
    - `local_replace_candidates(candidates, learning_tree, S, max_attempts=100)`
      - 输入参数：
        - `candidates`：当前候选列表（List[Dict]）
        - `learning_tree`：学习树字典
        - `S`：学生状态字典
        - `max_attempts`：尝试替换的最大次数（int）
      - 返回值：扩展/改进后的候选列表（List[Dict]），可能包含新加入的替换候选项。

- `prototype_recommendation/selector_ib_grpo.py`（已实现）
  - 说明：实现 IB-GRPO 策略选择器（核心为 `ib_grpo_select`），职责为最终决策与合规检查：
    - 输入：候选集 `P`、每条候选的原始 `raw_scores`、IB 约束（核心目标与阈值）、迭代次数、样本规模、最终输出 N 等。
    - 流程：过滤 -> IB 约束筛选（动态松弛）-> 多次随机化贪婪采样构造解集 -> 求 Pareto 前沿 -> 多样性修剪（Jaccard 相似度）-> 输出。
    - 可配置点：松弛步长、随机噪声幅度、迭代次数、diversity_beta、权重覆写接口。
    - Hooks/可控点：支持 `pre_select_hook` / `post_select_hook`、`weights_override`、`user_confirm` 流程以便接入管理员覆写或人工确认。
  - 审计：建议在此层记录完整审计日志（输入 `S`、候选摘要、`E/D/R/P`、归一化值、选中理由）。
  - 具体函数实现与接口（中文说明）：
    - `ib_grpo_select(P, raw_scores, IB_constraints, iterations=100, N=5, diversity_beta=0.5, weights_override=None, pre_select_hook=None, post_select_hook=None)`
      - 输入参数：
        - `P`：候选路径列表（List[Dict]）
        - `raw_scores`：每条候选对应的原始指标列表（List[Dict]）
        - `IB_constraints`：信息束约束定义（如 `{'E': {'min':0.2}, 'D': {'max':0.5}}`）
        - `iterations`：随机化贪婪迭代次数（int）
        - `N`：最终输出候选数上限（int）
        - `diversity_beta`：多样性剪枝参数（float）
        - `weights_override`：可选权重字典用于标量分计算
        - `pre_select_hook` / `post_select_hook`：可选回调函数用于在选择前后插入自定义逻辑
      - 返回值：最终选定的候选路径列表（List[Dict]），顺序为推荐优先级。

- `prototype_recommendation/run_demo.py`（已实现示例脚本）
  - 说明：示例流水线调用顺序和最小运行方式：
    - 步骤：`generate` -> `local_replace_candidates` -> `hard_prune` -> `evaluate (score + normalize + scalar)` -> `soft_prune_by_dominance` -> `ib_grpo_select`。
    - 运行方式（在仓库根目录）：
      ```bash
      python -c "import sys,os; repo=r'c:\\Users\\Lenovo\\Desktop\\基于动态知识图谱的RAG增强大模型辅助专家系统\\LianJue_Backend-main'; sys.path.insert(0, os.path.join(repo,'prototype_recommendation')); import run_demo as d; d.main()"
      ```
    - 输出：控制台打印候选、评分、最终选择示例（便于验证流程与手工检查）。
  - 主要入口与返回（中文说明）：
    - `main()`：无参数入口函数，读取示例数据并执行完整流水线。
      - 输入参数：无（运行时从示例数据模块读取）
      - 返回值：打印并返回最终选定的路径集合（List[Dict]，同时在控制台输出）。

- `prototype_recommendation/tests/`（已实现测试）
  - 说明：包含集成级测试：
    - `test_graph_adapter_integration.py`：使用 `InMemoryGraphAdapter` 验证 `generate(..., graph_adapter=adapter)` 能够产生到目标的路径并记录读计数。
    - `test_demo.py`：对 demo 流程的基本断言（演示示例，直接运行脚本可观察输出）。
  - 运行方式（无需 pytest，可直接以脚本方式导入运行 demo）：
    ```bash
    python -m pytest prototype_recommendation/tests/test_graph_adapter_integration.py -q
    # 或直接运行 demo
    python prototype_recommendation/run_demo.py
    ```
  - 说明：测试脚本可以直接作为示例运行，测试断言与示例数据位于 `prototype_recommendation/tests/`，每个测试文件顶部有说明如何以脚本方式运行。

**建议的下一步（Planned / Suggested Next Steps — 区分实现优先级）**
- 优先 (P0)：对生成阶段的评分调用做**批量化与缓存/批处理**，减少重复 `Evaluator.score` 开销；在 `candidate_generator` 中对每层评分次数设上限并批量调用 `evaluator`。
- 优先 (P0)：为早期软剪枝加入**可配置阈值**与**单元测试**覆盖，确保行为可控且可回溯。
- 优先 (P1)：在 `InMemoryGraphAdapter` 中添加 children 索引以加速 `expand()`（在树形子图上将从 O(N) 降为 O(children)）。
- 优先 (P1)：把评分与候选生成的耗时操作**并行化/异步化**，并在 Selector 端实现请求级时间预算（timeout）。
- 建议 (P2)：生产化 `KnowLionGraphAdapter`：验证真实服务返回格式、异常重试与分页、并加入集成基准测试。 
- 建议 (P2)：完善审计日志：在 `Selector` 中记录 `syllabus_version`、`learning_tree_version`、`user_profile_version`、候选集摘要与全部 `E/D/R/P` 向量，支持端到端回放。 
- 建议 (P2)：上线 A/B 实验与监控指标（完成率、转化率、满意度），并根据离线评估调优 IB 阈值与 GRPO 随机化率。


**多目标评估（评分设计）**
- 指标示例（按需扩展）:
  - 学习效率 (E): 覆盖新技能数量 / 预计学习时间
  - 难度匹配 (D): 路径平均难度与用户能力差距的惩罚
  - 风险/鲁棒性 (R): 依赖的未掌握先修比率
  - 偏好契合 (P): 格式、时长与用户偏好匹配度
- 每条路径 p 计算向量分数 v(p) = [E,D,R,P]
- 将向量归一化到同一尺度，例如归一化到 [0,1]

实现改进与工程化细节：

- **加权标量评分**: 在归一化后对每个指标使用可配置权重合成标量分数，便于快速排序与随机贪婪选择。默认权重示例：`E:0.4, D:0.2, R:0.2, P:0.2`。
- **归一化规则**: 对于 `D` 和 `R`（越小越好）先做反向变换再归一化，保证所有指标越大越好。
- **实现接口**: 提供 `score(path,S)->dict`（原始指标），`normalize_scores(list[dict])->list[dict]`，`scalar_scores(norm_scores, weights)->list[float]`。

**IB-GRPO 择优算法说明**
- 概念：在 Pareto 排序的基础上，引入信息束（Information Band / IB）对解集施加约束并用 GRPO（Greedy Randomized Pareto Optimization）进行多目标近似最优解选择。
- 步骤简述：
  1. 对候选集 P 做初步过滤（硬约束：时间、deadline、格式）
  2. 对每条路径计算 v(p)，并做归一化
  3. 建立信息束 IB：选择核心目标（例如 E 与 D），设定阈值区间（例如 E >= alpha, D <= beta）
  4. 在满足 IB 的解集中运行 GRPO：多次随机化贪婪选择并保留最优Pareto前沿的解（用于多样性）
  5. 剪枝策略：对Pareto前沿执行基于阈值和dominance的剪枝，保留 top-N


增强实现（IB-GRPO 细化）:

- 思路：结合归一化指标的 Pareto 筛选与随机化贪婪构造，加入 IB 动态松弛与多样性保留。
- IB 动态松弛：当没有候选满足初始 IB 阈值时，按照预设的松弛因子逐步降低阈值，直到获取可用池或达到最大尝试次数。
- 随机贪婪：在每次迭代从候选池采样若干解，按加权标量分数加少量噪声选择最优，重复多次以增加探索多样性。
- Pareto 前沿：对多次生成的解集合做归一化后求 Pareto 非劣前沿，保证输出解在多目标上是不可被支配的。
- 多样性修剪：对 Pareto 集合按标量分排序，然后贪婪选择 Top-N，同时用 Jaccard 相似度衡量技能覆盖的多样性并将多样性纳入选择打分，避免候选过于雷同。

伪代码（IB-GRPO 增强版）:

```
def ib_grpo_select(P, raw_scores, IB_constraints, iterations, N, diversity_beta):
  V_norm = normalize_scores(raw_scores)
  pool = filter_by_IB(V_norm, IB_constraints)
  if pool empty: relax IB thresholds until pool non-empty or attempts exhausted
  S = []
  for it in range(iterations):
    sample = random_sample(pool)
    pick = argmax(weighted_scalar(V_norm[sample]) + small_noise)
    S.append(pick)
  Pareto = pareto_frontier(S, V_norm)
  final = diversity_prune(Pareto, N, diversity_beta)
  return final
```

实现要点：阈值松弛步数与松弛因子、随机采样大小、迭代次数与 diversity_beta 均为可调超参数，建议通过离线探索或 A/B 测试调优。


**剪枝策略（工程化细化）**
- **硬剪枝（Hard prune）**: 在候选生成后立即剔除不满足用户硬约束的路径：
  - `max_total_time`：累计学习时间超过用户上限
  - `blocked_nodes`：用户显式屏蔽的节点
  - `deadline`：基于每日可用时长估算的完成时间超过 deadline
  实现注意：除在 `CandidateGenerator` 返回后执行硬剪枝外，建议在生成阶段同步进行早期软剪枝（对部分路径调用 `Evaluator.score` 并按标量分过滤），以进一步削减候选量和计算开销。早期软剪枝能在保证结果质量的前提下减少后续的评分与 Pareto 判定成本，但会增加生成阶段的计算（可通过缓存、并行和对评分次数做上限来控制）。
- **软剪枝（Soft prune）**: 在评分后剔除被其他候选严格支配的解（Pareto dominated），或总标量分低于阈值的解。
  - 优先做 Pareto 剔除以保证多目标覆盖；对剩余解再按标量分数或组合阈值做次级过滤。
- **层次/流水线剪枝**: 推荐流程为：候选生成 -> 硬剪枝 -> 评分 -> 软剪枝（Pareto） -> IB-GRPO 选择 -> 最终多样性剪枝。

实现样例：在 `prototype_recommendation/pruning.py` 提供 `hard_prune()` 与 `soft_prune_by_dominance()`，并在 `run_demo.py` 中演示调用顺序。

复杂度分析（粗略）:
- 候选生成：受束宽 `b` 和深度 `d` 影响，最坏情况 O(b * d * log(b))（每层排序的成本）。
- 硬剪枝：线性于候选数 O(|P| * L)（L 为路径平均长度）。
- 评分：O(|P| * L)（每条路径遍历节点计算指标）。
- 软剪枝（Pareto判定）：O(|P|^2 * m)（m 为指标维度），通常候选数通过前面步骤已受控。
- IB-GRPO 迭代选择：O(iterations * sample_size) + Pareto/多样性剪枝成本，整体依赖于 iterations 与样本规模。

工程建议：将候选生成和评分并行化；对长路径和大图增加时间预算和缓存启发/成本；对高并发场景把剪枝前的候选规模限制为 K_max（例如 200）。

**职责分层与决策流程**
- **职责分层（建议）**：采用多角色分层而非单一 agent：
  - **Generator Agent（候选生成）**：负责基于学习树与用户画像用 Beam/启发式策略生成候选路径（见 [prototype_recommendation/candidate_generator.py](prototype_recommendation/candidate_generator.py)）。
  - **Evaluator Agent（评估器）**：负责为每条候选路径计算可解释的多目标向量 `E/D/R/P` 并提供归一化/标量化工具（见 [prototype_recommendation/evaluator.py](prototype_recommendation/evaluator.py)）。
  - **Selector / Policy Agent（最终决策）**：负责运行 IB-GRPO 或策略模块做最终排序与输出，负责强制执行合规硬约束（时间、blocked nodes、deadline）、暴露 hook 供管理员/用户覆写权重或阈值，并记录决策审计（见 [prototype_recommendation/selector_ib_grpo.py](prototype_recommendation/selector_ib_grpo.py)）。
  - **Human-in-the-loop / UX**：当系统不确定或遇到敏感/高影响决策时，提供用户或教学管理员的覆写或确认流程。UI/UX 层应能展示可解释指标并支持交互式调整权重/阈值。

- **最终决定权**：建议将“最终路径决策权”归于 `Selector / Policy Agent`（代码实现为 `ib_grpo_select` 或上层 Policy），理由：该层聚合候选、评分与合规检查，最能综合多目标、策略与监管要求。为了可审计与可控，`Selector` 必须：
  - 始终在输出前执行硬约束检查（若不满足则拒绝或回退）
  - 记录决策上下文与解释性指标（用于日志与审计）
  - 暴露 hook/API，使管理员或用户在必要时覆写权重/阈值或触发人工确认（见 [prototype_recommendation/run_demo.py](prototype_recommendation/run_demo.py) 中的示例 hook 用法）

- **权威数据源与同步策略**：
  - **教学大纲（Syllabus） = 权威源**：将 Syllabus 作为能力定义、目标与推荐原则的权威来源，应做只读与版本化存储（DB 或 git）。任何策略更新必须以 Syllabus 的新版本为依据并保留版本号在决策上下文中。
  - **学习树（learning_tree）**：由 Syllabus 可执行化/索引化得到，它包含节点、先修、产出、估时等，是候选生成与图检索的实际图结构（建议在数据库中建立索引并版本化镜像）。
  - **用户画像（user_profile）**：运行时事实与偏好源，单独存储并实时更新（例如用户学习进度、已掌握技能、偏好与约束）。决策时将 `Syllabus`、`learning_tree` 与 `user_profile` 实时合并为 `S`。

- **实践建议**：
  - 把 `Syllabus` 作为只读/版本化资源（例如 `syllabus` 表 + `version` 字段或 git tag）；`learning_tree` 为其映射并可按版本生成索引化视图。
  - `user_profile` 为实时写入的运行库（单独表或 KV 存储），决策时从 `user_profile` 拉取当前状态并与 `learning_tree` 合并生成 `S`。
  - 在 `Selector` 中记录 `syllabus_version`、`learning_tree_version`、`user_profile_version` 与最终输出，以便审计与回溯。

- **实现要点与接口契约**：
  - `Generator` 提供：`generate(start_nodes, goals, S, opts) -> List[PathItem]`（见 [prototype_recommendation/candidate_generator.py](prototype_recommendation/candidate_generator.py)）。
  - `Evaluator` 提供：`score(path_item, S, learning_tree) -> dict(E,D,R,P)`、`normalize_scores(list)->list`、`scalar_scores(list,weights)->list`（见 [prototype_recommendation/evaluator.py](prototype_recommendation/evaluator.py)）。
  - `Selector` 提供：`select(candidates, raw_scores, opts) -> List[PathItem]`，并在实现中承担硬约束校验、IB-GRPO 策略、动态松弛与多样性剪枝（见 [prototype_recommendation/selector_ib_grpo.py](prototype_recommendation/selector_ib_grpo.py)）。
  - `GraphAdapter` 抽象用于在内存结构与真实图服务（KnowLion）间切换（见 [prototype_recommendation/graph_adapter.py](prototype_recommendation/graph_adapter.py)）。

- **合规、可控与 Human-in-loop**：
  - `Selector` 为最终输出权威，必要时支持“人工确认”模式：当候选集未达信心水平或命中合规边界时，暂停自动输出，呈现给管理员/用户确认。
  - 提供 audit log（包含输入 S、候选集摘要、每条路径的 `E/D/R/P`、归一化值、标量分与最终选择理由）以满足可解释性与监管需求。

- **剪枝与替换策略的职责边界**：
  - **Generator**：负责早期**硬剪枝**（blocked nodes、时间预算）与轻量启发式过滤（以控制爆炸）；可在每层做早期**软剪枝**（调用 `Evaluator.score` 生成标量分并截断 beam）。
  - **Pruning（后处理）**：在 `Generator` 返回后执行全局 `hard_prune()`，再由 `Evaluator` 完整评分并做 Pareto/软剪枝（`soft_prune_by_dominance()`），随后由 `Selector` 应用 IB-GRPO 与多样性剪枝。替换算子 `local_replace_candidates()` 在生成后、硬剪枝前作为候选增强步骤执行（见 [prototype_recommendation/pruning.py](prototype_recommendation/pruning.py)）。

- **日志、监控与测试**：
  - 在关键节点（生成、评分、选择）采集指标：候选数、每层扩展量、评分次数、平均标量分分布、选择稳定性等。
  - 提供端到端回放/回溯能力：记录请求输入、使用的 syllabus/version、生成候选、所有评分向量与最终决策，以便离线分析与 A/B 测试。

**接口与组件契约**
- `Perception` 服务
  - 输入：`UserProfile`、学习记录
  - 输出：`S`（状态向量）、`start_nodes`
- `CandidateGenerator` 类
  - 方法：`generate(start_nodes, goals, opts) -> List[Path]`
- `Evaluator` 类
  - 方法：`score(path, S) -> dict(metrics)`
- `Selector` 类（IB-GRPO）
  - 方法：`select(candidates, scores, opts) -> List[Path]`


**补充说明：最终决定权、覆写机制与数据源责任**

- **最终决定权归属**：`Selector / Policy Agent`（实现为 `ib_grpo_select`）承担最终路径决策权。该层负责合规性检查（硬约束）、IB-GRPO 策略执行与多样性剪枝，且必须在输出前记录完整审计上下文。
- **暴露覆写与 Hook 机制**：`Selector` 应提供清晰的 extension points：`pre_select_hook`、`post_select_hook`、`weights_override` 与 `threshold_override`。管理员或策略模块可通过这些接口临时覆写权重/阈值或注入自定义过滤逻辑；当系统信心水平不足或触发合规边界时，应进入 Human-in-the-loop 流程，等待人工确认或覆写后再输出。
- **权威源与版本化**：
  - `Syllabus`（教学大纲）为权威源，定义学习目标、能力维度与推荐原则。应以只读且版本化的方式存储（例如数据库的 `syllabus` 表带 `version` 字段或使用 git 存储并打 tag），任何策略更新需记录对应 `syllabus_version`。
  - `learning_tree` 为 `Syllabus` 的可执行化/索引化映射，包含节点、先修、估时与产出。`learning_tree` 应按 `syllabus_version` 生成并单独版本化（便于回放与回溯），同时在数据库中建立索引以加速检索与 expand 操作。
  - `user_profile` 为运行时存储（单独表或 KV 存储），实时更新用户掌握事实、偏好与约束。决策时在运行时把 `syllabus`（指定版本），对应的 `learning_tree` 版本，与当前 `user_profile` 合并为决策上下文 `S`。
- **审计与回放字段**：`Selector` 在日志中必须记录 `syllabus_version`、`learning_tree_version`、`user_profile_version`、候选集摘要、所有 `E/D/R/P` 向量、归一化值与最终选中理由，以支持端到端回放、离线分析与 A/B 对比。
- **存储与接口建议**：
  - `Syllabus`: 只读 + 版本化（DB 或 git）；变更需触发 `learning_tree` 重新构建并更新索引。
  - `learning_tree`: 以 `syllabus_version` 为键的索引化视图（可缓存），并提供快速的 `expand(node_id)` 与 `ancestors/descendants` 查询。
  - `user_profile`: 实时写入的运行库（KV 或表），决策时拉取并合并为 `S`，对外提供 `get_profile(user_id)` 与 `snapshot(user_id, timestamp)` 接口便于回放。







