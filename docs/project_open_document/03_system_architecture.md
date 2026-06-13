# 3 总体方案与系统架构

## 3.1 总体处理流程

系统围绕“画像 -> 路径 -> 资源 -> 学习 -> 答疑 -> 反馈 -> 成长树”的闭环运行。

典型流程：

```text
用户输入学习目标
  -> Total Agent 加载上下文
  -> Learning Profile 读取或构建画像
  -> Personal Recommendation 生成候选学习路径
  -> 用户接受路径
  -> 激活 active plan / next task
  -> Resource Generation 生成当前步骤资源
  -> 用户学习并反馈
  -> Learning Plan 更新 step 状态
  -> Study Graph 同步学习状态
  -> Total Agent 后续答疑和推荐继续读取更新后的状态
```

待补图：主流程泳道图。

## 3.2 总体结构设计

系统后端由五个核心能力模块和一个总编排模块组成：

- Learning Profile：学生画像和个人教学大纲。
- Personal Recommendation：学习路径推荐和学习计划状态。
- Resource Generation：多类型学习资源生成。
- Study Graph：学生学习成长树和课程聚合摘要。
- Total Agent：统一上下文加载、意图识别、工具编排和结果包装。
- Common 工具层：模型构造、RAG 检索、状态事件、数据库和公共 schema。

待补图：后端模块架构图。

## 3.3 多 Agent 协同结构

系统采用总 Agent 编排而不是所有 Agent 互相直接调用。Total Agent 负责判断用户意图，并通过稳定 task 接口调用专项模块。

协同关系：

- Total Agent 读取 Learning Profile、active plan、Study Graph features 和 RAG evidence。
- Recommendation 生成路径，但不写 Study Graph。
- Resource Generation 基于当前 step 和策略生成资源，不推进学习计划。
- Study Graph 只在学习反馈等真实触达事件后更新。
- QA 闭环不生成资源、不推进计划、不写反馈，只给出结构化回答和下一步动作建议。

## 3.4 数据流转设计

主要数据流：

```text
用户消息 / 上下文
  -> Total Agent payload
  -> total_context
  -> intent_result
  -> 对应工具 result
  -> build_total_agent_result
  -> 前端展示 result + status events
```

关键状态：

- `profile_summary`
- `active_plan`
- `next_task`
- `study_graph_state`
- `course_learning_tree_summary`
- `learning_evidence_result`
- `answer_learning_question_result`
- `resource_generation_result`

## 3.5 系统边界

系统当前后端能力偏完整，但仍有明确边界：

- 不承诺长期跨设备会话记忆产品化。
- 即时答疑不直接生成资源。
- 推荐路径不直接写成长树。
- Study Graph 不提前铺满完整课程地图。
- 真实 RAG 命中质量不可保证，低相关时以 warning 和降级处理。

## 3.6 错误与异常处理

主要异常类型：

- 缺少 `user_id` 或 `syllabus_id`。
- 无 active plan 或无 next task。
- RAG 检索失败或证据低相关。
- 资源生成失败。
- Study Graph sync 失败。
- 模型输出结构漂移。

处理原则：

- 结构化返回 `error_code`、`error_message`、`warnings`。
- `tool_status_events` 记录运行状态。
- 学习反馈同步 study graph 失败时不回滚 learning plan manifest，但要记录 warning。
- QA 结构化 payload 通过 normalize/validate 收口。

