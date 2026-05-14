# 题库资源收口级计划

## 0. （如果必要）新增的常量定义

本阶段建议保留或新增以下常量定义：

```python
BasePath.GENERATIVE_ROOT = "/generative"
GENERATIVE_QUIZ_SCHEMA_VERSION = "v1"
```

说明：

- 当前阶段不新增数据库表
- `manifest.json` 是实际运行中的用户级资源索引文件
- SQL 表结构由 `schema` 侧单独定义

## 1. 影响的文件范围

当前题库资源收口涉及：

- `constant.py`
- `tasks/generative_task.py`
- `tests/test_generative_task.py`
- `docs/generative_quiz_contract.md`
- `generative/.gitkeep`

当前不涉及：

- 前端文件
- blueprint API
- SQLAlchemy schema

## 2. 函数级收口的完整数据流

### 2.1 Agent 关系收口

调用关系固定为：

1. 总调度 Agent 接收请求
2. 总调度 Agent 组装标准任务包
3. 总调度 Agent 调用 `统一个性化资源生成 Agent`
4. 资源生成 Agent 生成结构化题库内容
5. Tool 创建目录、写文件、校验题库结构、派生 Markdown、更新 `manifest.json`
6. Tool 返回结构化结果

职责边界：

- 总调度 Agent：决定做什么，负责任务编排
- 资源生成 Agent：负责产出题目内容
- Tool：负责写、验、记索引

### 2.2 文件系统数据流

题库资源目录结构：

```text
generative/
  user_{user_id}/
    manifest.json
    quiz/
      {resource_id}/
        quiz.json
        quiz.md
```

数据流：

1. 调用方传入标准 payload
2. `generate_resource(payload, agent_adapter)` 读取 `resource_type`
3. 分发到 `generate_quiz(payload, agent_adapter)`
4. `ensure_generative_workspace(user_id)` 创建：
   - `generative/user_{user_id}/`
   - `generative/user_{user_id}/quiz/`
   - `manifest.json`
5. 资源生成 Agent 输出：
   - `schema_version`
   - `title`
   - `topic`
   - `questions`
6. Tool 生成 `resource_id`
7. Tool 创建资源目录：
   - `generative/user_{user_id}/quiz/{resource_id}/`
8. Tool 写入：
   - `quiz.json`
   - `quiz.md`
9. Tool 执行题库 schema 轻量校验
10. Tool 生成一条 manifest entry 并追加到 `manifest.json`
11. Tool 返回统一结构化结果

### 2.3 manifest.json 的收口定位

`manifest.json` 的定位明确为：

- 当前阶段的用户级资源索引
- 未来 SQL 迁移时的重要数据来源
- 调试和回放时的人类可读中间索引

推荐的未来 SQL 表原型：

```text
generative_resource
- id
- resource_id
- user_id
- syllabus_id
- resource_type
- title
- topic
- status
- resource_dir
- main_files_json
- validation_json
- metadata_json
- created_at
- updated_at
```

## 3. 精确到输入输出的函数级收口，以及重要函数内部逻辑的描述

### 3.1 标准输入 payload

```json
{
  "user_id": 6,
  "syllabus_id": 18,
  "resource_type": "quiz",
  "topic": "HBase RowKey",
  "difficulty": "medium",
  "question_distribution": {
    "single_choice": 1
  }
}
```

字段约束：

- `user_id`：必填，正整数
- `resource_type`：当前阶段必须为 `quiz`
- `topic`：必填，非空字符串
- `syllabus_id`：可选，正整数
- `difficulty`：可选，字符串
- `question_distribution`：可选，字典

### 3.2 Agent 输出收口

`agent_adapter.generate_quiz(payload)` 必须返回 JSON 对象，推荐结构：

```json
{
  "schema_version": "v1",
  "title": "HBase RowKey 单题练习",
  "topic": "HBase RowKey",
  "questions": [
    {
      "id": "q1",
      "type": "single_choice",
      "difficulty": "medium",
      "stem": "哪一项最符合 RowKey 设计原则？",
      "options": [
        "尽量递增",
        "避免热点并保证可区分",
        "越长越好",
        "全部使用时间戳原文"
      ],
      "answer": "B",
      "explanation": "RowKey 设计需要兼顾散列性和可区分性，避免热点。",
      "knowledge_points": ["RowKey设计"]
    }
  ]
}
```

约束：

- `schema_version` 当前必须为 `v1`
- `title` 缺失时允许回退到 `"{topic} 练习题"`
- `questions` 必须是非空列表
- 每题至少包含：
  - `type`
  - `stem`
  - `answer`
  - `explanation`
