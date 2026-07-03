# Demo Student Seed Contract

本文档收口演示学生播种的当前实现。目标是生成 5 个持久化演示学生，并且每个学生都对 `8 / 18 / 104` 三个学科走一致的数据链路。

## 目标

- 学生层级：`low`、`low_medium`、`medium`、`medium_high`、`high`。
- 学科范围：每个演示学生都绑定并播种 `DEMO_SYLLABUS_IDS = [8, 18, 104]`。
- 链路要求：每个学生、每个学科都从标准系统输入点开始，依次调用真实画像、推荐、学习树、资源生成入口。
- mock 边界：仅构造用户提问、学习记录、答题记录、资源使用记录等真实系统输入；不手工拼最终画像、推荐结果、学习树或生成资源。

## 运行入口

```powershell
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v
```

单档可单独运行：

```powershell
RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v -k demo_medium
```

## 数据链路

每个测试函数创建一个新用户：

```text
create_app() -> app_context
  -> 校验 syllabus 8/18/104 都存在
  -> 创建 User，用户名 demo_{level}_{uuid[:8]}，密码 demo123
  -> 为 8/18/104 创建 UserSyllabus
  -> 对每个学科循环执行完整播种
```

每个学科执行：

```text
1. _build_profile_input_records(level, now_ts, subject_title)
2. lpt.get_or_build_learning_profile(..., refresh_profile=True, 输入记录...)
3. prt.run_personal_recommendation_agent(payload)
4. 必要时用 _derive_graph_aligned_goals 做 deterministic retry
5. prt.save_recommendation_snapshot(...)
6. sgt.submit_learning_tree_changes(...) 批量提交学习树变化
7. generate_resources_from_request(...) 生成资源
8. 写入 summary.json 的 subjects[] 条目
```

## 五档差异

| level | 输入状态 | 学习树规模 | 资源类型 |
|---|---|---:|---|
| `low` | 刚开始学习导论和基础术语 | >= 2 nodes | `documents` |
| `low_medium` | 学过前几讲，但概念边界不稳 | >= 4 nodes | `quiz` |
| `medium` | 完成基础和部分核心模块，当前模块有薄弱点 | >= 5 nodes | `documents` |
| `medium_high` | 多数基础完成，开始跨章节综合应用 | >= 6 nodes | `ppt` |
| `high` | 大部分内容完成，聚焦高阶综合和易错复盘 | >= 10 nodes | `mindmap` |

这些差异不是简单子集关系。各档使用不同输入记录、学习树批次、推荐问题和资源类型，但都经过同一真实链路。

## Summary 输出

路径：

```text
tests/artifacts/total_agent/demo_students/summary.json
```

结构：

```json
{
  "level": "medium_high",
  "user_id": 123,
  "user_name": "demo_medium_high_ab12cd34",
  "syllabus_ids": [8, 18, 104],
  "password": "demo123",
  "subjects": [
    {
      "syllabus_id": 8,
      "subject_title": "学科标题",
      "profile_path": "...",
      "learning_plan_id": null,
      "recommendation_snapshot_id": "...",
      "study_graph_node_count": 6,
      "generated_resource_id": "...",
      "generated_resource_type": "ppt",
      "current_step_title": "..."
    }
  ],
  "created_at": 1780000000
}
```

按 `level` 去重，保留最新一次运行的用户。

## 前端接口

`GET /api/demo_students` 返回最新 5 个 `demo_%` 用户，包含：

- `user_id`
- `user_name`
- `level`
- `syllabus_ids`
- `created_at`

前端登录页展示最新 5 个播种学生，并显示层级和已绑定学科 ID。

## 验收标准

- 5 个独立测试函数存在，并可按 `-k demo_low` 等方式单独运行。
- 每个测试函数生成 1 个用户，并对 `8/18/104` 三个学科执行完整链路。
- 每个学科都有持久化画像、推荐快照、学习树和生成资源。
- `summary.json` 含 5 个 level 的最新记录，每条记录包含 3 个 `subjects`。
- `/api/demo_students` 默认返回 5 个最新播种学生，且能识别 `low_medium`、`medium_high`。
