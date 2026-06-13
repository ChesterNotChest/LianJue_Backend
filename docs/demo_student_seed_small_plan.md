# Demo Student Seed small plan

本文档收口"演示学生播种"的设计。目标是生成 3 个有真实学习数据的演示学生（低/中/高进度），供前端登录页选择并展示完整联觉平台能力。

## 1. 背景判断

已有能力：
- `deep_student_state.json` fixture 存储了一个学生的画像输入、推荐路径、学习树变更批次、消息模板。
- `e2e_cases_real_deep_state.py` 中 `_build_real_deep_state()` 可用真实 LLM/RAG/DB 构建完整学生状态，但存储落在 `tests/artifacts/` 且会被 `_reset_artifact_root` 清掉。
- `e2e_cases_amend.py` 中 `_save_fixture_profile()`、`_submit_deep_study_graph()` 等 helper 已验证了画像持久化、学习树批次提交的模式。

缺失能力：
- 没有"向真实路径播种演示学生"的 opt-in 测试。
- 前端登录页需要预置学生，但当前只能靠 E2E 测试残留的临时用户。
- 每次重建需要手动跑多个脚本，不可复现。

## 2. 目标

新增 `tests/total_agent/test_seed_demo_students.py`，opt-in 运行后产生 3 个持久化演示学生。

目标能力：
- 3 个独立测试函数，可单独运行（`pytest -k demo_low`）。
- 用户名带时间戳后缀（`demo_low_{uuid[:8]}`），每次运行生成新用户，不冲突。
- 画像通过真实 LLM Agent 构建，落到 `<CWD>/profiles/<sid>-<uid>.json`。
- 中/高学生通过真实推荐 Agent（含 deterministic fallback）产生学习计划。
- 中/高学生有学习树（study graph batch changes）和生成的资源（documents / mindmap）。
- 运行后输出 `tests/artifacts/total_agent/demo_students/summary.json`，含 user_id、username、密码、各层路径。
- 覆盖 conftest 的 `cleanup_new_json_artifacts`，防止画像文件被 autouse fixture 删除。

非目标：
- 不做 monkeypatch 存储重定向。所有数据写到生产路径。
- 不做 DB 清理。演示用户持久保留。
- 不做前端对接。本模块只负责后端数据准备。
- 不替代 E2E 测试。本模块是数据播种，不是回归验证。

## 3. 三个学生规格

### Low（~Week 1-2）

| 层 | 内容 |
|---|---|
| 画像 | 2 条学习记录 + 1 条答题 + 1 条资源使用，offset 2-3 天 |
| 学习计划 | 无 |
| 学习树 | 无 |
| 生成资源 | 无 |

目标：展示"新用户刚起步"的空状态。前端左侧栏显示空学习计划，右侧无画像数据，知识树几乎为空。

### Medium（~Week 6）

| 层 | 内容 |
|---|---|
| 画像 | 6 条学习记录（Week1-5 已掌握 + HBase 挣扎中），4 条答题，3 条资源使用，offset 42 天跨度 |
| 学习计划 | 真实推荐 Agent → deterministic fallback → accept → snapshot |
| 学习树 | 5 batches，~7 nodes（大数据基础/HDFS mastered，ETL practiced，HBase struggled） |
| 生成资源 | `documents` 类型，topic 取自 active step |

目标：展示"学到一半"的标准状态——有已掌握节点、薄弱点、当前计划、已生成的学习资料。前端三个面板都有内容。

### High（~Week 12）

| 层 | 内容 |
|---|---|
| 画像 | 8+ 学习记录，覆盖 12 周，offset 84 天跨度 |
| 学习计划 | 真实推荐 Agent → fallback → accept → snapshot |
| 学习树 | 9 batches，~14 nodes（与 `deep_student_state.json` 结构对齐） |
| 生成资源 | `mindmap` 类型用于复习 |

目标：展示"深度学习"的丰富状态——大量 mastered 节点、stale topics、薄弱点聚焦、综合复习阶段。

## 4. 持久化路径

由于 conftest 设置了 `*_FILE_BACKEND=1` 和 `monkeypatch.chdir(ROOT)`：

| 层 | 路径（相对于 `<backend_root>`） |
|---|---|
| 画像 | `../profiles/<syllabus_id>-<user_id>.json` |
| 学习计划 | `personal_recommendation/learning_plan/user_{uid}/syllabus_{sid}/manifest.jsonl` |
| 学习树 | `study_graph/user_{uid}/syllabus_{sid}/manifest.json` |
| 生成资源 | `generative/user_{uid}/{resource_type}/...` |
| 推荐快照 | DB（conftest 未设 `RECOMMENDATION_SNAPSHOT_FILE_BACKEND`） |
| Summary | `tests/artifacts/total_agent/demo_students/summary.json` |