- `single_choice` 题必须带 `options`

### 3.3 Tool 侧核心函数

#### `validate_quiz_payload(quiz: dict) -> dict`

输出：

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "method": "schema",
  "schema_version": "v1",
  "question_count": 1
}
```

内部逻辑：

1. 校验 quiz 顶层必须为字典
2. 校验 `schema_version == "v1"`
3. 校验 `title` 非空
4. 校验 `questions` 为非空列表
5. 逐题校验：
   - `type`
   - `stem`
   - `answer`
   - `explanation`
6. 若 `type == "single_choice"`，则强制要求 `options`
7. 返回 `valid/errors/warnings/question_count`

#### `render_quiz_markdown(quiz: dict) -> str`

输出：

- 一个完整的 Markdown 文本

内部逻辑：

1. 渲染标题
2. 渲染 `topic`
3. 按题号输出题目
4. 选择题输出选项
5. 输出答案、解析、知识点

#### `generate_quiz(payload: dict, agent_adapter: Any) -> dict`

输出：

```json
{
  "success": true,
  "resource_id": "quiz-20260511-xxxxxx",
  "resource_type": "quiz",
  "title": "HBase RowKey 单题练习",
  "topic": "HBase RowKey",
  "status": "ready",
  "resource_dir": "generative/user_6/quiz/...",
  "json_path": "generative/user_6/quiz/.../quiz.json",
  "md_path": "generative/user_6/quiz/.../quiz.md",
  "validation": {
    "valid": true,
    "method": "schema",
    "schema_version": "v1",
    "question_count": 1,
    "errors": [],
    "warnings": []
  }
}
```

内部逻辑：

1. 校验 payload
2. 调用 `agent_adapter.generate_quiz(payload)`
3. 生成 `resource_id`
4. 创建资源目录
5. 组织 `quiz.json`
6. 调用 `validate_quiz_payload(...)`
7. 调用 `render_quiz_markdown(...)`
8. 写入：
   - `quiz.json`
   - `quiz.md`
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
  "user_id": 6,
  "resource_type": "quiz",
  "topic": "HBase RowKey"
}
```

内部逻辑：

1. 校验 `resource_type`
2. 当前阶段若为 `quiz`，则分发到 `generate_quiz(...)`
3. 其余类型按已实现资源分别处理

### 3.4 manifest entry 收口

建议当前 `manifest.json` 顶层结构为：

```json
{
  "version": "v1",
  "user_id": 6,
  "resource_count": 1,
  "updated_at": 1740000001,
  "resources": [
    {
      "resource_id": "quiz-20260511-abc123",
      "resource_type": "quiz",
      "title": "HBase RowKey 单题练习",
      "topic": "HBase RowKey",
      "user_id": 6,
      "syllabus_id": 18,
      "status": "ready",
      "resource_dir": "generative/user_6/quiz/quiz-20260511-abc123",
      "main_files": {
        "json_path": "generative/user_6/quiz/.../quiz.json",
        "md_path": "generative/user_6/quiz/.../quiz.md"
      },
      "validation": {
        "valid": true,
        "method": "schema",
        "schema_version": "v1",
        "question_count": 1,
        "errors": [],
        "warnings": []
      },
      "metadata": {
        "question_count": 1,
        "question_types": ["single_choice"]
      },
      "created_at": 1740000000,
      "updated_at": 1740000000
    }
  ]
}
```

字段设计原则：

- manifest 顶层是索引容器
- `resources[*]` 是实际资源记录
- 顶层提供版本、计数、更新时间，便于文件级维护
- 资源记录保留 SQL 写入所需的核心业务字段
- 不再依赖单独的 ``

## 4. 测试用例的构建描述

当前 pytest 不验证模型质量，只验证收口链路。

建议覆盖：

1. `generate_quiz()` 能写：
   - `quiz.json`
   - `quiz.md`
   - `manifest.json` 追加记录
2. `quiz.json` 中的 `schema_version` 正确
3. `quiz.md` 中包含：
   - 标题
   - 题干
   - 答案
   - 解析
4. 非法 quiz 结构会被标记为 `invalid`
5. `single_choice` 缺少 `options` 时校验失败
6. `generate_resource()` 能正确分发到 `quiz`
7. manifest 中 `metadata.question_types` 和 `validation.question_count` 正确

当前不验证：

- 真实 LLM 内容质量
- 真实 PDF 导出
- 前端展示
- SQL 持久化行为
