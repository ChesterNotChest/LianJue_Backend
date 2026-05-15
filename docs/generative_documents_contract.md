# 文档资源收口级计划

## 0. （如果必要）新增的常量定义

本阶段建议保留或新增以下常量定义：

```python
BasePath.GENERATIVE_ROOT = "/generative"
GENERATIVE_DOCUMENT_SCHEMA_VERSION = "v1"
```

说明：

- 当前阶段不新增数据库表
- `manifest.json` 是实际运行中的用户级资源索引文件
- SQL 表结构由 `schema` 侧单独定义
- manifest 只保留后续迁移 SQL 所需的核心业务字段

## 1. 影响的文件范围

当前文档资源收口涉及：

- `constant.py`
- `tasks/generative_task.py`
- `tests/test_generative_task.py`
- `docs/generative_documents_small_plan.md`
- `docs/generative_documents_contract.md`
- `tests/TEST_GENERATIVE_DOCUMENTS.md`
- `generative/.gitkeep`

当前不涉及：

- 前端文件
- blueprint API
- SQLAlchemy schema
- 数据库迁移脚本

## 2. 函数级收口的完整数据流

### 2.1 Agent 关系收口

调用关系固定为：

1. 总调度 Agent 接收请求
2. 总调度 Agent 组装标准任务包
3. 总调度 Agent 调用 `统一个性化资源生成 Agent`
4. 资源生成 Agent 生成结构化文档内容
5. Tool 创建目录、写文件、校验文档结构、派生 Markdown、更新 `manifest.json`
6. Tool 返回结构化结果

职责边界：

- 总调度 Agent：决定做什么，负责任务编排
- 资源生成 Agent：负责产出文档内容
- Tool：负责写、验、记索引

### 2.2 文件系统数据流

文档资源目录结构：

```text
generative/
  user_{user_id}/
    manifest.json
    documents/
      {resource_id}/
        document.json
        document.md
```

数据流：

1. 调用方传入标准 payload
2. `generate_resource(payload, agent_adapter)` 读取 `resource_type`
3. 分发到 `generate_structured_document(payload, agent_adapter)`
4. `ensure_generative_workspace(user_id)` 创建：
   - `generative/user_{user_id}/`
   - `generative/user_{user_id}/documents/`
   - `manifest.json`
5. 资源生成 Agent 输出：
   - `schema_version`
   - `title`
   - `topic`
   - `summary`
   - `sections`
   - `extension_reading`
6. Tool 生成 `resource_id`
7. Tool 创建资源目录：
   - `generative/user_{user_id}/documents/{resource_id}/`
8. Tool 写入：
   - `document.json`
   - `document.md`
9. Tool 执行文档 schema 轻量校验
10. Tool 生成一条 manifest entry 并追加到 `manifest.json`
11. Tool 返回统一结构化结果

### 2.3 manifest.json 的收口定位

`manifest.json` 的定位明确为：

- 当前阶段的用户级资源索引
- 未来 SQL 迁移时的重要数据来源
- 调试和回放时的人类可读中间索引

## 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

### 3.1 标准输入 payload

```json
{
  "user_id": 11,
  "syllabus_id": 18,
  "resource_type": "documents",
  "topic": "HBase RowKey",
  "requirements": {
    "include_extension_reading": true
  }
}
```

字段约束：

- `user_id`：必填，正整数
- `resource_type`：当前阶段必须为 `documents`
- `topic`：必填，非空字符串
- `syllabus_id`：可选，正整数
- `requirements`：可选，字典

### 3.2 Agent 输出收口

`agent_adapter.generate_document(payload)` 必须返回 JSON 对象，推荐结构：

```json
{
  "schema_version": "v1",
  "title": "HBase RowKey 讲解文档",
  "topic": "HBase RowKey",
  "summary": "面向课程学习的知识点说明。",
  "sections": [
    {"heading": "概念", "body": "RowKey 是..."},
    {"heading": "设计原则", "body": "应避免热点并保持可区分性。"}
  ],
  "extension_reading": [
    {"title": "HBase Schema Design", "reason": "扩展理解 RowKey 与表设计关系"}
  ]
}
```

约束：

- `schema_version` 当前必须为 `v1`
- `title` 缺失时允许回退到 `"{topic} 讲解文档"`
- `summary` 必须非空
- `sections` 必须是非空列表
- 每个 section 至少包含：
  - `heading`
  - `body`
