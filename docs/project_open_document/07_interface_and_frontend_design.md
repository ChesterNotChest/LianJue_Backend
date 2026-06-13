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

## 7.2 前端 API 边界

前端接口按业务 task 粒度组织。读取类接口应只读取当前持久化状态，不隐式触发 Agent；构建、刷新、推荐、生成、反馈类接口才允许进入 Agent 或工具链。这样前端能明确区分“页面展示读取”和“用户动作触发计算”。

### 7.2.1 学习画像 API

学习画像提供两个主接口：

| 场景 | HTTP 入口 | 语义 | 是否触发画像 Agent |
|---|---|---|---|
| 读取当前画像 | `POST /api/learning_profile_detail` | 只读已持久化画像，用于页面初始化、右侧画像栏和演示回放 | 否 |
| 刷新画像 | `POST /api/learning_profile_refresh` | 根据学习记录、答题记录、资源使用记录显式构建或刷新画像 | 是 |

读取画像请求：

```json
{
  "user_id": 126,
  "syllabus_id": 29
}
```

读取画像响应：

```json
{
  "success": true,
  "profile": {},
  "profile_path": "profiles/29-126.json",
  "profile_saved": true,
  "profile_refreshed": false,
  "error_message": "",
  "error_code": ""
}
```

刷新画像请求可携带新增学习证据：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "learning_goal": "掌握 HBase RowKey 热点规避",
  "answer_records": [
    {
      "question": "RowKey 如何避免写入热点？",
      "correct": false,
      "time_spent_seconds": 170,
      "meta": {"knowledge_points": ["RowKey 热点", "加盐前缀"]}
    }
  ],
  "resource_usage": [
    {
      "resource_id": "quiz-rowkey-hotspot-001",
      "resource_type": "quiz",
      "action": "submit",
      "score": 0.6,
      "meta": {"knowledge_points": ["RowKey 热点", "预分区"]}
    }
  ]
}
```

刷新画像响应与读取接口保持同一外层结构，但 `profile_refreshed` 应为 `true`。前端在普通页面加载时使用 `learning_profile_detail`；只有用户完成测验、提交学习记录或明确要求重新分析时，才使用 `learning_profile_refresh`。

### 7.2.2 接口使用约束

- 前端不应为了读取画像而调用刷新接口。
- 前端不应依赖 `refresh_profile` 作为业务语义；画像 API 只有读和重算两个入口。
- 答题卡片可以先本地判分并展示解析，再静默调用刷新接口提交 `answer_records`。
- Total Agent 后续对话读取到的是已持久化画像，不要求前端在每次对话前刷新画像。

### 7.2.3 推荐快照 API

推荐页使用 Recommendation Snapshot 支撑推荐大网展示、刷新回放和手选候选路径。它是前端展示缓存，不是学习状态；推荐算法核心函数保持纯计算，API 层在推荐成功后默认保存该展示缓存。

| 场景 | HTTP 入口 | 语义 | 是否创建学习计划 |
|---|---|---|---|
| 生成推荐并保存展示缓存 | `POST /api/personal_recommendation` | 返回推荐大网、候选路径、`recommendation_id` | 否 |
| 列出推荐快照 | `GET /api/recommendations?user_id=...&syllabus_id=...` | 返回最近推荐摘要，不返回完整大图 | 否 |
| 读取推荐快照详情 | `GET /api/recommendations/<recommendation_id>` | 返回完整 `graph/candidates/selected/best_path` | 否 |
| 采纳候选路径 | `POST /api/recommendations/<recommendation_id>/accept` | 按 `candidate_index` 创建 active learning plan | 是 |

生成推荐请求：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "goals": ["掌握 HBase RowKey 热点规避"],
  "session_id": "sess_demo_001",
  "persist_snapshot": true
}
```

生成推荐响应：

```json
{
  "success": true,
  "recommendation_id": "recommendation_20260610191033_d27634",
  "snapshot_status": "proposed",
  "graph": {},
  "candidates": [],
  "selected": [],
  "best_path": {},
  "planning_hints": {},
  "error_message": "",
  "error_code": ""
}
```

快照列表只返回摘要：

```json
{
  "success": true,
  "snapshots": [
    {
      "recommendation_id": "recommendation_...",
      "status": "proposed",
      "candidate_count": 3,
      "node_count": 12,
      "edge_count": 14,
      "best_path": ["hbase_intro", "rowkey_design"],
      "best_path_titles": ["HBase 基础", "HBase RowKey 设计"],
      "accepted_plan_id": null,
      "created_at": 1781118633
    }
  ]
}
```

采纳候选路径请求：

```json
{
  "user_id": 126,
  "syllabus_id": 29,
  "candidate_index": 1
}
```

采纳响应返回现有 learning plan 结构，并追加 `snapshot_status`、`accepted_plan_id` 和 `accepted_candidate_index`。前端应把推荐大网理解为“建议网络/展示缓存”，只有采纳后的路径才进入学习计划；推荐快照不会直接改变学生成长树，也不会成为 Total Agent 后续学习推进的状态来源。

## 7.3 Total Agent 前端消费结构

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

## 7.4 多 Agent 状态流设计

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

## 7.5 学习工作台设计

学习工作台建议包含：

- 顶部：当前课程、学习目标、进度摘要。
- 左侧：学习路径和 active step。
- 中间：当前资源、答疑或任务内容。
- 右侧：成长树摘要、薄弱点和 Agent 状态流。
- 底部：反馈、继续学习、生成练习、生成资料等动作。

待补图：学习工作台主界面。

## 7.6 资源展示设计

资源类型展示建议：

- documents：Markdown 阅读器 + 关键点。
- quiz：题目列表 + 答题反馈。
- mindmap：图结构或层级树。
- coding_practice：题目、代码区、测试说明、答案解析。
- ppt：幻灯片大纲、页面预览或导出入口。

待补图：资源详情页。

## 7.7 降级交互设计

前端必须自然接住后端降级：

- 无 active plan：引导确认学习目标或生成学习路径。
- RAG 低相关：提示“当前证据不足，以下为基于已有上下文的建议”。
- 资源生成中：显示进度而不是空白等待。
- Study Graph sync warning：提示学习记录已保存，但成长树同步待检查。

## 7.8 演示路径设计

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

