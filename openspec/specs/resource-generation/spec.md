# Resource Generation

AI 资源生成模块。根据学习上下文批量或单类型生成 5 种学习资源，并行编排，支持校验和持久化。

## Resource Types

| Type | 生成内容 | 主文件 | 渲染方式 |
|------|---------|--------|---------|
| `documents` | 结构化短文档 | `document.json`, `document.md` | markdown |
| `mindmap` | Mermaid 思维导图 | `mindmap.json`, `mindmap.mmd` | mermaid |
| `quiz` | 诊断型题库 | `quiz.json`, `quiz.md` | markdown |
| `coding_practice` | 最小可运行代码实操 | `practice.json`, `practice.md`, 代码文件 | markdown |
| `ppt` | 结构化课件 | `ppt.json`, `ppt.md`, `ppt.pptx` | markdown |

## API Endpoints

### POST /api/generative_generate
触发 AI 驱动的资源生成流水线。
- **Input**: `{user_id, syllabus_id?, step_id?, resource_types: [str], knowledge_items?: [str], difficulty?, learning_goal?}`
- **Output**: `{resources: [{resource_id, resource_type, title, status, ...}], resource_tasks, overall_status}`

### POST /api/generative_list
列出用户已生成资源的清单。
- **Input**: `{user_id, syllabus_id?, resource_type?, limit?}`
- **Output**: `{resources: [{resource_id, resource_type, title, topic, status, created_at, ...}]}`

### POST /api/generative_detail
获取生成资源的详情与渲染内容。
- **Input**: `{user_id, resource_id}`
- **Output**: `{resource_id, resource_type, title, topic, status, validation, metadata, main_files, content (markdown/mermaid)}`

### GET /api/resource/download
下载生成资源的主文件。
- **Query**: `?resource_id=X&key=md_path|pptx_path|...`
- **Output**: 文件流（Content-Disposition）

## Data Flow

```
Total Agent: process_resource_generation_request
  → 冻结 resource_types → 并行单类型生成
  → read_generation_request
  → read_generation_plan
  → retrieve_generation_materials (RAG)
  → write_generation_draft (提炼 learning_brief)
  → generate_resource_payload (compact planning bundle)
  → persist_generated_resource (校验 + 落盘)
```

## State Machines

### 单类型任务
```
pending → running → succeeded | failed
```

### 多资源聚合
```
all succeeded  → overall_status = succeeded
partial        → overall_status = partial_success
all failed     → overall_status = failed
```

### 单资源持久化
```
status = "ready"  // 文件 + metadata 已落盘
```

## Data Model

```
generated_resource                  generated_resource_file
├── resource_id (PK)                ├── id (PK)
├── user_id                         ├── resource_id (FK)
├── syllabus_id                     ├── file_role
├── step_id                         ├── path_or_url
├── resource_type                   ├── mime_type
├── title                           └── created_at
├── topic
├── status ("ready")
├── resource_dir
├── validation_json
├── metadata_json
├── main_files_json
├── created_at
└── updated_at
```

## Validation

每种资源类型有独立的校验入口：
- documents: `validate_document_payload`
- mindmap: `validate_mermaid_text`
- quiz: `validate_quiz_payload`
- coding_practice: `validate_coding_practice_payload`
- ppt: `validate_ppt_payload`

## Known Issues

- `coding_practice` 不提供真实沙箱执行
- 旧 `syllabus_material_*` 端点已废弃（410），旧 `material` 表已清退

## Integration

- 被 Total Agent 的 `process_resource_generation_request` 触发
- 资源生成成功后可通知 Study Buddy (`resource_ready` 事件)
- 资源模块不推进 learning plan（由 Total Agent 负责）
- `tool_status_events` 透出每个 Resource Agent 事件
- 持久化：DB 表（生产）+ 文件目录 `/generative/user_{user_id}/`
