# learning_profile Agent Orchestration 改造说明

## 1. 目标

本说明严格沿用 `learning_profile_agent_workflow.md` 的业务骨架，只改执行形态，不改核心算法方向。

要保留的内容：

- 既定输入契约：`user_id`、`syllabus_id`、`dialogue_text`、`learning_goal`、`learning_records`、`answer_records`、`resource_usage`
- 既定输出契约：`success`、`profile`、`error_message`、`error_code`
- 画像核心字段与分层：`knowledge_mastery`、`confidence`、`evidence`、`recent_anomaly`、`conflict_resolution`、`signals`
- 既定算法思路：上下文补全、事件归一化、特征计算、风险判断、证据生成、画像汇总

要替换的内容：

- 不再由外部代码把所有数据一次性拼成一个大 prompt 再喂给 LLM
- 改为由 Agent 通过多个 tool 按需取数、调用特征计算能力、最后汇总输出 `profile`

一句话概括：

> 保留 learning_profile 的输入、输出和核心算法，只把“直接数据流构建”替换成“Agent + tools + orchestration”。

## 2. Agent 职责边界

### Agent 负责什么

- 接收 `user_id`、`syllabus_id` 以及可选输入字段
- 判断当前还缺哪些上下文
- 调用只读 tool 补齐上下文
- 调用特征计算 tool
- 汇总并输出最终 `profile`

### Agent 不负责什么

- 不重写已有画像字段定义
- 不改原本的特征口径
- 不直接承担持久化策略设计
- 不在第一版里直接改写数据库或 JSON 快照

这里的 Agent 更像：

- 编排层
- 调度层
- 画像组装层

而不是：

- 替代全部规则与算法的黑盒 LLM

## 3. 沿用原工作流后的新执行形态

原文档里的整体流程仍然保留：

1. 接收输入
2. 读取上下文
3. 事件归一化
4. 特征计算
5. 汇总成画像
6. 返回结果

区别只在于每一步不再默认由外部流程手工串起来，而是改成下述形态：

1. 调用方把基础参数交给 Agent
2. Agent 决定需要调用哪些 tool
3. tool 返回结构化数据
4. Agent 基于这些数据继续调用下一个 tool 或直接汇总
5. Agent 最终输出完整 `profile`

## 4. 按原骨架拆分的 tools

下面的拆分方式应尽量贴合 `learning_profile_agent_workflow.md` 的章节结构。

### 4.1 输入层

这一层不需要让 Agent“自己发明输入”，只需要保留现有接口契约：

- `user_id`
- `syllabus_id`
- `dialogue_text`
- `learning_goal`
- `learning_records`
- `answer_records`
- `resource_usage`

建议保留一个单独的预处理函数：

- `normalize_learning_profile_request(...)`

它负责：

- 兼容空字段
- 统一时间格式
- 统一文本字段形态
- 统一列表/单值字段形态

### 4.2 上下文读取 tools

这一层对应原文档“步骤 2：读取上下文”。

建议拆成以下只读 tool：

- `get_user_context(user_id)`
- `get_user_syllabus_context(user_id, syllabus_id)`
- `get_syllabus_context(syllabus_id)`
- `get_personal_syllabus_context(user_id, syllabus_id)`
- `get_history_context(user_id, syllabus_id)`

这些 tool 应返回结构化对象，不要返回自然语言大段描述。

### 4.3 事件归一化 tools

这一层对应原文档“步骤 3：事件归一化”。

建议拆成：

- `normalize_dialogue_events(dialogue_text, learning_goal)`
- `normalize_learning_records(learning_records)`
- `normalize_answer_records(answer_records)`
- `normalize_resource_usage(resource_usage)`
- `merge_profile_events(...)`

输出目标是统一事件结构，例如：

- `timestamp`
- `duration_minutes`
- `texts`
- `knowledge_points`
- `action`
- `event_type`

这一层最好尽量规则化，不要过度依赖 LLM。

### 4.4 特征计算 tools

这一层对应原文档“步骤 4：特征计算”。

建议按文档里的特征簇拆开，而不是做成一个巨大函数。

#### 对话特征

- `compute_dialogue_features(...)`

输出至少覆盖：

- `goal_clarity`
- `term_familiarity`
- `help_seeking_level`
- `self_reported_difficulty`
- `emotion_state`

#### 行为特征

- `compute_behavior_features(...)`

输出至少覆盖：

- `study_frequency`
- `study_duration`
- `attention_pattern`
- `difficulty_tolerance`

#### 资源偏好特征

- `compute_resource_preference_features(...)`

输出至少覆盖：

- `resource_preference`
- `learning_style`

#### 答题掌握度特征

- `compute_answer_mastery_features(...)`

输出至少覆盖：

- `knowledge_mastery.answer_score`
- `knowledge_mastery.by_knowledge_point`
- `knowledge_mastery.knowledge_point_details`

