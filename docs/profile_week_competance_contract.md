# Profile Week Competance 推进 — Implementation Contract

## Phase 0: 全链路逻辑澄清

### 两条线，两个问题

```
学习事件 (答题/学习记录)
  │
  └─→ profile agent
        │
        └─→ by_knowledge_point: {"HDFS 基础": 0.86, "ETL": 1.0}
              │
              ├─→ [问题1] 推荐层: 分数关联不到课程节点
              │     │
              │     │  课程节点叫 "分布式文件系统及主流技术HDFS"
              │     │  标签叫 "HDFS 基础"
              │     │  对不上 → 推荐以为"什么都没学过"
              │     │
              │     └─→ 已修复: perception.py 语义对齐
              │
              └─→ [问题2] 画像层: week 级 competance 永远是 "none"
                    │
                    │  by_knowledge_point 有数据但没回写到 personal syllabus
                    │
                    └─→ 本次修复: sync_knowledge_to_weeks()
```

### 推荐算法完整流程（含语义对齐的位置）

```
1. 加载画像
     profile = build_recommendation_profile(uid)
       └─ knowledge_mastery.by_knowledge_point = {"HDFS 基础": 0.86, "ETL": 1.0}

2. 构建学习树
     learning_tree = syllabus_json_to_learning_tree(syllabus)
       └─ {"n5": {title: "大数据存储与管理", outcomes: ["分布式文件系统及主流技术HDFS"]}}

3. 生成搜索状态 ← 语义对齐插在这里
     knowledge = _normalize_knowledge_levels(profile)
       └─ {"HDFS 基础": 0.86, "ETL": 1.0}

     knowledge = _llm_align_knowledge(knowledge, learning_tree)   ← 语义对齐
       └─ + {"大数据存储与管理": 0.86, "分布式文件系统...": 0.86}  ← 富化

     state, start_nodes = generate_state(profile, tree)
       │
       │  _node_outcomes_known(node, knowledge):
       │    对每个 outcome 做 knowledge.get(outcome)
       │    之前 "分布式文件系统…" 不在 knowledge 里 → miss → False
       │    现在 富化后有了 → 0.86 > 0 → True ✅ → 节点标记为 known
       │
       └─ start_nodes = [n6, n7, ...]  ← 不包含 n1-n5（已掌握）
                               ← 搜索从这里开始，跳过前5周

4. Beam 搜索生成候选路径
     generate(start_nodes, goals, tree, state, L_max=6, ...)
       │
       │  从 start_nodes 出发，beam_width 条并行展开
       │  每步检查: blocked? cost超限? 路径重复?
       │  覆盖到 goal outcomes 时产出候选
       │
       └─ candidates = [{path: [n6, n8, n9], cost: 8.5, skills: {...}}, ...]

5. 剪枝 + 打分 → 选出 best_path
     hard_prune → score → soft_prune → 最终推荐路径
```

**语义对齐的作用：** 插在第 3 步，让 `_node_outcomes_known` 能从 `knowledge` dict 里查到长 syllabus 文本对应的分数——使得已掌握节点被正确跳过，`start_nodes` 从学生真正不会的地方开始。

### 语义对齐在两处的复用

| 位置 | 输入 | 输出 | 解决什么 |
|------|------|------|----------|
| perception.py | knowledge_point标签 + 课程节点标题 | knowledge dict 富化（节点标题→分数） | 推荐跳过已掌握节点 |
| personal_syllabus.py (新增) | knowledge_point标签 + syllabus 周content | 每周 competance 值 | 画像雷达有区分度 |

同样的匹配逻辑做两件事——把短标签对到长文本。

### 为什么不用旧堆叠机制

旧的 suggestion → stacking → 晋级：需要每个周累计 5 条 suggestion 才晋级一次。
适合渐进式学习（每周慢慢推），但对于批量同步（seed 一次性模拟、profile rebuild）太重且不必要。

改为直接设 `competance`：根据 `by_knowledge_point` 的分数一次性定档。
- > 0.7 → competance = "master"
- > 0.35 → competance = "normal"  
- > 0 → competance = "weak"
- == 0 → competance 保持 "none"（该周无相关知识点）

---

## Phase 1: 新增常量

| 常量 | 值 | 位置 | 说明 |
|------|----|------|------|
| `_COMPETANCE_THRESHOLD_MASTER` | `0.7` | `personal_syllabus.py` | 分数 ≥ 此值设 master |
| `_COMPETANCE_THRESHOLD_NORMAL` | `0.35` | `personal_syllabus.py` | 分数 ≥ 此值设 normal |

无需环境变量——这是确定性逻辑。

---

## Phase 2: 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `tasks/learning_profile/personal_syllabus.py` | 修改 | 新增 `sync_knowledge_to_weeks()` |
| `tasks/learning_profile/service.py` | 修改 | `build_learning_profile` 末尾调 sync |

