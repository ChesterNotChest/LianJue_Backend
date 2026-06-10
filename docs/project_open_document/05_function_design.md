# 5 功能设计

## 5.1 Learning Profile 模块

功能描述：

学习画像模块负责读取或构建学生画像，沉淀学生学习目标、薄弱点、资源偏好、风险信号和个人教学大纲建议。

输入：

- `user_id`
- `syllabus_id`
- 学习目标或用户消息
- 历史学习事件
- 课程上下文

输出：

- `profile_summary`
- `weak_points`
- `preferred_formats`
- `learning_goal`
- `profile_source`

限制条件：

- 画像用于策略判断，不应直接把无关长文本塞入用户回答。

## 5.2 Personal Recommendation 模块

功能描述：

推荐模块负责根据学生画像、课程结构和学习状态生成候选学习路径，并在用户接受后落盘为 active learning plan。

输入：

- 用户目标。
- 课程学习树。
- 学习画像。
- Study Graph state。
- RAG overlay。

输出：

- 推荐候选路径。
- `best_path`。
- active learning plan。
- next task。

限制条件：

- 推荐阶段不写 Study Graph。
- RAG overlay 需要过滤低质量边。

## 5.3 Resource Generation 模块

功能描述：

资源生成模块根据当前 step、知识点和资源策略生成学习资源。

输入：

- 当前 step。
- `knowledge_items`。
- `resource_types`。
- 难度策略。
- RAG 材料。

输出：

- 资源 payload。
- resource metadata。
- persisted resource。
- 生成状态事件。

限制条件：

- 资源生成可耗时，但必须能被前端用状态事件展示进度。

## 5.4 Study Graph 模块

功能描述：

Study Graph 模块维护每个学生每个大纲的一棵个人学习成长树，并提供 Agent 可消费 features。

输入：

- 学习反馈。
- detected topics。
- parent candidates。
- mastery signal。

输出：

- manifest tree。
- change log。
- features。
- 课程聚合摘要。

限制条件：

- 不提前铺满完整课程地图。
- 只维护已触达知识节点和 `parent_of` 树边。

## 5.5 Total Agent 模块

功能描述：

Total Agent 是系统主编排入口，负责加载上下文、识别意图、调用工具链并返回统一结果。

输入：

- 用户消息。
- 用户、课程、上下文 ID。
- 可选 `qa_level`、`tone_style`、`answer_style`、`question_type_hint`。

输出：

- `success`
- `intent`
- `tool_trace`
- `tool_status_events`
- `result`
- `suggested_next_action`
- `error_code`
- `error_message`

限制条件：

- 即时答疑不推进 plan、不生成资源、不写 feedback。

## 5.6 前端演示模块

功能描述：

前端需要把后端闭环转成可理解、可操作、可演示的学习工作台。

核心页面建议：

- 学习目标输入与推荐页。
- 当前学习步骤页。
- 资源展示页。
- 即时答疑面板。
- 成长树页。
- 多 Agent 状态流面板。

待补图：前端页面信息架构图。

