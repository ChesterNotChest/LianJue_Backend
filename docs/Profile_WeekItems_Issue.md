# Profile WeekItems 全 6% 问题

## 症状

前端 SyllabusTimeline 显示所有学生（low / medium / high）16 周进度条全部 6%。

```
API 返回: week_items[0..15] = {competance: "none", score: 0, competance_progress: 0}
前端: Math.max(6, score * 100) = Math.max(6, 0) = 6%
```

## 根因链

### 1. personal syllabus 未初始化

`demo_db_env` fixture 创建的 `UserSyllabus` 不带 `personal_syllabus_path`。

`build_learning_profile` 中 `_tool_ensure_personal_syllabus` 函数已定义但**未被调用**——缺一行接线。

**影响：** `personal_syllabus_path = null`，profile JSON 中 `syllabus_scope[0].personal_syllabus_path` 始终为空。

### 2. profile_scope 捕获时机错误

`_tool_ensure_personal_syllabus` 接上线后，它在 `profile_scope` 构建之后才执行。`profile_scope` 循环读取 `UserSyllabus.personal_syllabus_path` 时仍是 null，即使随后 ensure 更新了 DB，`state['profile_scope']` 已是旧值。

**影响：** 即使 personal syllabus 存在于磁盘，profile JSON 中仍显示 null。

### 3. sync_knowledge_to_weeks LLM 对齐返回空

`_merge_weeks_into_profile` 调用 `sync_knowledge_to_weeks` 将 `by_knowledge_point` 映射到 syllabus 周。

LLM prompt 中 tag 格式为 `- HDFS 基础: 0.43`（带分数后缀），LLM 照抄 `"HDFS 基础: 0.43"` 作为 tag 值。代码检查 `"HDFS 基础: 0.43" in knowledge` → False → 匹配被丢弃。

**影响：** LLM 对齐始终返回 0 匹配。

### 4. sync_knowledge_to_weeks 无规则 fallback

LLM 返回空时，函数直接返回 `no_alignment_matches`，没有关键词/子串匹配兜底。

`by_knowledge_point` 中 `"HDFS 基础"` 与 Week 5 content `"分布式文件系统及主流技术HDFS"` 有 `"HDFS"` 子串重合，但 LLM 路径失败后无人利用。

**影响：** 即使有明确的关键词线索，`competance` 也无法更新。

### 5. `_extract_week_content` 不含描述关键词

传给 LLM 的候选文本只取 topic 名（`"大数据存储与管理"`），不含描述部分（`"分布式文件系统及主流技术HDFS"`）。LLM 缺少语义线索。

**影响：** 即使 LLM 正常工作，匹配线索也不足。

## 修复

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `service.py` | `_tool_ensure_personal_syllabus` 移至 `profile_scope` 前 + 重读 `UserSyllabus` | 确保 personal syllabus 存在且路径被正确捕获 |
| 2 | `service.py` | `_merge_weeks_into_profile` 在 `_tool_save_or_update_profile` 前执行 | profile JSON 保存时含最新 week 数据 |
| 3 | `perception.py` | tag prompt 格式 `f"- {k}: {v:.2f}"` → `f"- {k}"` | LLM 返回的 tag 不再带分数后缀 |
| 4 | `personal_syllabus.py` | `sync_knowledge_to_weeks` 加规则 fallback | LLM 空匹配时用子串/英文 token 扫描 week content |
| 5 | `personal_syllabus.py` | `_extract_week_content` 含描述片段 | LLM 能看到 "HDFS"、"ETL" 等关键词 |
| 6 | `personal_syllabus.py` | `DEBUG_PROFILE_SYNC=1` 调试输出 | 排查用 |

## 数据流（修后）

```
seed 创建 UserSyllabus
  ↓
build_learning_profile:
  ├─ _tool_ensure_personal_syllabus → 拷贝 syllabus → personal syllabus JSON
  ├─ 重读 UserSyllabus → personal_syllabus_path 正确捕获
  ├─ profile_scope 构建 → 路径正确
  ├─ profile agent 运行 → by_knowledge_point 产出
  ├─ _merge_weeks_into_profile:
  │    └─ sync_knowledge_to_weeks:
  │         ├─ LLM 语义对齐 (perception.py)
  │         ├─ 规则 fallback (子串/关键词)
  │         └─ 设 competance → 写 personal syllabus
  │    └─ 重建 week_signals → 合并进 state['profile']
  └─ _tool_save_or_update_profile → profile JSON 落盘
  ↓
API /api/learning_profile_detail → 读 profile JSON
  ↓
前端 normalizeProfile → week_items[i].score > 0 → 进度条 > 6%
```

## 前端 6% 的来源

`SyllabusTimeline.tsx:39-40`:
```ts
const effectivePct = Math.max(6, Math.round((w.competance_progress || 0) * 100));
```

`competance_progress` 映射到后端 `week_items[].score`（0-1 值）。后端 `score=0` 时 → `0*100=0` → `Math.max(6, 0) = 6%`。这是硬编码的最小值，用于非零微指示。
