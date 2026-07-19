# 项目测试文档 - 系统测试

## 4 系统测试

### 4.1 RAG性能测试

#### 4.1.1 测试用例与结果分析

RAG 性能测试数据来自 `experiments/RAG/eval_outputs/`。测试样本规模为 50 个问题，覆盖通用提问、专业性提问和习题提问等类型。测试指标包括检索精确率、召回率、平均检索耗时和 RAG 对幻觉率的影响。

##### 系统测试用例 ST-04-001：RAG检索精确率测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-001 |
| 测试单元描述 | 对 RAG 检索返回结果进行 LLM Judge 精确率评测 |
| 用例目的 | 验证检索结果与问题语义是否匹配，重点关注 TOP1 和 TOP3 返回质量 |
| 前提条件 | RAG 图谱构建完成；评测问题集准备完成；`precision_llm_judge_summary.csv` 可读取 |
| 特殊的规程说明 | 使用既有 experiments 数据进行整理，不重新生成评测；TOP3 准确率作为主要验收指标 |
| 用例间的依赖关系 | 与 ST-04-002 共同评估 RAG 检索质量 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取精确率评测结果 | `precision_llm_judge_summary.csv` | 能读取 TOP1、TOP3 的正确数、错误数和准确率 | 文件中包含 TOP1、TOP3 汇总 | 数据来源：`experiments/RAG/eval_outputs/` |
| 2 | 统计 TOP1 精确率 | 50 条评测样本 | TOP1 准确率不低于阶段可接受阈值 | TOP1 正确 44 条，错误 6 条，准确率 0.88 | 判定通过 |
| 3 | 统计 TOP3 精确率 | 50 条评测样本 | TOP3 准确率不低于 0.90 | TOP3 正确 47 条，错误 3 条，准确率 0.94 | 作为主要验收指标 |
| 4 | 形成结论 | TOP1/TOP3 结果 | 检索结果整体可用于学习问答 | TOP3 精确率达到阶段要求 | 建议继续优化 TOP1 排序 |

精确率汇总表如下：

| 指标 | 正确数 | 错误数 | 脏数据数 | 准确率 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| TOP1 精确率 | 44 | 6 | 0 | 0.88 | 通过 |
| TOP3 精确率 | 47 | 3 | 0 | 0.94 | 通过 |

##### 系统测试用例 ST-04-002：RAG检索召回率测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-002 |
| 测试单元描述 | 对 RAG 检索结果进行召回率评测 |
| 用例目的 | 验证相关证据是否能够在 TOP1、TOP3、TOP5 范围内被检索出来 |
| 前提条件 | RAG 图谱构建完成；召回评测数据已生成；`recall_llm_judge_summary.csv` 可读取 |
| 特殊的规程说明 | TOP5 召回率作为主验收指标；TOP1 召回率作为排序优化参考 |
| 用例间的依赖关系 | 与 ST-04-001 共同评估 RAG 检索质量 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取召回率评测结果 | `recall_llm_judge_summary.csv` | 能读取 TOP1、TOP3、TOP5 命中率 | 文件中包含三组召回指标 | 数据来源：`experiments/RAG/eval_outputs/` |
| 2 | 统计 TOP1 召回率 | 50 条评测样本 | TOP1 命中情况可作为排序质量参考 | TOP1 命中 31 条，未命中 19 条，命中率 0.62 | 需优化 |
| 3 | 统计 TOP3 召回率 | 50 条评测样本 | TOP3 命中率应接近可用水平 | TOP3 命中 44 条，未命中 6 条，命中率 0.88 | 基本可用 |
| 4 | 统计 TOP5 召回率 | 50 条评测样本 | TOP5 命中率不低于 0.90 | TOP5 命中 48 条，未命中 2 条，命中率 0.96 | 通过 |

召回率汇总表如下：

| 指标 | 命中数 | 未命中数 | 脏数据数 | 命中率 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| TOP1 召回率 | 31 | 19 | 0 | 0.62 | 需优化 |
| TOP3 召回率 | 44 | 6 | 0 | 0.88 | 基本通过 |
| TOP5 召回率 | 48 | 2 | 0 | 0.96 | 通过 |

