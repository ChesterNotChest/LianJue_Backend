# 代码实操案例资源收口级计划

## 0. （如果必要）新增的常量定义

本阶段建议保留或新增以下常量定义：

```python
BasePath.GENERATIVE_ROOT = "/generative"
GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION = "v1"
```

说明：

- 当前阶段不新增数据库表
- `manifest.json` 是实际运行中的用户级资源索引文件
- SQL 表结构由 `schema` 侧单独定义
- manifest 只保留后续迁移 SQL 所需的核心业务字段
- 第一版严格收口到一般教学型代码案例，不做大型项目实验报告、课程大作业实验说明或多阶段工程实训文档
- 第一版建议先严格支持 `python`，用本地确定性语法校验支撑“可运行代码”的最低收口

## 1. 影响的文件范围

当前代码实操案例资源收口涉及：

- `tasks/generative/contracts.py`
- `tasks/generative/renderers.py`
- `tasks/generative/validation.py`
- `tasks/generative_task.py`
- `tests/test_generative_task.py`
- `docs/generative_coding_practice_small_plan.md`
- `docs/generative_coding_practice_contract.md`
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
4. 资源生成 Agent 生成结构化代码实操案例内容
5. Tool 创建目录、写文件、校验案例结构、校验 Python 代码语法、派生 Markdown、更新 `manifest.json`
6. Tool 返回结构化结果

职责边界：

- 总调度 Agent：决定做什么，负责任务编排
- 资源生成 Agent：负责产出代码案例内容
- Tool：负责写、验、记索引

### 2.2 文件系统数据流

代码实操案例资源目录结构：

```text
generative/
  user_{user_id}/
    manifest.json
    coding_practice/
      {resource_id}/
        practice.json
        practice.md
        code/
          main.py
```

数据流：

1. 调用方传入标准 payload
2. `generate_resource(payload, agent_adapter)` 读取 `resource_type`
3. 分发到 `generate_coding_practice(payload, agent_adapter)`
4. `ensure_generative_workspace(user_id)` 创建：
   - `generative/user_{user_id}/`
   - `generative/user_{user_id}/coding_practice/`
   - `manifest.json`
5. 资源生成 Agent 输出：
   - `schema_version`
   - `title`
   - `topic`
   - `language`
   - `summary`
   - `learning_objectives`
   - `steps`
   - `code_files`
   - `run_guide`
6. Tool 生成 `resource_id`
7. Tool 创建资源目录：
   - `generative/user_{user_id}/coding_practice/{resource_id}/`
8. Tool 写入：
   - `practice.json`
   - `practice.md`
   - `code/*`
9. Tool 执行资源 schema 轻量校验
10. 若 `language == "python"`，Tool 对 `.py` 文件执行本地确定性语法校验
11. Tool 生成一条 manifest entry 并追加到 `manifest.json`
12. Tool 返回统一结构化结果

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
  "user_id": 15,
  "syllabus_id": 18,
  "resource_type": "coding_practice",
  "topic": "Python 函数封装与参数传递",
  "language": "python",
  "practice_requirements": {
    "course_rule": "给出可直接运行的入门级单文件案例",
    "difficulty": "introductory",
    "need_comments": true,
    "need_step_by_step_guide": true
  }
}
```

字段约束：

- `user_id`：必填，正整数
- `resource_type`：当前阶段必须为 `coding_practice`
- `topic`：必填，非空字符串
- `language`：第一版建议必填，且先严格支持 `python`
- `syllabus_id`：可选，正整数
- `practice_requirements`：可选，字典

### 3.2 Agent 输出收口

`agent_adapter.generate_coding_practice(payload)` 必须返回 JSON 对象，推荐结构：

```json
{
  "schema_version": "v1",
  "title": "Python 函数封装实操案例",
  "topic": "Python 函数封装与参数传递",
  "language": "python",
  "summary": "通过一个可运行示例理解函数定义、参数传递和返回值。",
  "learning_objectives": [
    "理解函数定义",
    "理解位置参数与返回值"
  ],
  "steps": [
    {
      "step_index": 1,
      "title": "阅读案例目标",
      "instruction": "先理解程序要完成的功能和输入输出。"
    },
    {
      "step_index": 2,
      "title": "运行示例程序",
      "instruction": "执行 main.py，观察输出结果。"
    }
  ],
  "code_files": [
    {
      "path": "code/main.py",
      "purpose": "entry",
      "content": "def greet(name):\n    # 返回问候语\n    return f'Hello, {name}'\n\nprint(greet('Alice'))\n"
    }
  ],
  "run_guide": {
    "entry_file": "code/main.py",
    "command": "python code/main.py",
    "expected_output": "Hello, Alice"
  }
}
```

约束：

- `schema_version` 当前必须为 `v1`
- `title` 缺失时允许回退到 `"{topic} 实操案例"`
- `language` 第一版必须为 `python`
- `summary` 必须非空
- `steps` 必须是非空列表
- `code_files` 必须是非空列表
- 每个代码文件至少包含：
  - `path`
  - `content`
- `run_guide` 至少包含：
  - `entry_file`
  - `command`
- `code_files[*].path` 和 `run_guide.entry_file` 必须是相对路径，禁止绝对路径和 `..`

### 3.3 Tool 侧核心函数

#### `validate_coding_practice_payload(practice: dict) -> dict`

输出：

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "method": "schema+python_syntax",
  "schema_version": "v1",
  "language": "python",
  "step_count": 2,
  "file_count": 1
}
```

