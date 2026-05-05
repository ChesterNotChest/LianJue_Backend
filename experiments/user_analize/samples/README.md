# 第一批画像实验数据集

本目录放第一批“画像构建算法”实验样本，固定约束如下：

- 图数据库固定为 `RAG`
- 课程边界固定取 `source_refs/syllabus_大数据概论_20260322235507.json`
- 题目主题固定参考 `source_refs/测试用例.md`
- 对话风格固定参考 `source_refs/history_8_1.json`
- `competance` / `competance_progress` 结构固定参考 `source_refs/student_alt_user_1_8_personal.json`

当前批次包含 4 个用户原型：

- `steady_mastery_builder`：稳定投入、目标清晰、低风险
- `low_activity_risk`：低活跃、知识遗忘明显、高风险
- `deadline_crammer`：考前突击、短期活跃高、风险中等
- `visual_practice_seeker`：资源偏好明显、愿意求助、风险较低

文件说明：

- `source_refs/`：分发用参考源文件镜像，避免依赖仓库其它目录
- `dataset_index.json`：样本总清单
- `syllabus_base_dataset.json`：课程基准数据集，直接取 syllabus 并补轻量派生字段
- `question_bank_dataset.json`：从 `测试用例.md` 收口出的题目主题样本
- `dialogue_profile_dataset.json`：对话与学习目标样本
- `learning_records_dataset.json`：学习行为样本
- `answer_records_dataset.json`：答题记录样本
- `resource_usage_dataset.json`：资源使用样本
- `personal_syllabus_dataset.json`：个人 syllabus 快照样本
- `profile_input_bundles.json`：可直接供后续规范化函数消费的合并输入
- `ablation_bundles.json`：字段贡献度 / 消融实验配置
- `edge_case_bundles.json`：边界输入与脏数据实验配置
- `stability_eval_set.json`：重复运行稳定性实验清单
- `manual_review_set.json`：人工复核实验清单与审阅重点

约束说明：

- 时间字段故意保留了 `unix timestamp`、`ISO 8601` 和常见非标准字符串三种格式，用于下一步输入规范化实验。
- `profile_input_bundles.json` 不内嵌 `personal_syllabus`，只保留对应样本引用，避免把“融合实验输入”和“基础输入规范化”混在一起。
- 消融集和边界集采用“基准 bundle + 变体模板”的方式定义，避免重复拷贝大 JSON。
- 需要分发的原始 syllabus、题单、history、personal syllabus 参考文件都已复制到 `source_refs/`，`samples/` 目录现在是自包含的。
