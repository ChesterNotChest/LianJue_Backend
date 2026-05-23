# PPT 资源收口级计划

## 0. （如果必要）新增的常量定义

本阶段建议保留或新增以下常量定义：

```python
BasePath.GENERATIVE_ROOT = "/generative"
GENERATIVE_PPT_SCHEMA_VERSION = "v1"
```

说明：

- 当前阶段不新增数据库表
- `manifest.json` 是实际运行中的用户级资源索引文件
- SQL 表结构由 `schema` 侧单独定义
- manifest 只保留后续迁移 SQL 所需的核心业务字段
- 当前阶段收口到“结构化课件内容 + Markdown 大纲 + 可直接打开的 `.pptx` 文件”
- `.pptx` 导出已经支持按 slide role 做差异化版式，而不是单一纯文本列表

## 1. 影响的文件范围

当前 PPT 资源收口涉及：

- `tasks/generative/contracts.py`
- `tasks/generative/storage.py`
- `tasks/generative/renderers.py`
- `tasks/generative/validation.py`
- `tasks/generative_task.py`
- `tests/test_generative_task.py`
- `docs/generative_ppt_small_plan.md`
- `docs/generative_ppt_contract.md`
- `generative/.gitkeep`

当前不涉及：

- 前端文件
- blueprint API
- SQLAlchemy schema
- 数据库迁移脚本
- 复杂模板/主题引擎

## 2. 函数级收口的完整数据流

### 2.1 Agent 关系收口

调用关系固定为：

1. 总调度 Agent 接收请求
2. 总调度 Agent 组装标准任务包
3. 总调度 Agent 调用 `统一个性化资源生成 Agent`
4. 资源生成 Agent 生成结构化 PPT 内容
5. Tool 创建目录、写文件、校验课件结构、派生 Markdown 大纲、更新 `manifest.json`
6. Tool 返回结构化结果

职责边界：

- 总调度 Agent：决定做什么，负责任务编排
- 资源生成 Agent：负责产出课件内容
- Tool：负责写、验、记索引

### 2.2 文件系统数据流

PPT 资源目录结构：

```text
generative/
  user_{user_id}/
    manifest.json
    ppt/
      {resource_id}/
        ppt.json
        ppt.md
        ppt.pptx
```

数据流：

1. 调用方传入标准 payload
2. `generate_resource(payload, agent_adapter)` 读取 `resource_type`
3. 分发到 `generate_ppt(payload, agent_adapter)`
4. `ensure_generative_workspace(user_id)` 创建：
   - `generative/user_{user_id}/`
   - `generative/user_{user_id}/ppt/`
   - `manifest.json`
5. 资源生成 Agent 输出：
   - `schema_version`
   - `title`
   - `topic`
   - `summary`
   - `theme`
   - `slide_style`
   - `slides`
6. Tool 生成 `resource_id`
7. Tool 创建资源目录：
   - `generative/user_{user_id}/ppt/{resource_id}/`
8. Tool 写入：
   - `ppt.json`
   - `ppt.md`
   - `ppt.pptx`
9. Tool 执行 PPT schema 轻量校验
10. Tool 用 `python-pptx` 将 `slides` 渲染为结构化课件
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
  "user_id": 19,
  "syllabus_id": 18,
  "resource_type": "ppt",
  "topic": "Spark Shuffle",
  "requirements": {
    "audience_level": "introductory",
    "slide_count_limit": 8,
    "theme": "academic-clean",
    "style": "teaching-outline"
  }
}
```

字段约束：

- `user_id`：必填，正整数
- `resource_type`：当前阶段必须为 `ppt`
- `topic`：必填，非空字符串
- `syllabus_id`：可选，正整数
- `requirements`：可选，字典

### 3.2 Agent 输出收口

`agent_adapter.generate_ppt(payload)` 必须返回 JSON 对象，推荐结构：

```json
{
  "schema_version": "v1",
  "title": "Spark Shuffle 教学课件",
  "topic": "Spark Shuffle",
  "summary": "用于课堂讲解的结构化课件大纲。",
  "theme": "academic-clean",
  "slide_style": "teaching-outline",
  "slides": [
    {
      "slide_index": 1,
      "title": "课程目标",
      "bullets": ["理解核心概念", "掌握关键步骤"],
      "speaker_notes": "先说明本节课要解决的问题。",
      "visual_hint": "简洁标题页 + 目标列表"
    },
    {
      "slide_index": 2,
      "title": "关键知识点",
      "bullets": ["概念定义", "应用场景", "注意事项"],
      "speaker_notes": "结合实例展开讲解。",
      "visual_hint": "左右分栏信息结构"
    }
  ]
}
```

约束：

- `schema_version` 当前必须为 `v1`
- `title` 缺失时允许回退到 `"{topic} PPT"`
- `summary` 必须非空
- `slides` 必须是非空列表
- 每页至少包含：
  - `title`
  - `bullets`
- `bullets` 必须为非空列表
- `speaker_notes` 和 `visual_hint` 可选

### 3.3 Tool 侧核心函数

#### `validate_ppt_payload(ppt: dict) -> dict`

输出：

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "method": "schema",
  "schema_version": "v1",
  "slide_count": 2
}
```

