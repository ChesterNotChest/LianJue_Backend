# Demo Student Seed contract

本文档收口"演示学生播种"的实现。目标是生成 3 个有真实学习数据的持久化演示学生（低/中/高进度），供前端登录页选择。

## 阶段 1：基础框架 — 画像播种

### 0. 常量定义

```python
WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
DEMO_SUMMARY_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "demo_students"
DEMO_PASSWORD = "demo123"
```

### 1. 影响的文件范围

新增：
- `tests/total_agent/test_seed_demo_students.py`

修改：
- 无。删除 `tests/total_agent/seed_demo_state.py`（旧的空壳脚本）。

### 2. 函数级收口

#### `demo_db_env` fixture

```text
create_app() → app_context
  → 查/建 Syllabus（按 WORKING_SYLLABUS_PATH）
  → 建 User（demo_{level}_{uuid[:8]}，密码 werkzeug hash demo123）
  → 建 UserSyllabus
  → yield (user, syllabus, relation)
  → finally: 不做 DB 清理
```

#### `cleanup_new_json_artifacts` fixture（覆盖 conftest autouse）

```text
yield  # 空操作，conftest 同名 fixture 会在 teardown 删除 /profiles/ 下新 JSON，
       # 此 fixture 覆盖后保留画像文件。
```

#### 画像数据三级定义

模块级 dict，每个 level 一个。结构对齐 `deep_student_state.json` 的 `profile_input_records`：

```python
def _build_profile_input_records(level: str, now_ts: int) -> dict:
    """返回 {dialogue_text, learning_goal, learning_records, answer_records, resource_usage}
    每个 learning_record/answer_record 用 started_at_offset_seconds 相对 now_ts 表达时间。"""
```

| level | learning_records | answer_records | resource_usage | offset 跨度 |
|-------|-----------------|----------------|----------------|------------|
| low | 2 | 1 | 1 | 2-3 天 |
| medium | 6 | 4 | 3 | 42 天 |
| high | 8+ | 5+ | 5+ | 84 天 |

### 3. 内部逻辑

Low 学生：
1. 调用 `lpt.get_or_build_learning_profile(uid, sid, refresh_profile=True, **records)` 
2. 验证：`lpt.get_persisted_learning_profile(uid, sid)` 返回 dict，`profile_saved=True`
3. 写 summary entry。**无计划、无树、无资源。**

Medium/High 学生：
1. 同 Low 构建画像
2. 进入阶段 2（推荐）、阶段 3（学习树）、阶段 4（资源生成）

## 阶段 2：推荐 + 计划播种（Medium/High）

### 0. 常量定义

无新增。

### 1. 影响的文件范围

修改：`tests/total_agent/test_seed_demo_students.py`（同一文件）

### 2. 函数级收口

#### `_run_recommendation_for_demo(user_id, sid, graph_name, goals, learning_goal, question) -> dict`

输入：
```python
user_id: int, syllabus_id: int
graph_name: str  # "RAG"
goals: list[str]  # 从 profile 的 bottleneck_topics 或手动指定
learning_goal: str
question: str
```

输出：
```json
{
  "recommendation": <dict from run_recommendation_route>,
  "snapshot": <dict from save_recommendation_snapshot>,
  "plan": <dict from accept_recommendation_path>,
  "flow": "agent" | "deterministic_retry"
}
```

内部逻辑：
```text
1. 构建 payload:
     {user_id, syllabus_id, goals, question, learning_goal,
      graph_name, rag_top_k=5, decomposer_mode="agent", K=10, beam_width=8}

2. 推荐（两段式）:
   a. prt.run_personal_recommendation_agent(payload) → agent_result
   b. 如果 agent_result.recommendation.best_path 存在 → 使用
   c. 如果不存在:
      - _tokenize_goal_text(question, learning_goal, " ".join(goals)) → tokens
      - _derive_graph_aligned_goals(recommendation, tokens) → alignment
      - 如果 alignment.goals 非空:
          去掉 payload 中的 graph_name/rag_top_k
          注入 aligned goals
          prt.run_recommendation_route_from_payload(aligned_payload) → recommendation
          flow = "deterministic_retry"
      - 如果 alignment.goals 为空 → 返回 error 并终止该学生

3. 快照:
   prt.save_recommendation_snapshot(user_id, sid, recommendation, request_payload=payload)

4. 采纳:
   prt.accept_recommendation_path(user_id, sid, recommendation, candidate_index=0)
   → plan

5. 返回 {recommendation, snapshot, plan, flow}
```

`_tokenize_goal_text` 和 `_derive_graph_aligned_goals` 从 `e2e_cases_large.py` 内联复制，不在模块间导入（避免测试收集依赖）。

### 3. 内部逻辑

Medium goals：`["分布式数据库中典型技术HBase", "HBase"]` — 从 Week6 的 HBase 相关内容来。
High goals：`["HBase RowKey 设计", "预分区策略", "综合复习"]` — 聚焦弱项复习。

`question` 和 `learning_goal` 从画像构建时的 `profile_input_records` 中取。

## 阶段 3：学习树播种（Medium/High）

### 0. 常量定义

无新增。复用 `e2e_cases_amend.py` 中 `_study_change` 和 `_submit_study_batch` 模式。

### 1. 影响的文件范围

修改：`tests/total_agent/test_seed_demo_students.py`（同一文件）

### 2. 函数级收口

#### `_submit_study_batches_for_demo(user_id, sid, subject_title, batches, now_ts) -> dict`

