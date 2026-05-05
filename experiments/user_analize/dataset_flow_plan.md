# 画像构建实验收口方案

## 0. 目标与固定前提

本方案服务于**学习画像构建算法**，不是服务于 RAG 回答评测本身。

本轮实验固定前提如下：

- 图数据库检索图名固定为：`RAG`
- syllabus 固定为：
  - `E:\AI\Learning-Platform\Lianjue_Backend\schedule\syllabus\大数据概论_20260322235507.json`

本轮实验不追求全量真实生产数据，而是先构建一套**可重复、可解释、可对照**的数据集与函数流。

实验目标收口为四件事：

1. 数据集：收口并逐个产生
2. 函数级数据流：按实验逐步收口
3. 输入输出与精度口径：按函数收口
4. 实验报告：形成固定模板和后续填报计划

## 1. 数据集方案

本轮建议构建 4 组数据集，分别对应不同实验目的。

---

### 数据集 A：课程基准数据集

#### 用途

- 作为画像算法的课程知识基线
- 作为知识点、周次、主题范围的标准来源
- 支撑“课程进度特征”“知识点映射”“答题归因”等实验

#### 数据来源

直接取自 syllabus 本身，不需要额外生成：

- `title`
- `day_one`
- `graph_name`
- `period[*].week_index`
- `period[*].content`
- `period[*].enhanced_content`
- `period[*].importance`

#### 是否需要生成

需要做**轻量派生**，但不需要生成新语义内容：

- `week_topic_summary`
- `week_keyword_candidates`
- `week_difficulty_prior`

这些派生字段可以通过规则或简单抽取生成，目的只是方便后续特征计算，不改变 syllabus 原意。

#### 结论

这部分应**优先直接取用 syllabus**，不要让 LLM 再次改写课程内容。

---

### 数据集 B：行为画像样本集

#### 用途

- 支撑 `learning_records` / `resource_usage` 相关实验
- 用于验证活跃度、学习时长、注意力模式、资源偏好等特征

#### 数据来源

当前仓库没有成体系的真实行为数据，因此建议：

- 先基于 syllabus 周次构造一批**半合成行为样本**
- 样本结构保持与目标接口一致

建议字段：

- `user_id`
- `syllabus_id`
- `event_type`
- `started_at`
- `duration_minutes`
- `source`
- `meta.topic`
- `meta.week_index`

#### 是否需要生成

这部分**需要生成**，而且生成比硬等真实数据更合理。

原因：

- 真实行为数据当前并未在仓库中完备落地
- 行为实验关注的是特征计算链路，不是数据真实性审计
- 合成样本更容易覆盖高活跃、低活跃、突发下降、偏视频、偏练习等边界情况

#### 生成原则

- 生成样本必须围绕 syllabus 的周次内容
- 每条行为记录应能映射到具体 `week_index`
- 至少覆盖 4 类用户画像原型：
  - 高活跃稳定型
  - 低活跃风险型
  - 临时冲刺型
  - 资源偏好明显型

---

### 数据集 C：答题画像样本集

#### 用途

- 支撑 `answer_records`、`knowledge_mastery`、`concept_gaps` 实验
- 验证知识点级掌握度、尝试次数、答题正确率等特征

#### 数据来源

建议采用“syllabus 派生 + 测试用例补充”的方式：

- syllabus 的 `period[*].content` / `enhanced_content`
- `测试用例.md` 中已有的课程问答题目

#### 是否需要生成

这部分建议**混合处理**：

- 知识范围和题目主题：直接取自 syllabus 与 `测试用例.md`
- 具体 `answer_records`：按实验需要生成

建议生成字段：

- `question_id`
- `week_index`
- `knowledge_points`
- `correct`
- `score`
- `answered_at`
- `time_spent_seconds`

#### 为什么这样更合理

- 题目主题必须贴 syllabus，不然无法验证画像是否真正围绕课程
- 但答题表现本身属于学习行为，不太可能只从 syllabus 直接获得
- 所以“题目来源真实、答题结果合成”是目前最稳妥的办法

---

### 数据集 D：对话画像样本集

#### 用途

- 支撑 `dialogue_text`、`learning_goal`、`goal_clarity`、`term_familiarity`、`emotion_state` 等实验
- 用于测 LLM/规则在主观文本理解上的稳定性

#### 数据来源

可用的现成数据非常有限：

- `history/8_1.json` 可作为少量真实风格参考
- `schedule/student_alt/user_1/8_personal.json` 可作为“课程周次 + 学习状态”参考

#### 是否需要生成

这部分**需要生成**，且生成是合理的。

建议生成 3 层对话样本：

1. 简单提问型
2. 带学习目标型
3. 带情绪和困难陈述型

每条样本都应显式标注：

- 关联周次
- 目标清晰度预期
- 术语熟悉度预期
- 情绪预期
- 求助意愿预期

#### 生成原则

- 语言风格要贴学生，不要写成说明文
- 必须围绕 syllabus 已有内容
- 同一知识点至少准备：
  - 表面提问
  - 深入提问
  - 混乱提问

## 2. 哪些直接取，哪些生成

### 直接取用更合理的部分

- syllabus 全量结构
- `graph_name = RAG`
- 周次、课程主题、课程节奏
- 历史问答样式参考
- personal syllabus 的 `competance` / `competance_progress` 样式
- `测试用例.md` 的题目主题

### 生成更合理的部分

- `learning_records`
- `answer_records`
- `resource_usage`
- 多轮 `dialogue_text`
- `learning_goal`
- 面向画像的“标准答案标签”，例如预期风险、预期资源偏好、预期情绪状态

### 原则

一句话收口：

> 课程知识边界直接取 syllabus；学习行为和主观表达用合成样本补齐。