## 5. 文件结构

```
tests/total_agent/test_seed_demo_students.py   # 单一模块，3 个测试函数 + 共享 helper
tests/artifacts/total_agent/demo_students/     # 运行产物目录
  summary.json                                 # 运行摘要
```

## 6. 共享 helper 设计

从 `e2e_cases_large.py` 和 `e2e_cases_amend.py` 复用或内联：

| 函数 | 来源 | 用途 |
|---|---|---|
| `_require_seed_demo_env()` | 适配 `_require_large_e2e_env` | opt-in gate |
| `_run_recommendation_for_demo()` | 适配 `_run_recommendation_attempt` + `_derive_graph_aligned_goals` | 推荐→快照→采纳 |
| `_submit_study_batches_for_demo()` | 适配 `_submit_deep_study_graph` | 学习树批次提交 |
| `_generate_demo_resource()` | 适配 `_run_current_step_resource_and_feedback` | 单资源生成 |
| `_write_demo_summary_entry()` | 新写 | 写入 summary.json |
| `_tokenize_goal_text` / `_derive_graph_aligned_goals` | 从 `e2e_cases_large` 复制 | 目标对齐 fallback |

### `_run_recommendation_for_demo` 流程

```text
1. 构建 payload（user_id, syllabus_id, goals, learning_goal, question, graph_name, rag_top_k）
2. prt.run_personal_recommendation_agent(payload) → agent_result
3. 如果 agent_result.recommendation.best_path 存在 → 使用
4. 如果不存在：
   a. _tokenize_goal_text(question, learning_goal, " ".join(goals))
   b. _derive_graph_aligned_goals(recommendation, user_goal_tokens)
   c. 如果对齐出 goals → 去掉 graph_name/rag_top_k，走 run_recommendation_route_from_payload
   d. 如果对齐失败 → 返回 error（测试 skip）
5. prt.save_recommendation_snapshot(user_id, sid, recommendation)
6. prt.accept_recommendation_path(user_id, sid, recommendation, candidate_index=0)
7. 返回 {recommendation, snapshot, plan, flow}
```

### `_submit_study_batches_for_demo` 流程

```text
1. 接收 batches 列表，每个 batch 含 phase, timestamp_offset_seconds, changes
2. 遍历 batches：
   a. 计算绝对时间戳 = now_ts + offset
   b. 每个 change 调用 _study_change(key, title, signal, summary, parent_title, ...)
   c. sgt.submit_learning_tree_changes(user_id, sid, changes, source={kind, phase}, timestamp)
3. sgt.get_student_learning_tree(user_id, sid) → 验证节点数
4. sgt.get_learning_tree_features(user_id, sid) → 验证 weak/mastered/stale 分类
5. 返回 {tree, features, submit_batches}
```

## 7. 关键设计决策

### conftest cleanup 覆盖
```python
@pytest.fixture(autouse=True)
def cleanup_new_json_artifacts():
    yield  # 空操作，不删除 profiles/
```
此 fixture 必须在模块内定义，覆盖 conftest 同名 autouse fixture。

### demo_db_env fixture
- 在 `create_app().app_context()` 内创建 User + Syllabus + UserSyllabus
- `finally` 块不做 DB 清理
- fixture scope 默认 function，每次测试独立

### graph_name 传递
- 从 `os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"` 获取
- 画像构建不需要 graph_name，推荐和资源生成需要

### 密码
- 使用 werkzeug `generate_password_hash("demo123")`，前端登录页直接用 demo123

## 8. 测试计划

非 pytest 测试（本模块本身就是测试），验证方式：

- 运行后检查 `summary.json` 含 3 个 entry
- `lpt.get_persisted_learning_profile(uid, sid)` 返回有效画像
- Medium/High: `prt.get_active_learning_plan(uid, sid)` 返回非空计划
- Medium/High: `sgt.get_student_learning_tree(uid, sid)` 返回节点数 >= 预期
- Medium/High: 磁盘上存在生成资源文件
- 前端登录页用 summary.json 中的 user_id 可正常进入

## 9. 验收标准

- 3 个独立测试函数，`pytest -k demo_low` 单独通过
- 运行后 `/profiles/` 下有 3 份画像文件
- Medium/High 有完整学习计划和学习树
- Medium/High 的生成资源文件存在
- `summary.json` 含 3 条记录，字段完整
- 不因 conftest autouse cleanup 丢失数据
- `seed_demo_state.py` 可删除（被本模块替代）