**两文件改动，不涉及 agent 层。**

---

## Phase 3: 函数级完整数据流

```
build_learning_profile(user_id, sid, events...)          [service.py]
  │
  ├─ profile agent 运行
  │     └─→ state['profile'] 产出
  │           └─ knowledge_mastery.by_knowledge_point: {"HDFS 基础": 0.86, ...}
  │
  ├─ _tool_save_or_update_profile(state)                  # 已存在，持久化 profile JSON
  │
  └─ sync_knowledge_to_weeks(user_id, sid)               ← NEW
        │
        ├─ 读 profile: by_knowledge_point
        │
        ├─ 读 syllabus: 16周的 content
        │
        ├─ 调用 perception._llm_align_knowledge_lite()   ← 复用 LLM 对齐
        │     │  输入: knowledge={"HDFS 基础": 0.86}, candidates=["分布式文件系统...", ...]
        │     │  输出: {"分布式文件系统及主流技术HDFS": "HDFS 基础", ...}
        │     │
        │     └─→ 映射表: 第5周content → "HDFS 基础"
        │
        ├─ 遍历16周:
        │     查该周 content 是否有匹配的 knowledge_point
        │     有 → 设 competance 为对应档位
        │     无 → 保持 none
        │
        └─ 写入 personal syllabus JSON（一次 write）
```

---

## Phase 4: 函数级收口

### 4.1 `sync_knowledge_to_weeks(user_id, syllabus_id) -> dict | None`

**输入：**
- `user_id: int`
- `syllabus_id: int`

**输出：**
- 成功: `{"synced_weeks": 3, "competance_before": {...}, "competance_after": {...}}`
- 失败: `None`（personal syllabus 不存在、profile 不存在等）

**内部逻辑：**

1. 读 profile：`get_persisted_learning_profile(user_id, syllabus_id)`
   - 若不存在 → return None
2. 取 `by_knowledge_point`：挑出 score > 0 的项
   - 若为空 → return None（无需同步）
3. 读 syllabus JSON：`get_syllabus_detail_info(syllabus_id)` → 取 `period` 列表
4. 读 personal syllabus：`read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)`
   - 若不存在 → return None
5. 构建 candidates：每个周取 `content` 和 `enhanced_content`（取 `topic：desc` 的 topic 部分，已有 `_period_title` 逻辑可用）
6. 调用 `perception._llm_align_knowledge(knowledge, week_candidates)` 做语义对齐
   - 这里 knowledge 是 `by_knowledge_point`，candidates 是各周的 content 文本
   - LLM 返回 `{"matches": {"分布式文件系统及主流技术HDFS": {"tag": "HDFS 基础"}}}`
7. 反查：每个 match 的 candidate 文本属于哪一周 → 建立 `week_index → best_kp_score` 映射
8. 遍历 personal syllabus 的 period：
   - 若该周有匹配的 knowledge_point 分数 → 按阈值设 `competance` + 设 `competance_progress` 为 3（中等进度）
   - 若无匹配 → 不修改（保持 none）
9. 写回 personal syllabus JSON
10. 返回同步结果摘要

### 4.2 修改 `build_learning_profile` (service.py L139)

在 agent 运行成功后、`_tool_save_or_update_profile(state)` 之后，加一行：

```python
if syllabus_id is not None and state.get('profile'):
    sync_knowledge_to_weeks(int(user_id), int(syllabus_id))
```

位于原有 `_tool_save_or_update_profile(state)` 调用之后。

---

## Phase 5: 测试用例

### 5.1 单元测试：sync_knowledge_to_weeks

**用例 1 — 基本同步：**
- 准备: user 有 profile with `by_knowledge_point: {"HDFS 基础": 0.86}`
- 准备: syllabus Week 5 content = "大数据存储与管理：分布式文件系统及主流技术HDFS"
- 调用 `sync_knowledge_to_weeks(uid, sid)`
- 验证: Week 5 的 `competance` 变为 `"master"`（0.86 > 0.7）
- 验证: Week 1（"大数据课程导论与基本概念"）的 `competance` 仍为 `"none"`

**用例 2 — 多周命中：**
- 准备: `by_knowledge_point: {"HDFS 基础": 0.86, "HBase 基础": 0.43}`
- 验证: Week 5 competance="master", Week 6 competance="normal"

**用例 3 — 无匹配时不改：**
- 准备: `by_knowledge_point: {"Spark": 0.9}`（syllabus 里没有 Spark 相关内容）
- 验证: 所有周 competance 保持 none
- 验证: 返回值 `synced_weeks=0`

### 5.2 回归验证：Seed 后画像区分度

**用例 4 — medium seed 画像不全是 6%：**
- 运行 medium seed
- 查询该用户的 `week_items`
- 验证: 至少有一周 `competance != "none"`，`overall_score > 0.15`