##### 系统测试用例 ST-04-003：RAG检索速度测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-003 |
| 测试单元描述 | 对 RAG 图谱检索的 embedding、retrieval-only 和 total time 进行统计 |
| 用例目的 | 验证 RAG 检索耗时是否能够支撑交互式学习问答 |
| 前提条件 | RAG 图谱服务可用；速度评测报告已生成；`retrieval_speed_report.md` 可读取 |
| 特殊的规程说明 | 本用例使用 50 个 case，每个 case 重复 3 次，Top-k=5 |
| 用例间的依赖关系 | 与 ST-04-001、ST-04-002 共同评估 RAG 综合可用性 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取速度评测报告 | `retrieval_speed_report.md` | 能读取 case count、Top-k、重复次数和平均耗时 | 报告可读取 | 数据来源：`experiments/RAG/eval_outputs/` |
| 2 | 统计 embedding 平均耗时 | 50 个问题，重复 3 次 | embedding 耗时可被单独统计 | Avg embed time = 258.87 ms | 可接受 |
| 3 | 统计 retrieval-only 平均耗时 | Top-k=5 | 检索主体耗时可被单独统计 | Avg retrieval-only time = 3143.737 ms | 可接受但仍可优化 |
| 4 | 统计 total 平均耗时 | embedding + retrieval | 平均总耗时可用于交互式学习 | Avg total time = 3402.608 ms | 通过 |

速度测试汇总表如下：

| 指标 | 数值 |
| --- | ---: |
| Graph | RAG |
| Case count | 50 |
| Top-k | 5 |
| Repeats per case | 3 |
| Warmup cases | 1 |
| Avg embed time | 258.87 ms |
| Avg retrieval-only time | 3143.737 ms |
| Avg total time | 3402.608 ms |

##### 系统测试用例 ST-04-004：RAG降低幻觉率测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-004 |
| 测试单元描述 | 对比 LLM 与 LLM w/RAG 的回答幻觉率 |
| 用例目的 | 验证 RAG 检索证据是否能够降低回答幻觉 |
| 前提条件 | 幻觉率评测文件已生成；`hallucination_llm_judge_summary.csv` 可读取 |
| 特殊的规程说明 | 本用例关注相对改善，即 RAG 模式幻觉率应低于无 RAG 基线 |
| 用例间的依赖关系 | 依赖 RAG 检索链路可用 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取幻觉率汇总 | `hallucination_llm_judge_summary.csv` | 能读取 LLM 和 LLM w/RAG 两组数据 | 文件包含两组模型结果 | 数据来源：`experiments/RAG/eval_outputs/` |
| 2 | 统计无 RAG 基线 | LLM 结果 | 得到无 RAG 幻觉率 | 无幻觉 47 条，幻觉 3 条，幻觉率 6.00% | 基线 |
| 3 | 统计 RAG 模式 | LLM w/RAG 结果 | 得到 RAG 模式幻觉率 | 无幻觉 48 条，幻觉 2 条，幻觉率 4.00% | 优于基线 |
| 4 | 形成结论 | 两组幻觉率 | RAG 幻觉率低于无 RAG | 4.00% < 6.00% | 通过 |

幻觉率对比表如下：

| 模式 | 无幻觉数 | 幻觉数 | 幻觉率 | 结果 |
| --- | ---: | ---: | ---: | --- |
| LLM | 47 | 3 | 6.00% | 基线 |
| LLM w/RAG | 48 | 2 | 4.00% | 优于基线 |

#### 4.1.2 测试结果综合分析及建议

RAG 系统测试结果显示，TOP3 精确率达到 0.94，TOP5 召回率达到 0.96，说明检索增强在多数学习问题下能够返回可用证据。RAG 模式幻觉率为 4.00%，低于无 RAG 的 6.00%，说明检索证据对回答可信度有正向作用。

当前主要优化点是 TOP1 召回率，现有结果为 0.62，说明第一条返回结果不总是最佳证据。建议后续优化排序策略、章节权重、问题类型识别和重排模型，使第一条证据更稳定。同时，平均总耗时约 3.40 秒，可支持普通学习问答；若面向更强实时交互场景，可继续优化 embedding 缓存、图谱索引和并发检索。

### 4.2 画像准确性分析

#### 4.2.1 测试用例与结果分析

画像准确性分析数据来自 `experiments/user_analize/outputs/`。实验包含基础画像样本、消融样本、边界样本、稳定性目标、人工复核和产物可用性检查。该部分用于验证学习画像是否能够区分不同学生状态，并对缺失字段、异常事件和空行为等输入给出合理处理。

