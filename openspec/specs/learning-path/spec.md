# Learning Path Recommendation

学习路径推荐模块。基于用户画像、课程大纲和学习树，生成可解释、可排序的学习路径候选，支持快照缓存和计划管理。

## API Endpoints

### POST /api/personal_recommendation
运行个性化学习路径推荐。
- **Input**: `{user_id, syllabus_id, goals: [str], L_max?, K?, beam_width?}`
- **Output**: `{recommendation_id, graph: {nodes, edges}, candidates: [{path, score, ...}], best_path, selected}`

### GET /api/recommendations
列出推荐快照。
- **Query**: `?user_id=N&syllabus_id=N`
- **Output**: `[{recommendation_id, status, created_at, ...}]`

### GET /api/recommendations/<recommendation_id>
获取单个推荐快照详情。
- **Output**: `{graph, candidates, best_path, selected, rag_overlay, planning_hints}`

### POST /api/recommendations/<recommendation_id>/accept
采纳推荐快照中的一条路径，创建 active learning plan。
- **Input**: `{user_id, syllabus_id, candidate_index}`
- **Output**: `{plan_id, steps: [{step_id, title, order_index, status}]}`

### GET /api/learning_plan
获取当前活跃的学习计划。
- **Query**: `?user_id=N&syllabus_id=N`
- **Output**: `{plan_id, status, steps: [{step_id, node_id, title, outcomes, order_index, status, resource_ids}]}`

## Data Flow

```
payload (user_id + syllabus_id + goals)
  → load_request_context (profile + personal_syllabus + study_graph_features)
  → search_recommendation_context (RAG overlay)
  → run_recommendation_route
      → state perception (perception.py)
      → candidate generation (A* search, candidate_generator.py)
      → hard prune (time/deadline constraints, pruning.py)
      → score (evaluator.py: efficiency, difficulty, risk, preference, granularity, confidence)
      → soft prune (Pareto dominance, pruning.py)
      → IB-GRPO selection (selector_ib_grpo.py)
  → return graph + candidates + best_path
```

推荐快照（Recommendation Snapshot）是展示缓存，不代表学生已进入学习。只有 accept 才创建 active learning plan。

## State Machines

### Recommendation Snapshot
```
proposed → accepted | expired
```

### Learning Plan
```
active → completed | superseded | abandoned
```

### Learning Plan Step
```
pending → active → completed | skipped
```

## Data Model

```
learning_plan                    recommendation_snapshot
├── plan_id (PK)                 ├── recommendation_id (PK)
├── user_id (FK→user)            ├── user_id
├── syllabus_id                  ├── syllabus_id
├── status                       ├── session_id
├── source                       ├── status (proposed/accepted/expired)
├── candidate_index              ├── graph_json (LONGTEXT)
├── path_json                    ├── candidates_json (LONGTEXT)
├── created_at                   ├── selected_json (LONGTEXT)
└── updated_at                   ├── best_path_json (LONGTEXT)
                                 ├── accepted_plan_id
learning_plan_step               ├── accepted_candidate_index
├── step_id (PK)                 ├── created_at / updated_at
├── plan_id (FK)                 └── expires_at
├── node_id
├── title                        learning_plan_event
├── outcomes_json                ├── entry_id (PK)
├── order_index                  ├── plan_id (FK)
├── status                       ├── user_id
├── resource_ids_json            ├── step_id
├── created_at                   ├── event_type
└── updated_at                   ├── payload_json
                                 └── created_at
```

## Known Issues

- `tool_run_learning_recommendation` 直调确定性函数，未过 `run_personal_recommendation_agent`（旁路）
- 推荐结果 ~150KB（含完整 graph），message_history 接入后需瘦身
- 跨轮 pending recommendation 不 restore

## Integration

- 读取 Learning Profile（build_recommendation_profile）
- 读取 Study Graph（只读 study_graph_state，不写入）
- 可被 Total Agent 的 `accept_recommendation_path` 创建 active plan
- RAG overlay 是软增强，不修改原始 syllabus JSON
