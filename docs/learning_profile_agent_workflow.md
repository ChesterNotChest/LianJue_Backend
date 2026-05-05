# 学习画像构建 Agent 工作流说明

## 1. 这个 Agent 是做什么的

学习画像构建 Agent 负责把学生的对话、学习行为、答题记录、资源使用记录和个人教学大纲信息，整理成一份统一、结构化、可解释的学生画像。

它的职责不是生成教学内容，而是先回答下面这些问题：

- 这个学生当前学到哪里
- 哪些知识点掌握较弱
- 最近学习是否稳定
- 偏好什么资源形式
- 是否出现掉队风险或异常状态

当前实现已经不是单纯的字段拼装，而是会把多源事件转成可计算信号，再输出标准化画像结果。

### 主要功能

- 从对话中抽取学习目标、术语熟悉度、求助意愿、自我感知难度、情绪状态
- 从学习记录中统计活跃度、学习时长、投入度
- 从答题记录中计算知识点级掌握度
- 从资源使用中识别资源偏好和完成情况
- 结合个人教学大纲中的 `competance` 和 `competance_progress` 评估课程进度掌握情况
- 输出带 `confidence`、`evidence`、`recent_anomaly` 的结构化画像

### 不做什么

- 不直接生成课程内容
- 不直接生成题目、文档、思维导图
- 不替代路径规划 Agent
- 不替代答疑 Agent
- 不直接写回数据库中的画像快照

## 2. 工作流

整体流程可以理解成“收集输入 -> 读取上下文 -> 事件归一化 -> 标签计算 -> 证据生成 -> 输出画像”。

### 步骤 1：接收输入

输入可以来自前端、调用方服务或其他 Agent，常见字段包括：

- `user_id`
- `syllabus_id`（可选，但建议提供）
- `dialogue_text`
- `learning_goal`
- `learning_records`
- `answer_records`
- `resource_usage`

### 步骤 2：读取上下文

Agent 会自动补齐和读取以下上下文：

- `user` 表中的用户基础信息
- `user_syllabus` 表中的课程关联与个人大纲路径
- `syllabus` 表中的课程标题
- `history/` 下的历史问答窗口
- 个人教学大纲 JSON 中的 `period`、`competance`、`competance_progress`

### 步骤 3：事件归一化

实现会把不同来源的数据统一整理成内部事件格式：

- 历史问答 -> `history` 事件
- 学习记录 -> `learning_records` 事件
- 答题记录 -> `answer_records` 事件
- 资源使用 -> `resource_usage` 事件

归一化后统一抽取以下信号：

- `timestamp`
- `duration_minutes`
- `texts`
- `knowledge_points`
- `action`
- `event_type`

### 步骤 4：特征计算

当前版本会计算这些核心特征：

- 对话特征：`goal_clarity`、`term_familiarity`、`help_seeking_level`、`self_reported_difficulty`、`emotion_state`
- 行为特征：`study_frequency`、`study_duration`、`attention_pattern`
- 偏好特征：`resource_preference`、`learning_style`
- 答题特征：知识点级正确率、尝试次数、知识点掌握度
- 课程特征：个人大纲周次能力得分、薄弱周次、已掌握周次
- 风险特征：`dropout_risk`、`dropout_risk_score`、`recent_anomaly`

### 步骤 5：汇总成画像

Agent 会把多个来源的结果融合成最终画像，主要包括：

- 课程整体掌握度
- 知识点级掌握度
- 学习风格与资源偏好
- 风险判断
- 证据链和置信度

### 步骤 6：返回结果

接口返回 JSON，核心字段是 `profile`。

## 3. 如何调用

### 接口地址

`POST /api/user_learning_profile`

### 请求参数

```json
{
  "user_id": 1,
  "syllabus_id": 19,
  "dialogue_text": "我最近在学 Python，尤其是函数和循环",
  "learning_goal": "掌握 Python 基础语法",
  "learning_records": [],
  "answer_records": [],
  "resource_usage": []
}
```

### 参数说明

- `user_id`：必填，学生 ID
- `syllabus_id`：可选，指定课程后会优先围绕该课程生成画像
- `dialogue_text`：可选，字符串或字符串数组
- `learning_goal`：可选，显式学习目标
- `learning_records`：可选，学习行为记录
- `answer_records`：可选，答题数据
- `resource_usage`：可选，资源使用记录

### 返回示例

下面示例更贴近当前实现：