输入：
```python
user_id: int, syllabus_id: int
subject_title: str  # "大数据概论"
batches: list[dict]  # 每个 batch: {phase, timestamp_offset_seconds, changes}
now_ts: int
```

输出：
```json
{
  "tree": <dict from get_student_learning_tree>,
  "features": <dict from get_learning_tree_features>,
  "submit_batches": [<result dicts>]
}
```

内部逻辑：
```text
for each batch:
  1. timestamp = now_ts + batch.timestamp_offset_seconds
  2. for each change in batch.changes:
       _study_change(user_id, sid, key, title,
                     signal=signal, summary=summary,
                     confidence=confidence, parent_title=parent_title, delta=delta)
  3. sgt.submit_learning_tree_changes(user_id, sid, changes,
        source={"kind": "demo_student_seed", "phase": batch.phase},
        timestamp=timestamp, subject_title=subject_title)
4. sgt.get_student_learning_tree(user_id, sid) → tree
5. sgt.get_learning_tree_features(user_id, sid) → features
```

#### `_study_change`（内联复制自 `e2e_cases_amend.py:165-193`）

```python
def _study_change(uid, sid, key, title, *, signal, summary, confidence=0.9, parent_title="", delta=None):
    change = {
        "op": "upsert_knowledge_node",
        "client_change_id": f"demo-seed:{uid}:{sid}:{key}",
        "knowledge": {"title": title, "summary": summary, "aliases": [title]},
        "mastery": {"signal": signal, ...},
        "confidence": confidence,
    }
    if parent_title:
        change["parent_candidate"] = {"title": parent_title}
    return change
```

### 3. 批次设计

#### Medium（5 batches，~7 nodes）

| phase | offset | changes |
|-------|--------|---------|
| mastered_foundations | -21天 | 大数据基础(mastered), HDFS基础(mastered) |
| data_perception_etl | -14天 | 数据感知(mastered), ETL过程(practiced) |
| hbase_start | -4天 | HBase 基础(struggled) |
| hbase_model | -3天 | HBase 数据模型(learned) |
| hdfs_detail | -20天 | HDFS读写流程(practiced) |

weak_topics 预期：HBase 基础
mastered_topics 预期：大数据基础, HDFS 基础

#### High（9 batches，~14 nodes）

复用 `deep_student_state.json` 的 9 个批次结构，offset 比例缩放到 84 天跨度。
预期 weak_topics 含 HBase RowKey 设计、RowKey 热点、预分区。
预期 mastered_topics 含 大数据基础、HDFS 基础、MapReduce 基础、非关系型数据库基础。
预期 stale_topics 含 MapReduce 基础。

## 阶段 4：资源播种（Medium/High）

### 0. 常量定义

无新增。

### 1. 影响的文件范围

修改：`tests/total_agent/test_seed_demo_students.py`（同一文件）

### 2. 函数级收口

#### `_generate_demo_resource(user_id, sid, step, graph_name, resource_type) -> dict`

输入：
```python
user_id: int, syllabus_id: int
step: dict  # learning plan 的 active step，含 title, outcomes
graph_name: str
resource_type: str  # "documents" | "mindmap"
```

输出：`gt.generate_resources_from_request(...)` 的返回值

内部逻辑：
```text
gt.generate_resources_from_request({
    "user_id": user_id,
    "syllabus_id": syllabus_id,
    "question": f"请为 {step.title} 生成学习资料",
    "topic": step.title,
    "learning_objectives": step.outcomes,
    "resource_types": [resource_type],
    "graph_name": graph_name,
    "generation_requirements": {"model_tier": "standard"},
})
```

注意：`model_tier` 用 `"standard"` 而非 `"cheap"`，保证演示质量。

### 3. 内部逻辑

- Medium：生成 `documents`，topic 取自 active step（大概率是 Week6 HBase 相关）
- High：生成 `mindmap`，topic 取自 active step（大概率是 RowKey 复习相关）

资源落盘路径由 conftest 的 `GENERATIVE_FILE_BACKEND=1` 控制，写入 `<backend_root>/generative/user_{uid}/{type}/...`。

## 阶段 5：Summary 输出

### 2. 函数级收口

#### `_write_demo_summary_entry(entry) -> None`

输入：
```python
entry: {
    "level": "low" | "medium" | "high",
    "user_id": int, "user_name": str,
    "syllabus_id": int, "password": "demo123",
    "profile_path": str | None,
    "learning_plan_id": str | None,
    "recommendation_snapshot_id": str | None,
    "study_graph_node_count": int | None,
    "generated_resource_id": str | None,
    "current_step_title": str | None,
    "created_at": int,
}
```

内部逻辑：
```text
1. DEMO_SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
2. 读取已有 summary.json（如果有）
3. 追加/更新 entry（按 level 去重，保留最新）
4. 写入 summary.json
```

## 最终验收标准

- 3 个独立测试函数，`pytest -k demo_low` 单独通过
- 运行后 `/profiles/` 下新增 3 份画像文件
- Medium/High 的 `manifest.jsonl` 学习计划文件存在
- Medium/High 的 `study_graph/` 下 `manifest.json` 存在
- Medium/High 的 `generative/` 下资源文件存在
- `tests/artifacts/total_agent/demo_students/summary.json` 含 3 条记录
- 前端用 summary.json 中的 user_id + demo123 可登录
- `seed_demo_state.py` 可删除
