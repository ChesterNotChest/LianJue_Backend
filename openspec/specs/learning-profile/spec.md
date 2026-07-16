# Learning Profile

学习画像模块。构建、读取和持久化用户学习画像，管理个人教学大纲（personal syllabus）的初始化和建议更新。

## API Endpoints

### POST /api/learning_profile_detail
获取已持久化的学习画像（只读，不触发 agent 构建）。
- **Input**: `{user_id, syllabus_id}`
- **Output**: `{profile: {learning_style, overall_score, practice_ability, bottleneck_topics, weak_points, strong_points, resource_preference, ...}}`

### POST /api/learning_profile_refresh
构建或刷新学习画像（触发 agent 管线）。
- **Input**: `{user_id, syllabus_id, dialogue_text?, learning_goal?}`
- **Output**: `{profile, tool_trace}`

### POST /api/learning_init_personal_syllabus
为用户初始化个人教学大纲。
- **Input**: `{user_id, syllabus_id}`
- **Output**: `{personal_syllabus}`

### POST /api/learning_personal_syllabus_detail
获取个人教学大纲详情（含知识点掌握度）。
- **Input**: `{user_id, syllabus_id}`
- **Output**: `{personal_syllabus: {period: [{week_index, content, competance, competance_progress, ...}]}}`

### POST /api/resource_usage
记录资源查看事件（用于画像分析的停留时长）。
- **Input**: `{user_id, resource_id, syllabus_id?, duration_seconds?}`

## Data Flow

```
history_entries + dialogue_texts + answer_records + resource_usage
  → normalize_events
  → compute_features (feature_bundle)
  → assemble_profile (完整 profile dict)
  → save_personal_profile → /profiles/{syllabus_id}-{user_id}.json
```

## Profile Structure

```
{
  learning_style: str,
  overall_score: float,        // 0.0-1.0
  practice_ability: float,
  bottleneck_topics: [str],
  weak_points: [str],
  strong_points: [str],
  resource_preference: {...},
  learning_records: [...],     // 学习事件记录
  answer_records: [...],       // 答题记录
  resource_usage: [...],       // 资源使用记录
  knowledge_mastery: {
    week_items: [{week_index, competance, ...}],
    knowledge_point_details: [...]
  }
}
```

## Personal Syllabus

```
/schedule/student_alt/user_{user_id}/{syllabus_id}_personal.json
├── period: [{week_index, content, enhanced_content, competance, competance_progress, suggestions[]}]
```

周状态推进通过 suggestion 累积，达 `WEEK_REVIEW_THRESHOLD=5` 后推进 competance。

## Competance 状态

```
none → weak → normal → mastered
          ↑ 5 weak suggestions 累积后推进
                    ↑ 5 master_far suggestions 累积后推进
```

## Known Issues

- Total Agent 的 `tool_note_profile_observation` 直写 profile JSON（旁路），未通过 `run_learning_profile_agent`
- `quiz_attempts.py` 的 answer_records 直写 profile，未通过 profile agent

## Integration

- 被 Total Agent（`load_total_context` 阶段）读取
- 被 Recommendation Agent（画像感知）读取
- 持久化依赖 `user_syllabus.personal_profile_path` 和 `user_syllabus.personal_syllabus_path`
- 文件后端（无独立数据库表）