```json
{
  "success": true,
  "profile": {
    "user_id": 1,
    "user_name": "alice",
    "email": "alice@example.com",
    "syllabus_scope": [
      {
        "syllabus_id": 19,
        "title": "Python 基础",
        "personal_syllabus_path": "schedule/student_alt/demo.json"
      }
    ],
    "learning_goal": "掌握 Python 基础语法",
    "goal_clarity": {
      "level": "high",
      "score": 0.9,
      "confidence": 0.73
    },
    "term_familiarity": {
      "level": "medium",
      "score": 0.36,
      "confidence": 0.41
    },
    "help_seeking_level": {
      "level": "medium",
      "score": 0.46
    },
    "self_reported_difficulty": {
      "level": "medium",
      "score": 0.49
    },
    "emotion_state": {
      "label": "frustrated",
      "negative_hits": 2,
      "positive_hits": 0
    },
    "target_level": "入门",
    "deadline": null,
    "knowledge_mastery": {
      "overall_level": "weak",
      "overall_score": 0.43,
      "syllabus_score": 0.35,
      "answer_score": 0.33,
      "engagement_score": 0.61,
      "week_items": [
        {
          "week_index": 1,
          "competance": "weak",
          "competance_progress": -1,
          "score": 0.2,
          "content": "循环结构与变量作用域"
        }
      ],
      "mastered_weeks": [],
      "weak_weeks": [1],
      "by_knowledge_point": {
        "函数参数": 0.0,
        "循环嵌套": 1.0
      },
      "knowledge_point_details": {
        "函数参数": {
          "score": 0.0,
          "confidence": 0.61,
          "attempt_count": 2,
          "level": "low"
        }
      }
    },
    "concept_gaps": ["循环结构与变量作用域", "函数参数"],
    "practice_ability": {
      "level": "medium",
      "score": 0.54
    },
    "comprehension_level": {
      "level": "medium",
      "score": 0.49
    },
    "study_frequency": "medium",
    "study_duration": "medium",
    "resource_preference": ["video", "practice"],
    "answer_pattern": "example-seeking",
    "learning_style": "visual-driven",
    "attention_pattern": "stable",
    "difficulty_tolerance": "medium",
    "bottleneck_topics": ["循环结构与变量作用域", "函数参数"],
    "dropout_risk": "medium",
    "dropout_risk_score": 0.47,
    "recent_anomaly": ["frustration_signal"],
    "confidence": 0.68,
    "evidence": [
      "近7天活跃 2 天",
      "平均单次学习时长约 31.7 分钟",
      "知识点“函数参数”当前掌握度约为 0%"
    ],
    "source_events": ["answer_records", "learning_records", "resource_usage"],
    "knowledge_mapping": {
      "mapped_nodes": ["函数参数", "循环嵌套"],
      "mapped_node_count": 2,
      "graph_binding": "knowledge_point_proxy_nodes"
    },
    "conflict_resolution": {
      "alignment": "aligned",
      "gap": 0.06,
      "objective_priority": "behavior_and_answer_records"
    },
    "updated_at": 1759999900,
    "signals": {
      "history_count": 0,
      "history_sources": 1,
      "question_text_count": 3,
      "profile_scope_count": 1,
      "learning_record_count": 2,
      "answer_record_count": 3,
      "resource_event_count": 1,
      "active_days_7d": 2,
      "active_days_30d": 2,
      "avg_duration_minutes": 31.67
    }
  },
  "error_message": "",
  "error_code": ""
}
```

## 4. 字段解释

### 顶层核心字段

- `learning_goal`：最终采用的学习目标，优先使用请求中的 `learning_goal`
- `target_level`：基于综合掌握度推断的阶段目标，通常为 `入门`、`进阶`、`熟练`
- `confidence`：本次画像整体置信度
- `evidence`：用于解释当前画像的证据文本
- `source_events`：本次画像实际用到了哪些输入源

### 对话分析字段

- `goal_clarity`：目标明确度
- `term_familiarity`：术语熟悉度
- `help_seeking_level`：求助意愿
- `self_reported_difficulty`：学生自我感知难度
- `emotion_state`：情绪状态，目前输出 `frustrated`、`positive`、`neutral`

### 掌握度字段

- `knowledge_mastery.overall_score`：综合掌握度
- `knowledge_mastery.syllabus_score`：来自个人教学大纲的课程掌握度
- `knowledge_mastery.answer_score`：来自答题记录的掌握度
- `knowledge_mastery.engagement_score`：来自行为投入度的分数
- `knowledge_mastery.by_knowledge_point`：知识点级掌握度
- `knowledge_mastery.knowledge_point_details`：每个知识点的细粒度详情

### 行为与风险字段

- `study_frequency`：近 7 天或近 30 天活跃情况，可能为 `none`、`low`、`medium`、`high`
- `study_duration`：单次学习时长分类，可能为 `unknown`、`short`、`medium`、`long`
- `attention_pattern`：当前注意力模式，可能为 `stable`、`sporadic`、`bursty`
- `dropout_risk`：掉队风险等级
- `dropout_risk_score`：掉队风险分数
- `recent_anomaly`：近期异常，如 `inactive_recently`、`frustration_signal`、`accuracy_drop`

## 5. 如何提供这些可选参数

为了让画像更准确，尽量把以下可选字段按示例格式传入。接口支持部分或全部字段；如果没有历史数据，也会返回低置信度的基础画像。

- `dialogue_text`

```json
"dialogue_text": "我最近在学 Python，函数和循环掌握得不好，想在两周内达到入门水平。"
```