## 3. 各实验的数据流收口

下面只保留真正服务画像算法的实验流。

---

### 实验 1：输入可得性与规范化实验

#### 目标

验证输入字段是否能稳定进入统一结构。

#### 输入

- syllabus 基准数据
- 合成的 `dialogue_text`
- 合成的 `learning_goal`
- 合成的 `learning_records`
- 合成的 `answer_records`
- 合成的 `resource_usage`

#### 数据流

1. 原始样本
2. 请求级预处理
3. 时间字段标准化
4. 事件结构标准化
5. 输出统一 `profile_input_bundle`

#### 输出

- 标准化后的输入对象
- 缺失字段报告
- 异常格式报告

---

### 实验 2：对话特征实验

#### 目标

验证对话输入是否能稳定产出主观特征。

#### 输入

- `dialogue_text`
- `learning_goal`
- syllabus 周次上下文

#### 数据流

1. 读取对话样本
2. 绑定对应周次内容
3. 调用对话特征函数
4. 输出结构化对话特征

#### 输出

- `goal_clarity`
- `term_familiarity`
- `help_seeking_level`
- `self_reported_difficulty`
- `emotion_state`

---

### 实验 3：行为特征实验

#### 目标

验证行为记录是否能稳定产出学习节奏与资源偏好特征。

#### 输入

- `learning_records`
- `resource_usage`

#### 数据流

1. 读取行为样本
2. 归一化时长与时间
3. 聚合近 7 天 / 30 天指标
4. 输出行为特征

#### 输出

- `study_frequency`
- `study_duration`
- `attention_pattern`
- `resource_preference`
- `learning_style`

---

### 实验 4：答题掌握度实验

#### 目标

验证答题样本是否能支持知识点级掌握度。

#### 输入

- `answer_records`
- syllabus 周次内容

#### 数据流

1. 读取答题样本
2. 绑定 `knowledge_points`
3. 聚合尝试次数、正确率、时间衰减
4. 输出掌握度特征

#### 输出

- `knowledge_mastery.answer_score`
- `knowledge_mastery.by_knowledge_point`
- `knowledge_mastery.knowledge_point_details`
- `concept_gaps`

---

### 实验 5：课程进度与风险融合实验

#### 目标

验证 `personal_syllabus + 行为 + 答题 + 对话` 融合后的画像是否合理。

#### 输入

- `personal_syllabus`
- 对话特征结果
- 行为特征结果
- 答题特征结果

#### 数据流

1. 读取 personal syllabus
2. 提取 `competance` / `competance_progress`
3. 融合行为、答题、对话信号
4. 产出风险、证据、总画像

#### 输出

- `knowledge_mastery.overall_score`
- `dropout_risk`
- `dropout_risk_score`
- `recent_anomaly`
- `evidence`
- `confidence`

## 4. 函数设计收口

建议把函数拆成四层。

### 4.1 数据集构建层

- `load_syllabus_base_dataset()`
- `build_dialogue_dataset()`
- `build_learning_records_dataset()`
- `build_answer_records_dataset()`
- `build_resource_usage_dataset()`
- `build_personal_syllabus_dataset()`

### 4.2 规范化层

- `normalize_profile_request()`
- `normalize_dialogue_input()`
- `normalize_learning_records()`
- `normalize_answer_records()`
- `normalize_resource_usage()`
- `merge_profile_events()`

### 4.3 特征计算层

- `compute_dialogue_features()`
- `compute_behavior_features()`
- `compute_resource_features()`
- `compute_answer_mastery_features()`
- `compute_syllabus_mastery_features()`
- `compute_risk_features()`

### 4.4 汇总层

- `resolve_profile_conflicts()`
- `build_profile_evidence()`
- `build_profile_confidence()`
- `assemble_profile_output()`

## 5. 输入输出精确度收口

这里的“精确度”不只指数值误差，而是指函数边界与输出口径是否稳定。

### 对数据集构建函数的要求

- 输出结构固定
- 每条样本必须携带 `sample_id`
- 尽量携带 `week_index`
- 必须可复现

### 对规范化函数的要求

- 所有时间字段统一输出成同一格式
- 所有事件字段统一映射为标准键
- 空值处理规则固定

### 对特征计算函数的要求

- 输入字段清单固定
- 输出字段名与画像契约对齐
- 数值范围尽量统一为 `0~1`
- 枚举值集合固定

### 对汇总函数的要求

- 输出必须严格落到 `profile` 结构
- `evidence` 必须能回溯到输入信号
- `confidence` 必须有明确生成口径

## 6. 实验报告构建计划

建议每个实验单独一份记录，最后再汇总。

目录建议：

- `experiments/user_analize/experiment_plan.md`
- `experiments/user_analize/dataset_flow_plan.md`
- `experiments/user_analize/reports/`
- `experiments/user_analize/outputs/`
- `experiments/user_analize/samples/`

### 单实验报告模板

每个实验报告固定 4 段：

1. 实验准备
2. 数据来源
3. 实验记录
4. 实验结论

### 汇总报告建议结构

最终汇总报告可命名为：

- `experiments/user_analize/reports/profile_algorithm_summary.md`

建议结构：

1. 数据集说明
2. 规范化结果
3. 各特征实验结果
4. 融合画像结果
5. 当前可信字段
6. 当前高风险字段
7. 后续 Agent 化建议

## 7. 下一步建议

按这个收口方案，接下来最合理的落地顺序是：

1. 先生成 4 组数据集
2. 再写规范化函数
3. 再写特征实验脚本
4. 最后写汇总画像实验和报告

一句话收口：

> 先把“课程知识边界”固定在 syllabus 上，再把“学习行为与对话表达”做成可控样本集，最后用函数级数据流去验证画像算法本身。