内部逻辑：

1. 校验 ppt 顶层必须为字典
2. 校验 `schema_version == "v1"`
3. 校验 `title`、`topic`、`summary` 非空
4. 校验 `slides` 为非空列表
5. 逐页校验：
   - `title`
   - `bullets`
6. 校验 `bullets` 中不允许空字符串项
7. `speaker_notes` 允许为空，但可记 warning
8. 返回 `valid/errors/warnings/slide_count`

#### `render_ppt_markdown(ppt: dict) -> str`

输出：

- 一个完整的 Markdown 文本

内部逻辑：

1. 渲染标题
2. 渲染 `topic`
3. 渲染 `theme`
4. 渲染 `slide_style`
5. 渲染摘要
6. 逐页渲染 slide 标题
7. 渲染 bullet 列表
8. 若存在 `visual_hint` 或 `speaker_notes`，则一并输出

#### `render_pptx_file(ppt: dict, output_path: Path) -> None`

输出：

- 一个真实 `.pptx` 文件

内部逻辑：

1. 使用 `python-pptx` 创建 Presentation
2. 为每个 slide 生成与内容匹配的结构化版式
3. 把 `speaker_notes` 写入 notes
4. 把 `visual_hint` 作为页脚辅助信息
5. 对常规内容自动做主点/子点整理，对 `术语:解释` 形式内容可转成两列表格，对流程页可转成步骤卡片
6. 保存到 `ppt.pptx`

#### `generate_ppt(payload: dict, agent_adapter: Any) -> dict`

输出：

```json
{
  "success": true,
  "resource_id": "ppt-20260516-xxxxxx",
  "resource_type": "ppt",
  "title": "Spark Shuffle 教学课件",
  "topic": "Spark Shuffle",
  "status": "ready",
  "resource_dir": "generative/user_19/ppt/...",
  "json_path": "generative/user_19/ppt/.../ppt.json",
  "md_path": "generative/user_19/ppt/.../ppt.md",
  "pptx_path": "generative/user_19/ppt/.../ppt.pptx",
  "validation": {
    "valid": true,
    "method": "schema",
    "schema_version": "v1",
    "slide_count": 2,
    "errors": [],
    "warnings": []
  }
}
```

内部逻辑：

1. 校验 payload
2. 调用 `agent_adapter.generate_ppt(payload)`
3. 生成 `resource_id`
4. 创建资源目录
5. 组织 `ppt.json`
6. 调用 `validate_ppt_payload(...)`
7. 调用 `render_ppt_markdown(...)`
8. 调用 `render_pptx_file(...)`
9. 写入：
   - `ppt.json`
   - `ppt.md`
   - `ppt.pptx`
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
  "user_id": 19,
  "resource_type": "ppt",
  "topic": "Spark Shuffle"
}
```

内部逻辑：

1. 校验 `resource_type`
2. 当前阶段若为 `ppt`，则分发到 `generate_ppt(...)`
3. 其余类型按已实现资源分别处理

### 3.4 manifest entry 收口

建议当前 `manifest.json` 顶层结构为：

```json
{
  "version": "v1",
  "user_id": 19,
  "resource_count": 1,
  "updated_at": 1740000001,
  "resources": [
    {
      "resource_id": "ppt-20260516-abc123",
      "resource_type": "ppt",
      "title": "Spark Shuffle 教学课件",
      "topic": "Spark Shuffle",
      "user_id": 19,
      "syllabus_id": 18,
      "status": "ready",
      "resource_dir": "generative/user_19/ppt/ppt-20260516-abc123",
      "main_files": {
        "json_path": "generative/user_19/ppt/.../ppt.json",
        "md_path": "generative/user_19/ppt/.../ppt.md",
        "pptx_path": "generative/user_19/ppt/.../ppt.pptx"
      },
      "validation": {
        "valid": true,
        "method": "schema",
        "schema_version": "v1",
        "slide_count": 2,
        "errors": [],
        "warnings": []
      },
      "metadata": {
        "slide_count": 2,
        "theme": "academic-clean",
        "slide_style": "teaching-outline"
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

## 4. 测试用例的构建描述

当前 pytest 不验证模型质量，只验证收口链路。

建议覆盖：

1. `generate_ppt()` 能写：
   - `ppt.json`
   - `ppt.md`
   - `ppt.pptx`
   - `manifest.json` 追加记录
2. `ppt.json` 中的 `schema_version`、`theme`、`slides` 正确
3. `ppt.md` 中包含：
   - 标题
   - Slide 标题
   - bullet 列表
   - `Speaker Notes`
   - `Visual Hint`
4. 非法 PPT 结构会被标记为 `invalid`
5. `slides` 为空时校验失败
6. slide 缺少 `title` 或 `bullets` 时校验失败
7. `generate_resource()` 能正确分发到 `ppt`
8. manifest 中 `metadata.slide_count` 和 `validation.slide_count` 正确
9. `.pptx` 能被 `python-pptx` 重新打开，并读到正确的页数

当前不验证：

- 真实 LLM 内容质量
- 图片素材生成
- 前端展示
- SQL 持久化行为