- `learning_records`

```json
"learning_records": [
  {
    "event_type": "study_session",
    "duration_minutes": 45,
    "started_at": 1670000000,
    "source": "web",
    "meta": {"topic": "循环"}
  },
  {
    "event_type": "video_watch",
    "duration_minutes": 12,
    "started_at": "2026-04-01T10:22:00Z",
    "source": "mobile",
    "meta": {"topic": "函数"}
  }
]
```

- `answer_records`

```json
"answer_records": [
  {
    "question_id": 456,
    "correct": false,
    "score": 0,
    "answered_at": 1670003600,
    "time_spent_seconds": 120,
    "meta": {"knowledge_points": ["函数参数"]}
  },
  {
    "question_id": 457,
    "correct": true,
    "score": 1,
    "answered_at": 1670007200,
    "time_spent_seconds": 30,
    "meta": {"knowledge_points": ["循环嵌套"]}
  }
]
```

- `resource_usage`

```json
"resource_usage": [
  {
    "resource_id": "file_123",
    "action": "view",
    "timestamp": 1670010000,
    "duration_seconds": 180
  },
  {
    "resource_id": "video_88",
    "action": "complete",
    "timestamp": "2026-04-02T09:10:00Z",
    "meta": {"knowledge_points": ["函数参数"]}
  }
]
```

前端调用示例：

```javascript
import { getLearningProfile } from '../api/learning_api';

const profile = await getLearningProfile({
  syllabusId: 19,
  dialogueText: '我最近在学 Python，想掌握函数',
  learningRecords: [...],
  answerRecords: [...],
  resourceUsage: [...],
});

// profile.success, profile.profile
```

## 6. 内部逻辑说明

当前实现位于 `tasks/learning_profile_task.py`，核心逻辑分为以下几层。

### 1）上下文读取

- 获取用户基础信息
- 获取用户与课程绑定关系
- 读取个人教学大纲 JSON
- 读取课程标题
- 读取历史问答

### 2）事件归一化

不同输入源会统一归一化成内部事件，以保证后续计算只面对一种结构。

当前会标准化：

- 时间戳解析
- 时长转换为分钟
- 文本扁平化
- 知识点提取
- 资源类型推断

### 3）对话分析

通过关键词和文本信号计算：

- 目标明确度
- 术语熟悉度
- 求助程度
- 自述难度
- 正负向情绪信号

### 4）行为分析

通过学习和资源事件计算：

- 近 7 天活跃天数
- 近 30 天活跃天数
- 平均学习时长
- 资源完成率
- 注意力模式

### 5）答题分析

通过 `answer_records` 中的 `knowledge_points` 聚合计算：

- 每个知识点的尝试次数
- 每个知识点的加权掌握度
- 每个知识点的置信度

这里会做简单的时间衰减：

- 7 天内权重较高
- 30 天内次之
- 更早的数据权重更低

### 6）课程进度分析

如果存在个人教学大纲，会根据每周的：

- `competance`
- `competance_progress`

计算课程级掌握度、薄弱周次和已掌握周次。

### 7）融合与冲突消解

最终掌握度由三部分构成：

- 个人大纲掌握度
- 答题掌握度
- 行为投入度

如果学生“自述很会”但答题表现很差，画像会保留这种冲突，并在 `conflict_resolution` 中明确说明客观数据优先。

### 8）风险与解释

当前实现会额外输出：

- `dropout_risk`
- `dropout_risk_score`
- `recent_anomaly`
- `evidence`
- `confidence`

也就是说，下游模块拿到的不只是结论，还有“为什么这么判断”。

## 7. 推荐接入方式

### 前端

前端在课程详情页、学生详情页或学习分析页调用一次即可，把结果渲染为：

- 当前掌握情况
- 薄弱知识点
- 学习节奏
- 风险提示

### 后端其他模块

- 学习路径规划模块消费 `knowledge_mastery`、`concept_gaps`、`target_level`
- 资源生成模块消费 `learning_style`、`difficulty_tolerance`、`resource_preference`
- 答疑模块消费 `bottleneck_topics`、`emotion_state`、`term_familiarity`
- 风险预警模块消费 `dropout_risk`、`recent_anomaly`、`confidence`

## 8. 文件位置

- 任务实现：`tasks/learning_profile_task.py`
- 接口入口：`blueprint/user_api.py`
- 测试文件：`tests/test_learning_profile.py`
- 文档位置：`docs/learning_profile_agent_workflow.md`

## 9. 使用建议

- 调用时尽量带上 `syllabus_id`，这样画像会贴近具体课程
- 如果前端已经有学习埋点，建议把最近 7 到 30 天的摘要一并传入
- `answer_records` 里尽量补齐 `knowledge_points`，否则知识点级画像会变弱
- 如果只是初始化画像，可以只传 `user_id` 和 `syllabus_id`
- 如果要演示完整效果，建议同时传入对话、学习记录、答题记录和资源使用记录
