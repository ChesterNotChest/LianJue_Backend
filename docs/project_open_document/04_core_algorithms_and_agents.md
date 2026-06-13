# 4 核心算法与智能体机制

## 4.1 多智能体协同机制

系统的多 Agent 机制以 Total Agent 为总编排入口。Total Agent 不把所有能力塞进一个提示词，而是将上下文加载、意图识别、证据检索、路径推荐、资源生成、即时答疑、学习反馈和成长树同步拆分为可测试工具链。

核心设计点：

- 用结构化 state 和 payload 串联工具。
- 用 `tool_trace` 和 `tool_status_events` 暴露运行过程。
- 用专项模块保持职责边界。
- 用 E2E 测试验证跨模块闭环。

待补图：多 Agent 协同状态图。

## 4.2 学习画像构建

学习画像模块从用户目标、历史学习事件、个人教学大纲和课程上下文中抽取学生状态。画像不是一次性表单，而是可读取、可构建、可更新的动态结构。

核心输出包括：

- 学习目标。
- 薄弱知识点。
- 偏好资源类型。
- 风险或节奏信号。
- 个人教学大纲建议。

画像用于推荐路径、资源生成策略和 QA 策略，但不应把无关长句直接塞入用户答案。

## 4.3 个性化学习路径推荐

推荐模块基于课程学习树、画像、RAG overlay 和 Study Graph state 构建推荐图，并生成候选路径。路径推荐的核心不是单纯排序，而是将学生状态、课程结构和知识依赖组织成可接受、可持久化的 learning plan。

关键机制：

- `build_recommendation_profile`
- `load_recommendation_learning_tree`
- `build_recommendation_graph_tree`
- `generate_state`
- `generate / hard_prune / score / soft_prune_by_dominance / ib_grpo_select`
- `accept_recommendation_path`
- `update_learning_plan_step_status`

当前边界：

- 推荐可以读取 Study Graph features。
- 推荐不直接写 Study Graph。
- 低质量 RAG overlay 边需要过滤，避免字符级噪声污染路径。

## 4.4 RAG 检索与证据融合

系统使用 RAG 为推荐、资源生成和即时答疑提供外部课程证据。RAG 不被视为绝对真值，而是作为 evidence summary 进入后续工具链。

即时答疑中，RAG query 会结合：

- 当前问题。
- 会话 topic hints。
- 学习目标。
- 当前 step。
- 相关薄弱点。
- Study Graph weak nodes。

证据低相关时返回 `low_relevance_evidence` warning。系统不要求 RAG 必须精准命中才成功，但不能把低相关证据包装成高质量依据。

## 4.5 多模态资源生成策略

资源生成模块围绕当前学习步骤生成资源。当前资源类型包括：

- `documents`
- `mindmap`
- `quiz`
- `coding_practice`
- `ppt`

资源生成不是在 QA 中临时完成，而是通过 Resource Generation Agent 的工具链完成：读取生成请求、生成计划、检索材料、写草稿、生成 payload、持久化资源。

待补图：资源生成工具链流程图。

## 4.6 学习反馈与成长树更新

成长树只记录学生真实触达、学习、提问、练习、答错、掌握或被个人大纲确认过的知识节点。Student Agent 可以提交变更候选，真正的归一化、去重、父节点裁决、低置信度拦截、掌握度更新和展示状态更新由 tool/service 层完成。

展示状态：

- `seed / weak`
- `sprout / growing`
- `branch / stable`
- `fruit / mastered`

该机制确保成长树不是推荐结果堆积，也不是审计日志，而是学生学习状态的可视化结构。

## 4.7 即时答疑质量策略

即时答疑支持问题类型分类：

- `concept_explanation`
- `learning_strategy`
- `exercise_help`
- `unknown`

不同问题类型走不同回答策略：

- 概念型问题：RAG + 上下文解释。
- 策略型问题：active plan + next task + weak points + 学习建议。
- 练习帮助：题目定位、知识点排查和练习建议。

输出是结构化 answer payload：

- `question_type`
- `text`
- `key_points`
- `evidence_used`
- `plan_reference`
- `relevant_weak_points`
- `filtered_weak_points`
- `next_actions`
- `confidence`
- `tone`
- `warnings`

`tone_style` 和 `answer_style` 只影响展示文本语气和详略，不影响结构化决策。

