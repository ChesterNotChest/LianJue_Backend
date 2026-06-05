# Total Agent next closure small plan

本文档用于收口 Total Agent 下一轮后端能力。当前核心链路已经覆盖深画像、学习记录树、active plan、资源生成、反馈推进和全真实 deep-state opt-in；下一轮目标是补齐赛题更完整的学习场景、个人资源库复用、即时答疑和教师/全局视角。

边界：

- 本文档是 small plan，不替代 `docs/E2E_amend_contract.md`。
- 默认测试仍不能访问真实 LLM/RAG/DB。
- opt-in E2E 必须保留真实 Agent / RAG / DB 入口。
- 不要求立即新增专职 QA Agent；优先把 Total Agent intent 和工具链补齐。

## 一、E2E 闭环补充矩阵

本阶段补三类代表性闭环。每类都必须有默认 mock/deterministic 版本和 opt-in 全真实版本。

### 1. 初次学习闭环

目标：

```text
自然语言目标
  -> 真实或 fixture Profile Agent 建画像
  -> 推荐路径
  -> 用户采纳
  -> 生成第一份资源
```

证明点：

```text
新学生从 0 到开始学习
```

默认 E2E：

```text
mock/fixture profile input
  -> learning_profile toolchain
  -> deterministic recommendation fixture
  -> accept learning plan
  -> monkeypatch resource generation
  -> artifact
```

opt-in E2E：

```text
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1
  -> real Profile Agent
  -> real Recommendation Agent + RAG
  -> real Total Agent accept flow
  -> real Resource Agent generates first resource
```

核心断言：

- profile 持久化成功。
- recommendation 有 `best_path` 或合法 clarification artifact。
- 用户确认后才创建 active plan。
- 第一份资源属于该 user/syllabus 的个人资源库。

### 2. 即时答疑闭环

目标：

```text
学生问概念/题目
  -> answer_learning_question
  -> RAG / active context / profile / study graph
  -> 直接解释
  -> 可选推荐资料或练习
```

证明点：

```text
赛题“智能辅导”加分项
```

设计原则：

- 不新增专职 QA Agent 起步。
- Total Agent 先新增 intent：`answer_learning_question`。
- 该 intent 不默认推进 learning plan。
- 该 intent 不默认生成资源。
- 如果回答后需要资源，再建议 `generate_current_step_resource`。

默认 E2E：

```text
question: "为什么 RowKey 会出现热点？"
  -> mock RAG snippets
  -> deterministic answer tool
  -> assert answer contains key points
  -> assert suggested_next_action can be generate_current_step_resource
```

opt-in E2E：

```text
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1
  -> real RAG retrieval
  -> Total Agent answer_learning_question
  -> answer cites / summarizes evidence
  -> artifact records retrieval summary
```

核心断言：

- intent 是 `answer_learning_question`。
- answer 不是资源生成结果。
- result 包含 `answer`、`evidence_summary`、`suggested_next_action`。
- 不创建或推进 learning plan。

### 3. 学习效果评估闭环

目标：

```text
完成资源 + quiz 得分 / 错题
  -> record_learning_feedback
  -> update learning_plan
  -> sync study_graph
  -> update / refresh profile signal
  -> next resource strategy changes
```

证明点：

```text
赛题“学习效果评估”和动态优化
```

默认 E2E：

```text
deep student state
  -> submit quiz score below threshold
  -> record feedback
  -> study graph weak node updated
  -> next strategy becomes targeted/review
```

opt-in E2E：

```text
RUN_LLM_TESTS=1 RUN_DB_TESTS=1
  -> real feedback event
  -> real study graph sync
  -> optional profile refresh / profile signal update
  -> Total Agent recommends targeted review resource
```

核心断言：

- learning plan 事件写入。
- study graph 记录薄弱点或低分信号。
- profile 或 profile-summary 能反映新弱点。
- 下一轮 resource strategy 不是普通 `standard`，而是 `targeted` 或 `review`。

## 二、个人资源库与资源推荐优化

目标边界：

```text
学生可见资源 = 自己生成 / 分配过的个人资源库
推荐资源来源 = 优先个人库命中；不足时新生成
全局课程资料 / RAG = 只作为生成和答疑的知识来源，不直接作为学生可见资源
```

### 1. 资源可见性和来源

规则：

- 学生只能看到自己 `user_id + syllabus_id` 下的资源。
- 自动推荐不能直接返回别人的资源。
- 全局课程资料和 RAG 检索结果只能作为 evidence / generation input。
- 如果确实要把全局材料推荐给学生，也必须复制、派生或记录为该学生的个人资源条目。