- `extension_reading` 可选，为列表时每项推荐包含：
  - `title`
  - `reason`

### 3.3 Tool 侧核心函数

#### `validate_document_payload(document: dict) -> dict`

输出：

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "method": "schema",
  "schema_version": "v1",
  "section_count": 2
}
```

内部逻辑：

1. 校验 document 顶层必须为字典
2. 校验 `schema_version == "v1"`
3. 校验 `title` 非空
4. 校验 `summary` 非空
5. 校验 `sections` 为非空列表
6. 逐节校验：
   - `heading`
   - `body`
7. `extension_reading` 若存在则校验其类型，缺失字段仅记 warning
8. 返回 `valid/errors/warnings/section_count`

#### `render_document_markdown(document: dict) -> str`

输出：

- 一个完整的 Markdown 文本

内部逻辑：

1. 渲染标题
2. 渲染 `topic`
3. 渲染摘要
4. 逐节渲染正文
5. 若存在 `extension_reading`，则输出扩展阅读小节

#### `generate_structured_document(payload: dict, agent_adapter: Any) -> dict`

输出：

```json
{
  "success": true,
  "resource_id": "documents-20260511-xxxxxx",
  "resource_type": "documents",
  "title": "HBase RowKey 讲解文档",
  "topic": "HBase RowKey",
  "status": "ready",
  "resource_dir": "generative/user_11/documents/...",
  "json_path": "generative/user_11/documents/.../document.json",
  "md_path": "generative/user_11/documents/.../document.md",
  "validation": {
    "valid": true,
    "method": "schema",
    "schema_version": "v1",
    "section_count": 2,
    "errors": [],
    "warnings": []
  }
}
```

内部逻辑：

1. 校验 payload
2. 调用 `agent_adapter.generate_document(payload)`
3. 生成 `resource_id`
4. 创建资源目录
5. 组织 `document.json`
6. 调用 `validate_document_payload(...)`
7. 调用 `render_document_markdown(...)`
8. 写入：
   - `document.json`
   - `document.md`
9. 根据校验结果计算 `status`
   - 通过：`ready`
   - 不通过：`invalid`
10. 生成 manifest entry
11. 追加到 `manifest.json`
12. 返回统一结果

#### `generate_resource(payload: dict, agent_adapter: Any) -> dict`

输入：

```json
{
  "user_id": 11,
  "resource_type": "documents",
  "topic": "HBase RowKey"
}
```

内部逻辑：

1. 校验 `resource_type`
2. 当前阶段若为 `documents`，则分发到 `generate_structured_document(...)`
3. 其余类型按已实现资源分别处理

### 3.4 manifest entry 收口

建议当前 `manifest.json` 顶层结构为：

```json
{
  "version": "v1",
  "user_id": 11,
  "resource_count": 1,
  "updated_at": 1740000001,
  "resources": [
    {
      "resource_id": "documents-20260511-abc123",
      "resource_type": "documents",
      "title": "HBase RowKey 讲解文档",
      "topic": "HBase RowKey",
      "user_id": 11,
      "syllabus_id": 18,
      "status": "ready",
      "resource_dir": "generative/user_11/documents/documents-20260511-abc123",
      "main_files": {
        "json_path": "generative/user_11/documents/.../document.json",
        "md_path": "generative/user_11/documents/.../document.md"
      },
      "validation": {
        "valid": true,
        "method": "schema",
        "schema_version": "v1",
        "section_count": 2,
        "errors": [],
        "warnings": []
      },
      "metadata": {
        "section_count": 2,
        "extension_reading_count": 1
      },
      "created_at": 1740000000,
      "updated_at": 1740000000
    }
  ]
}
```

## 4. 测试用例的构建描述

当前 pytest 不验证模型质量，只验证收口链路。

建议覆盖：

1. `generate_structured_document()` 能写：
   - `document.json`
   - `document.md`
   - `manifest.json` 追加记录
2. `document.json` 中的 `schema_version` 正确
3. `document.md` 中包含：
   - 标题
   - 摘要
   - 节标题
   - 扩展阅读
4. 非法 document 结构会被标记为 `invalid`
5. `sections` 为空或缺少 `heading/body` 时校验失败
6. `generate_resource()` 能正确分发到 `documents`
7. manifest 中 `metadata.section_count` 和 `validation.section_count` 正确

当前不验证：

- 真实 LLM 内容质量
- 真实 PDF 导出
- 前端展示
- SQL 持久化行为
