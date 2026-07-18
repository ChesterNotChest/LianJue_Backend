## Context

QuizAttempts 在 CourseLayout 内渲染。数据来自 `generative_list` (type=quiz) + `quiz_attempts` API。每张测验卡片为三栏布局：左 320px（测验标识+按钮）、中 360px（成绩摘要+薄弱点）、右 200px（提交历史）。

## 数据流

```
CourseLayout → <Outlet /> → QuizAttempts
  │
  ├── POST /api/generative_list {user_id, syllabus_id, resource_type:"quiz"}
  │     → {materials: [ResourceSummary]}
  │
  ├── GET /api/quiz_attempts?user_id=N&syllabus_id=S
  │     → {attempts: [{resource_id, score, correct_count, total_questions, weak_topics, created_at}]}
  │
  └── Merge: materials.map(r → {...r, attempts: attemptsMap[r.resource_id]})
```

## 函数级收口

### QuizCard 组件
- **输入**: `{quiz: ResourceSummary, attempts: QuizAttempt[]}`
- **输出**: `880×200 rx=12` 三栏卡片

#### Left: QuizIdentity
- `280×168 rx=8 fill=#fef3c7` (amber background)
- "测验" badge 10px/600/#f59e0b
- Title 16px/700/#0f172a
- Description: 2 lines 11px/#64748b
- "开始测验"/"重新测验" btn: `100×28 rx=8 fill=#f59e0b` + text 11px/700/white
- "查看详情" btn: `72×28 rx=8 fill=#fff stroke=#e2e8f0` + text 10px/#64748b

#### Middle: ScoreSummary
- "成绩摘要" header 10px/600/#64748b
- **Best card**: `160×48 rx=8` — completed → green `fill=#dcfce7 stroke=#bbf7d0`; ≥70% → amber `fill=#fef3c7 stroke=#fde68a`
  - "最佳" 9px/600 + score 18px/800 + "N/M 正确" 9px + "第 N 次提交" 9px
- **Recent card**: `160×48 rx=8 fill=#f8fafc stroke=#e2e8f0`
  - "最近" 9px/600 + score 18px/800 + "N 次提交" 9px + "最后" 9px
- **Weak points**: `344×44 rx=6 fill=#fef2f2`
  - red tag chips (10px/#ef4444) + amber tag (10px/#f59e0b) + note text 9px/#94a3b8

#### Right: AttemptHistory
- "提交历史" header 10px/600/#64748b
- 3 entries: `160×28 rx=6`, fill=#fff or #fef2f2 (if <70%)
  - Circle: green r=4 if ≥70%, red if <70%
  - "第 N 次 · X%" 10px + score "N/M" 9px/#94a3b8 right-aligned

### UntouchedCard
- `880×120 rx=12 fill=#fafafa stroke=#e2e8f0 strokeDasharray=5,3`
- Left: gray `280×88 rx=8 fill=#f1f5f9` + "测验" 10px/600/#94a3b8 + title 16px/700/#94a3b8 + "N 题 · 尚未作答" 11px/#cbd5e1 + "开始测验" btn `100×28 rx=8 fill=#6366f1`
- Right: gray placeholder text

### StatsBar
- 4 列: 可用测验 (total) / 已完成 (completed count, green) / 平均得分 (avg score%, green) / 薄弱知识点 (weak topic count, red)
- 从 attempts 数组聚合计算