#### 课程进度特征

- `compute_syllabus_mastery_features(...)`

输出至少覆盖：

- `knowledge_mastery.syllabus_score`
- `knowledge_mastery.week_items`
- `knowledge_mastery.mastered_weeks`
- `knowledge_mastery.weak_weeks`

#### 风险特征

- `compute_risk_features(...)`

输出至少覆盖：

- `dropout_risk`
- `dropout_risk_score`
- `recent_anomaly`

### 4.5 汇总与解释 tools

这一层对应原文档“步骤 5：汇总成画像”。

建议拆成：

- `resolve_profile_conflicts(...)`
- `build_profile_evidence(...)`
- `build_profile_signals(...)`
- `assemble_learning_profile(...)`

这里应负责：

- 融合多源特征
- 处理主观陈述与客观表现冲突
- 生成 `confidence`
- 生成 `evidence`
- 生成最终 `profile`

### 4.6 返回层

这一层对应原文档“步骤 6：返回结果”。

保持原契约，不改：

```json
{
  "success": true,
  "profile": {},
  "error_message": "",
  "error_code": ""
}
```

## 5. Agent 在流程中的参与方式

这里建议把 Agent 放在“编排和判断”位置，而不是所有环节都交给 LLM。

推荐形态：

1. 规则函数先做请求预处理
2. Agent 调用上下文读取 tools
3. Agent 调用事件归一化 tools
4. Agent 调用特征计算 tools
5. Agent 调用汇总 tool 形成 `profile`
6. API 层返回既定响应结构

也就是说：

- 规则和函数承担“算”
- Agent 承担“调”
- LLM 承担“少量语义判断 + 复杂汇总解释”

不建议第一版就做成：

- 所有原始数据全扔给 LLM
- 所有特征都靠 LLM 临场生成
- 所有写操作都开放给 Agent

## 6. 推荐的最小实现方案

建议新增一个真正面向 `learning_profile` 的模块，而不是继续围绕 `learning_task.py` 的问答流程修补。

建议文件：

- `tasks/learning_profile_agent_task.py`

建议入口函数：

- `run_learning_profile_agent(...)`

建议保留的接口地址：

- `POST /api/user_learning_profile`

如果现有接口尚未实现，也应优先沿用该命名，不要另起与文档冲突的新名字。

## 7. 推荐的 SDK 与实现方式

推荐一套足够简单的链路：

- `pydantic-ai-slim[openai]`

原因：

- 可直接 `pip install`
- 支持 function tool calling
- 支持结构化输出
- 支持 OpenAI-compatible `base_url`
- 足够轻，适合先做一版 orchestration

推荐分工：

- tool：普通 Python 函数或现有 repo/task 函数包装层
- Agent：决定调用哪些 tool、何时停止、如何汇总输出
- Output model：用 `Pydantic BaseModel` 对齐 `profile` 契约

## 8. 第一批可包装成 tool 的能力

优先开放只读能力。

### 直接可包装

- 用户基础信息读取
- 用户与 syllabus 绑定关系读取
- syllabus 基础信息读取
- personal syllabus JSON 读取
- history 窗口读取
- learning_records / answer_records / resource_usage 归一化
- 各类特征计算函数
- 画像汇总函数

### 暂时不要开放

- 保存画像快照
- 更新个人 syllabus
- 更新 competance / competance_progress
- 写回 DB
- 写回本地 JSON

原因很简单：

- 第一版先解决“能不能把 learning_profile 这条链路 Agent 化”
- 写操作放早了，会把权限、幂等和回滚问题一起引进来

## 9. 验收标准

如果这次改造完成，至少应满足下面几点：

1. `learning_profile_agent_workflow.md` 的输入字段不变
2. 返回结构仍然是 `success + profile + error_message + error_code`
3. `profile` 的关键字段层级不变
4. Agent 确实在运行时调用多个 tool，而不是外部先把所有特征硬拼成一个大 prompt
5. 对话分析、行为分析、答题分析、风险分析仍然保留原有算法意图
6. 第一版默认只读，不自动持久化

## 10. 建议交付物

建议这次至少产出：

1. `tasks/learning_profile_agent_task.py`
2. 一组与 `learning_profile` 对齐的 tool 封装函数
3. 一个可跑通的 `POST /api/user_learning_profile` 实现
4. 一份简短说明：
   当前哪些字段由规则计算，哪些字段由 Agent 汇总

## 11. 结论

这个改造不是重做画像算法，而是把原方案从：

- 外部直接组织数据流

改成：

- Agent 调用 tools 组织数据流

核心判断标准只有一个：

> `learning_profile` 的业务骨架、字段契约和算法方向不变；变化的只是执行方式从“人工拼装流程”切到“Agent orchestration”。