### 2. 个人资源库查询工具

建议新增轻量工具：

```text
generative_task.find_personal_resources(payload)
```

输入：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "node_id": "hbase_intro",
  "knowledge_items": ["HBase 基础", "RowKey 热点"],
  "resource_types": ["documents", "quiz"],
  "max_age_days": 30
}
```

输出：

```json
{
  "success": true,
  "matches": [
    {
      "resource_id": "documents-xxx",
      "resource_type": "documents",
      "topic": "HBase 基础",
      "quality_state": "usable",
      "freshness_state": "fresh",
      "student_feedback_state": "accepted",
      "match_score": 0.86,
      "paths": {}
    }
  ],
  "missing_resource_types": ["quiz"]
}
```

### 3. Manifest 可用性字段

资源 manifest 建议补充或归一以下字段：

```json
{
  "user_id": 76,
  "syllabus_id": 29,
  "node_id": "hbase_intro",
  "knowledge_items": ["HBase 基础", "RowKey 热点"],
  "resource_type": "documents",
  "created_at": 1780640000,
  "updated_at": 1780640000,
  "validation": {"valid": true},
  "quality_state": "usable",
  "freshness_state": "fresh",
  "student_feedback_state": "accepted",
  "student_feedback": {
    "liked": true,
    "too_easy": false,
    "too_hard": false,
    "explicitly_rejected": false
  },
  "expires_at": null,
  "source": {
    "kind": "generated",
    "rag_graph": "RAG"
  }
}
```

最小枚举：

```text
quality_state = usable | invalid | low_quality | needs_review
freshness_state = fresh | stale | expired
student_feedback_state = unknown | accepted | disliked | rejected
```

### 4. Total Agent 资源策略调整

当前链路：

```text
build_current_step_resource_strategy
  -> generate_current_step_resource
```

建议改为：

```text
build_current_step_resource_strategy
  -> find_personal_resources
  -> if enough usable matches:
       return existing resources
     else:
       generate missing resource types
  -> persist new resources
```

输出要保留：

```json
{
  "resource_recommendation_mode": "reuse_existing | generate_missing | generate_all",
  "existing_resources": [],
  "generated_resources": [],
  "missing_resource_types": []
}
```

### 5. Resource Agent 适度拆分原则

审查风险：

```text
Resource Agent 如果继续同时承担：
  -> 资源请求读取
  -> 计划编排
  -> RAG 检索
  -> 草稿生成
  -> 多格式内容生成
  -> 持久化
  -> 个人库查询
  -> 复用判断

会变成过大的单体工具链。
```

本阶段不建议按 `documents / quiz / mindmap / ppt / coding_practice` 硬拆成多个专职 Agent。原因：

- 资源类型之间共享同一套学习上下文、RAG 证据、画像信号和持久化约束。
- 过早拆分会让 Total Agent 编排复杂度上升。
- 当前问题更像“阶段职责过多”，不是“资源类型必须独立”。

建议采用适度划分：

```text
Total Agent
  -> build_current_step_resource_strategy
  -> find_personal_resources             # 个人库查询，不进入 Resource Agent 生成链
  -> decide reuse_or_generate
  -> if generate:
       Resource Agent
         -> read_generation_request
         -> read_generation_plan
         -> retrieve_generation_materials
         -> write_generation_draft
         -> generate_resource_payload
         -> persist_generated_resource
```

也就是说：

- `find_personal_resources` 是 generative task 的查询工具，不是 Resource Agent 的内部工具。
- `reuse_existing | generate_missing | generate_all` 是 Total Agent 的策略决策，不是 Resource Agent 自己决定。
- Resource Agent 继续做“给定请求后生成并持久化资源”的通用生成器。
- 资源类型差异先由 `generate_resource_payload` 内部按 `resource_type` 分派，不急着拆 Agent。

拆分信号：

```text
必须拆：
  -> 某一阶段需要独立权限/独立缓存/独立 API
  -> 某一阶段需要不同模型或不同超时策略
  -> 某一阶段失败后需要可恢复重试，而不能重跑整条资源链
  -> 单个 Agent tool 数量长期超过 8-10 个，且新增工具不服务于“生成并持久化资源”主目标

建议拆：
  -> 个人库查询、资源复用判断、资源质量评分开始有复杂规则
  -> 多资源类型并发生成需要独立调度
  -> ppt/video/coding_practice 需要完全不同的执行环境

暂不拆：
  -> 只是不同资源类型的 schema 和 renderer 差异
  -> 只是生成 prompt 不同
  -> 只是 persistence 输出文件不同