##### 系统测试用例 ST-04-005：基础画像区分度测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-005 |
| 测试单元描述 | 对四类典型学生画像样本进行掌握度、风险等级和薄弱点分析 |
| 用例目的 | 验证画像结果能够区分稳定掌握、低活跃风险、临近截止冲刺和视觉练习偏好等学习状态 |
| 前提条件 | `base_profile_summary.md` 可读取；基础画像样本已生成 |
| 特殊的规程说明 | 本用例关注画像结果的相对区分度，不以单个分值作为唯一判断 |
| 用例间的依赖关系 | 为推荐路径、资源策略和学伴交互提供画像质量依据 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取基础画像样本 | `base_profile_summary.md` | 读取 4 类 persona 的画像结果 | 文件包含 4 条基础画像记录 | 数据来源：`experiments/user_analize/outputs/tables/` |
| 2 | 检查掌握度分布 | Overall score | 不同 persona 分数存在明显差异 | 分数范围 0.2442 至 0.7928 | 具备区分度 |
| 3 | 检查风险等级 | Risk level、Risk score | 低活跃和冲刺样本风险较高 | `low_activity_risk`、`deadline_crammer` 为 high | 通过 |
| 4 | 检查薄弱点数量 | Concept gaps、Weak weeks | 高风险样本薄弱点更多 | 低活跃样本 concept gaps=11 | 通过 |

基础画像结果如下：

| Persona | Overall score | Confidence | Risk level | Risk score | Concept gaps | Weak weeks |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| steady_mastery_builder | 0.7928 | 0.84 | medium | 0.44 | 4 | 1 |
| low_activity_risk | 0.2442 | 0.84 | high | 0.95 | 11 | 2 |
| deadline_crammer | 0.4871 | 0.84 | high | 0.74 | 6 | 3 |
| visual_practice_seeker | 0.6874 | 0.84 | medium | 0.45 | 4 | 1 |

##### 系统测试用例 ST-04-006：画像边界输入容错测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-006 |
| 测试单元描述 | 对缺失目标、缺失知识点、空行为、非法事件类型等边界样本进行画像容错验证 |
| 用例目的 | 验证画像模块遇到不完整或异常输入时不崩溃，并能输出 warning、missing fields 或 format issues |
| 前提条件 | `edge_case_summary.md` 可读取；边界样本已生成 |
| 特殊的规程说明 | 出现 issue 并不等同于测试失败，关键是能被识别、记录和降级处理 |
| 用例间的依赖关系 | 与画像 API、Total Agent 画像读取降级能力相关 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取边界样本表 | `edge_case_summary.md` | 读取 7 条边界用例 | 文件包含 7 条边界记录 | 数据来源：`experiments/user_analize/outputs/tables/` |
| 2 | 检查缺失字段处理 | missing goal、missing knowledge points | 缺失字段被记录，不导致画像失败 | 两类缺失样本 Total issues 均为 2 | 通过 |
| 3 | 检查空行为处理 | empty behavior arrays | 输出较低 confidence 和 high risk | confidence=0.56，Total issues=4 | 符合预期 |
| 4 | 检查非法事件处理 | invalid event type | 记录 format issue | format issues=1 | 通过 |
| 5 | 检查非标准时间和重复资源 | nonstandard time、duplicate resource | 可降级处理，无总问题或少量 warning | 多个样本 Total issues=0 | 通过 |

边界样本结果如下：

| Case ID | Template | Confidence | Risk level | Warnings | Missing fields | Format issues | Total issues |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| edge_s02_empty_behavior | edge_empty_behavior_arrays | 0.56 | high | 2 | 2 | 0 | 4 |
| edge_s01_missing_goal | edge_missing_learning_goal | 0.81 | medium | 1 | 1 | 0 | 2 |
| edge_s01_missing_knowledge_points | edge_missing_knowledge_points | 0.81 | medium | 1 | 1 | 0 | 2 |
| edge_s03_invalid_event_type | edge_invalid_event_type | 0.815 | high | 1 | 0 | 1 | 2 |
| edge_s02_nonstandard_time | edge_nonstandard_time_mix | 0.84 | high | 0 | 0 | 0 | 0 |
| edge_s03_week_mismatch | edge_week_index_mismatch | 0.84 | high | 0 | 0 | 0 | 0 |
| edge_s04_duplicate_resource | edge_duplicate_resource_events | 0.84 | medium | 0 | 0 | 0 | 0 |

