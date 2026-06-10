# 7 接口与前端交互设计

## 7.1 接口设计目标

接口设计应服务于生产级前端体验，而不是只返回后端调试结果。前端需要能够展示：

- 当前意图。
- 当前学习计划和步骤。
- Agent 工具运行状态。
- 资源生成进度。
- 答疑结构化结果。
- 下一步可点击动作。
- 错误、warning 和降级原因。

## 7.2 Total Agent 前端消费结构

前端重点消费：

```json
{
  "success": true,
  "intent": "answer_learning_question",
  "tool_trace": [],
  "tool_status_events": [],
  "result": {},
  "suggested_next_action": "",
  "error_code": "",
  "error_message": ""
}
```

即时答疑重点消费：

```json
{
  "answer": {
    "question_type": "learning_strategy",
    "text": "",
    "key_points": [],
    "next_actions": [],
    "plan_reference": {},
    "warnings": []
  }
}
```

## 7.3 多 Agent 状态流设计

建议采用“主回答 + Agent cards”的结构：

```text
主内容区
  当前学习步骤 / 资源 / 答疑结果

右侧或底部状态区
  Profile Agent
  Recommendation Agent
  Resource Agent
  QA Agent
  Study Graph Agent
```

每个 Agent card 展示：

- 状态：running / succeeded / failed。
- 当前 stage。
- 简短说明。
- 关键输出摘要。
- 错误或 warning。

待补图：Agent cards 交互稿。

## 7.4 学习工作台设计

学习工作台建议包含：

- 顶部：当前课程、学习目标、进度摘要。
- 左侧：学习路径和 active step。
- 中间：当前资源、答疑或任务内容。
- 右侧：成长树摘要、薄弱点和 Agent 状态流。
- 底部：反馈、继续学习、生成练习、生成资料等动作。

待补图：学习工作台主界面。

## 7.5 资源展示设计

资源类型展示建议：

- documents：Markdown 阅读器 + 关键点。
- quiz：题目列表 + 答题反馈。
- mindmap：图结构或层级树。
- coding_practice：题目、代码区、测试说明、答案解析。
- ppt：幻灯片大纲、页面预览或导出入口。

待补图：资源详情页。

## 7.6 降级交互设计

前端必须自然接住后端降级：

- 无 active plan：引导确认学习目标或生成学习路径。
- RAG 低相关：提示“当前证据不足，以下为基于已有上下文的建议”。
- 资源生成中：显示进度而不是空白等待。
- Study Graph sync warning：提示学习记录已保存，但成长树同步待检查。

## 7.7 演示路径设计

建议演示一条完整路径：

```text
输入：我想学习 HBase RowKey 热点规避
  -> 画像读取
  -> 路径推荐
  -> 接受计划
  -> 生成短文档
  -> 提问：我下一步应该怎么学？
  -> 展示结构化策略回答
  -> 完成资源并提交反馈
  -> 学习计划推进
  -> 成长树出现或更新 RowKey 热点节点
```

待补图：7 分钟演示脚本流程图。