内部逻辑：

1. 校验 practice 顶层必须为字典
2. 校验 `schema_version == "v1"`
3. 校验 `title`、`topic`、`language`、`summary` 非空
4. 校验 `steps` 为非空列表
5. 逐步校验：
   - `title`
   - `instruction`
6. 校验 `code_files` 为非空列表
7. 逐文件校验：
   - `path`
   - `content`
8. 校验 `path` 为安全相对路径，不允许路径穿越
9. 校验 `run_guide.entry_file` 和 `run_guide.command` 非空
10. 若 `language == "python"`：
   - 至少要有一个 `.py` 文件
   - 用 `ast.parse(...)` 对 `.py` 文件做本地语法校验
11. 返回 `valid/errors/warnings/step_count/file_count`

#### `render_coding_practice_markdown(practice: dict) -> str`

输出：

- 一个完整的 Markdown 文本

内部逻辑：

1. 渲染标题
2. 渲染 `topic`
3. 渲染摘要
4. 渲染学习目标
5. 按顺序渲染实操步骤
6. 渲染运行方式和预期输出
7. 逐文件渲染代码块
8. 代码块根据 `language` 选择 fenced code block info string

#### `generate_coding_practice(payload: dict, agent_adapter: Any) -> dict`

输出：

```json
{
  "success": true,
  "resource_id": "coding_practice-20260516-xxxxxx",
  "resource_type": "coding_practice",
  "title": "Python 函数封装实操案例",
  "topic": "Python 函数封装与参数传递",
  "status": "ready",
  "resource_dir": "generative/user_15/coding_practice/...",
  "json_path": "generative/user_15/coding_practice/.../practice.json",
  "md_path": "generative/user_15/coding_practice/.../practice.md",
  "entry_file_path": "generative/user_15/coding_practice/.../code/main.py",
  "validation": {
    "valid": true,
    "method": "schema+python_syntax",
    "schema_version": "v1",
    "language": "python",
    "step_count": 2,
    "file_count": 1,
    "errors": [],
    "warnings": []
  }
}
```

内部逻辑：

1. 校验 payload
2. 调用 `agent_adapter.generate_coding_practice(payload)`
3. 生成 `resource_id`
4. 创建资源目录
5. 组织 `practice.json`
6. 写入 `code_files`
7. 调用 `validate_coding_practice_payload(...)`
8. 调用 `render_coding_practice_markdown(...)`
9. 写入：
   - `practice.json`
   - `practice.md`
   - `code/*`
10. 根据校验结果计算 `status`
   - 通过：`ready`
   - 不通过：`invalid`
11. 生成 manifest entry
12. 追加到 `manifest.json`
13. 返回统一结果

#### `generate_resource(payload: dict, agent_adapter: Any) -> dict`

输入：

```json
{
  "user_id": 15,
  "resource_type": "coding_practice",
  "topic": "Python 函数封装与参数传递",
  "language": "python"
}
```

内部逻辑：

1. 校验 `resource_type`
2. 当前阶段若为 `coding_practice`，则分发到 `generate_coding_practice(...)`
3. 其余类型按已实现资源分别处理

### 3.4 manifest entry 收口

建议当前 `manifest.json` 顶层结构为：

```json
{
  "version": "v1",
  "user_id": 15,
  "resource_count": 1,
  "updated_at": 1740000001,
  "resources": [
    {
      "resource_id": "coding_practice-20260516-abc123",
      "resource_type": "coding_practice",
      "title": "Python 函数封装实操案例",
      "topic": "Python 函数封装与参数传递",
      "user_id": 15,
      "syllabus_id": 18,
      "status": "ready",
      "resource_dir": "generative/user_15/coding_practice/coding_practice-20260516-abc123",
      "main_files": {
        "json_path": "generative/user_15/coding_practice/.../practice.json",
        "md_path": "generative/user_15/coding_practice/.../practice.md",
        "entry_file_path": "generative/user_15/coding_practice/.../code/main.py"
      },
      "validation": {
        "valid": true,
        "method": "schema+python_syntax",
        "schema_version": "v1",
        "language": "python",
        "step_count": 2,
        "file_count": 1,
        "errors": [],
        "warnings": []
      },
      "metadata": {
        "language": "python",
        "file_count": 1,
        "step_count": 2,
        "entry_file": "code/main.py"
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
- `main_files.entry_file_path` 和 `metadata.entry_file` 便于调用方快速定位主运行文件

## 4. 测试用例的构建描述

当前 pytest 不验证模型质量，只验证收口链路。

建议覆盖：

1. `generate_coding_practice()` 能写：
   - `practice.json`
   - `practice.md`
   - `code/main.py`
   - `manifest.json` 追加记录
2. `practice.json` 中的 `schema_version`、`language`、`run_guide` 正确
3. `practice.md` 中包含：
   - 标题
   - 学习目标
   - 实操步骤
   - 运行命令
   - 代码块
4. 合法 Python 代码通过语法校验并标记为 `ready`
5. 非法 Python 代码被标记为 `invalid`
6. `code_files` 为空时校验失败
7. `steps` 为空或缺少 `instruction` 时校验失败
8. `code_files.path` 包含绝对路径或 `..` 时校验失败
9. `generate_resource()` 能正确分发到 `coding_practice`
10. manifest 中 `metadata.language`、`metadata.file_count`、`validation.step_count` 正确

当前不验证：

- 真实 LLM 内容质量
- 真实代码运行结果
- 多文件大型工程
- 前端展示
- SQL 持久化行为