##### 系统测试用例 ST-04-007：画像人工复核覆盖测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-007 |
| 测试单元描述 | 对画像人工复核样本进行优先级和关注字段统计 |
| 用例目的 | 验证高风险画像能够进入人工复核范围，并保留需要关注的字段 |
| 前提条件 | `manual_review_summary.md` 可读取；人工复核样本已整理 |
| 特殊的规程说明 | 人工复核用于补充自动化指标，不替代自动化画像结构检查 |
| 用例间的依赖关系 | 与画像质量闭环和后续风险阈值校准相关 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取人工复核汇总 | `manual_review_summary.md` | 读取 high、medium 复核统计 | 文件包含 high 和 medium 两类 | 数据来源：`experiments/user_analize/outputs/tables/` |
| 2 | 检查 high 优先级数量 | high priority | 高风险样本进入复核 | high 复核数 4 条 | 通过 |
| 3 | 检查关注字段数量 | Total focus fields、Average focus fields | 每条复核样本保留多个关注字段 | high 平均 3.75，medium 平均 3.50 | 通过 |
| 4 | 形成质量建议 | 复核统计 | 输出画像校准建议 | 建议保留复核结论和风险阈值校准记录 | 后续改进 |

人工复核结果如下：

| Priority | Review count | Total focus fields | Average focus fields |
| --- | ---: | ---: | ---: |
| high | 4 | 15 | 3.75 |
| medium | 2 | 7 | 3.50 |

##### 系统测试用例 ST-04-008：画像产物可用性测试

| 项目 | 内容 |
| --- | --- |
| 用例编号 | ST-04-008 |
| 测试单元描述 | 对画像实验生成的样本文件、报告文件和 bundle 产物进行可用性检查 |
| 用例目的 | 验证画像评测产物完整、可读取，并且没有记录产物级问题 |
| 前提条件 | `profile_asset_validation_summary.json` 可读取 |
| 特殊的规程说明 | 产物可用性只说明文件与报告结构完整，不直接代表画像业务质量完全正确 |
| 用例间的依赖关系 | 为 ST-04-005、ST-04-006、ST-04-007 提供数据可信度支撑 |

| 具体步骤 | 输入 | 期望输出 | 实际输出 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 读取产物校验摘要 | `profile_asset_validation_summary.json` | 文件可读取并包含检查统计 | 摘要文件可用 | 数据来源：`experiments/user_analize/outputs/` |
| 2 | 检查样本和报告数量 | sample/report count | 检查样本和报告文件数量明确 | checked_sample_file_count=13，checked_report_file_count=2 | 通过 |
| 3 | 检查 bundle 和边界样本数量 | profile_bundle_count、edge_case_count | 画像 bundle 和边界样本存在 | profile_bundle_count=4，edge_case_count=7 | 通过 |
| 4 | 检查 issue 数 | issue_count | 产物问题数为 0 | issue_count=0 | 通过 |

画像实验总体数据如下：

| 指标 | 数值 |
| --- | ---: |
| 基础画像样本数 | 4 |
| 消融样本数 | 24 |
| 边界样本数 | 7 |
| 稳定性目标数 | 5 |
| 人工复核样本数 | 6 |
| 检查样本文件数 | 13 |
| 检查报告文件数 | 2 |
| 画像 bundle 数 | 4 |
| 产物问题数 | 0 |

#### 4.2.2 测试结果综合分析及建议

画像准确性分析显示，系统能够区分不同学习状态，并对高风险学生给出较高 risk score。`low_activity_risk` 的 Overall score 为 0.2442、Risk score 为 0.95，`deadline_crammer` 的 Risk score 为 0.74，均被识别为 high risk；稳定掌握和视觉练习偏好样本为 medium risk，说明风险评估具备基本区分度。

边界样本中，空行为、缺失目标、缺失知识点和非法事件类型均能被记录为 warning、missing fields 或 format issues。该结果说明画像模块具备基本输入质量检测能力，可以为 Total Agent 降级处理和前端提示提供依据。

后续建议包括：进一步校准 high/medium 风险阈值；复核 `confidence=0.84` 集中现象；为缺失字段样本提供更明确的前端提示；保留人工复核结论，形成可追溯的画像质量闭环。