```

推荐的中间形态：

```text
ResourceLibraryTool
  -> find_personal_resources
  -> score_resource_reuse
  -> mark_resource_feedback

ResourceGenerationAgent
  -> plan/retrieve/draft/generate/persist

TotalAgent
  -> decide whether to reuse or generate
```

这样既避免 Resource Agent 继续膨胀，也不会把系统拆成难以编排的一堆专职 Agent。

### 6. Total Agent 即时答疑 RAG 工具

建议给 Total Agent 增加单纯 RAG 工具：

```text
retrieve_learning_evidence
```

用途：

- 即时问答。
- 资源生成前的轻量证据读取。
- 推荐失败时辅助目标归一化。

边界：

- 只返回压缩 evidence。
- 不直接把全局资料变成学生可见资源。
- 不推进 learning plan。

输出：

```json
{
  "success": true,
  "evidence_summary": [
    {
      "title": "HBase RowKey 热点",
      "summary": "单调递增 RowKey 会导致写入集中到少数 Region。",
      "source": "RAG",
      "score": 0.82
    }
  ],
  "warnings": []
}
```

## 三、教师 / 全局学习进度树工具

目标：

```text
Total Agent / Teacher Agent 可以读取课程或班级级聚合学习进度树，
用于判断当前学生策略是否需要结合全局情况调优。
```

### 1. 视角和权限

```text
student
  -> own study graph only

teacher
  -> course/class aggregate study graph
  -> optional drill down to assigned students

admin
  -> cross-course analytics
```

默认 Total Agent 为学生服务时，只能读取压缩后的全局摘要，不能裸露其他学生个人数据。

### 2. 聚合学习树工具

建议新增：

```text
study_graph_task.get_course_learning_tree_summary(payload)
```

输入：

```json
{
  "teacher_id": 3,
  "syllabus_id": 29,
  "class_id": "class_hbase_2026",
  "focus_user_id": 76,
  "limit": 20
}
```

输出：

```json
{
  "success": true,
  "summary": {
    "syllabus_id": 29,
    "student_count": 42,
    "weak_nodes": [
      {
        "title": "RowKey 热点",
        "weak_student_count": 18,
        "average_mastery": 0.34,
        "common_wrong_points": ["单调递增 RowKey", "预分区边界"]
      }
    ],
    "mastered_nodes": [],
    "recently_active_nodes": [],
    "recommended_intervention": [
      "下一节课建议补 RowKey 热点和预分区案例。"
    ]
  },
  "privacy": {
    "aggregation": true,
    "student_ids_redacted": true
  }
}
```

### 3. Total Agent 使用方式

学生侧 Total Agent 可以使用压缩后的全局摘要，但只能作为策略信号：

```text
if current step is also class-wide weak:
  -> increase priority for explanation / quiz / review
else:
  -> keep personalized profile + own study graph as primary signals
```

输出策略信号：

```json
{
  "strategy_signals": {
    "matched_profile_weak_point": true,
    "matched_own_study_graph_weak_node": true,
    "matched_course_global_weak_node": true
  }
}
```

### 4. 压缩原则

- 不返回全量学生树。
- 不返回完整个人画像。
- 默认只返回 top weak / top mastered / recent activity / intervention summary。
- 单次返回节点数建议小于 20。
- 如果给学生侧 Total Agent 使用，应进一步隐藏学生数量过小的节点，避免反推个人信息。

## 四、推荐执行顺序

```text
1. answer_learning_question intent + retrieve_learning_evidence 工具
2. 即时答疑默认 E2E + opt-in E2E
3. find_personal_resources + manifest 可用性字段
4. 资源推荐复用个人库默认 E2E
5. 学习效果评估闭环默认 E2E + opt-in E2E
6. course/global study graph summary 工具
7. 初次学习全真实 opt-in E2E
8. 最后一条 release 级多轮大闭环
```

release 级多轮大闭环建议：

```text
Turn 1: 学生表达自然语言目标
  -> build profile
  -> recommend path

Turn 2: 学生确认计划
  -> accept plan
  -> generate / reuse documents + quiz

Turn 3: 学生问“为什么 RowKey 会热点？”
  -> answer_learning_question

Turn 4: 学生完成 quiz，分数偏低
  -> record feedback
  -> update study graph / profile signal
  -> next strategy targeted/review

Turn 5: 学生要求总结
  -> generate / reuse mindmap or ppt
```

该测试成本高、外部波动大，只作为发布前 opt-in，不进默认 CI。
