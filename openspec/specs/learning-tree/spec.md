# Learning Tree (Study Graph)

学习成长树模块。维护学生的个人知识树，只记录已触达的知识节点，提供课程/班级聚合摘要。

## Core Rules

- 每个 `user_id + syllabus_id` 维护一棵个人学习成长树
- **只放已触达节点**：学生学过的、提问过的、练习过的、答错的、被大纲确认过的
- **不预铺课程地图**：未学习内容不出现在树中
- **只维护 `parent_of` 边**：推荐边、资源边、题目边、审计边不进入主树
- **Student Agent 只提交变更候选**：归一化、去重、父节点裁决、低置信拦截由 service 层完成

## API Endpoints

### GET /api/study_graph/detail
获取学习图谱树。
- **Query**: `?user_id=N&syllabus_id=N`
- **Output**: `{tree: {nodes: [...], edges: [...], summary}, tree_id}`

### GET /api/study_graph/features
获取学习树特征（掌握度统计）。
- **Query**: `?user_id=N&syllabus_id=N`
- **Output**: `{features: {mastered_node_ids: [...], weak_node_ids: [...], learning_node_ids: [...], learned_node_ids: [...], stale_node_ids: [...], recently_grown_node_ids: [...], tree_growth: {...}}}`

### POST /api/study_graph/agent_run
运行 Student Agent 以更新/分析学习图谱。
- **Input**: `{user_id, syllabus_id, detected_topics?: [{title, confidence, signal}], events?: [...], rag_context?: [...], parent_candidates?: [...]}`
- **Output**: `{tree, features, changes: [{status, ...}], tool_trace}`

## Data Flow (Write Path)

```
Total Agent payload
  → Student Agent (student_agent.py)
      → rag_search (RAG 检索)
      → get_tree_context (当前树状态)
      → build_changes (含 parent_candidate 解析)
      → submit_changes
  → service.apply_learning_tree_changes
      → 归一化 → 去重 → 父节点裁决 → 低置信拦截
      → 掌握度更新 → 展示状态更新
  → read tree + features
```

## State Machines

### 变更候选
```
accepted | merged | rejected | needs_review | skipped
```

`needs_review`/`rejected`/`skipped` 只写 change log，不写节点。

### 掌握度 (Mastery)
```
weak → learning → normal → mastered
```
Delta 驱动: `learned +0.15, practiced +0.08, struggled -0.12, mastered +0.25`

### 展示状态
```
growth_stage: seed → sprout → branch → fruit
color_state:  weak → growing → stable → mastered
```

## Data Model

```
study_graph_tree                    study_graph_node
├── tree_id (PK)                    ├── node_id (PK)
├── user_id (FK→user)               ├── tree_id (FK)
├── syllabus_id (FK→syllabus)       ├── type ("knowledge"|"tree_root")
├── title                           ├── title
├── summary_json                    ├── normalized_title
├── manifest_json                   ├── parent_node_id
├── created_at / updated_at         ├── mastery_json
                                    ├── mastery_label (weak/learning/normal/mastered)
study_graph_edge                    ├── mastery_score
├── edge_id (PK)                    ├── display_json
├── tree_id (FK)                    ├── source_json
├── source_node_id                  ├── first_seen_at
├── target_node_id                  └── last_updated_at
├── edge_type ("parent_of")
├── created_at / updated_at         study_graph_change_log
                                    ├── id (PK)
                                    ├── tree_id (FK)
                                    ├── client_change_id
                                    ├── status
                                    ├── request_json / result_json
                                    └── created_at
```

## Known Issues

- Total Agent 的 `record_learning_feedback` 旁路 Student Agent，直调 `submit_learning_tree_changes`（无 parent_candidate、无 evidence 评分、无 RAG 融合）→ 知识树可能是散点
- 复杂证据和事件明细只进入 change log，不把主树变成审计系统

## Integration

- 被 Total Agent 读取（`load_total_context` → `get_study_graph_features`）
- 被 Study Buddy 读取（构建学伴树的 learned/explore 层）
- 推荐模块只读 study_graph_state，不写入
- Course Learning Tree Summary 提供班级聚合（隐私边界：只输出聚合统计）
- 持久化：DB 表（生产）+ 文件 manifest（测试）
