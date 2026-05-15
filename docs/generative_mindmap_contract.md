# 思维导图收口级计划

## 0. （如果必要）新增的常量定义

本阶段建议保留或新增以下常量定义：

```python
BasePath.GENERATIVE_ROOT = "/generative"
```

可选常量：

```python
MINDMAP_ALLOWED_DIAGRAM_PREFIXES = ("mindmap", "flowchart", "graph")
```

说明：

- 当前阶段不新增数据库表
- `manifest.json` 是实际运行中的用户级资源索引文件
- SQL 表结构由 `schema` 侧单独定义
- manifest 只保留后续迁移 SQL 所需的核心业务字段

## 1. 影响的文件范围

当前思维导图资源收口涉及：

- `constant.py`
- `tasks/generative_task.py`
- `tests/test_generative_task.py`
- `docs/generative_mindmap_small_plan.md`
- `docs/generative_mindmap_contract.md`
- `tests/TEST_GENERATIVE_MINDMAP.md`
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
4. 资源生成 Agent 生成思维导图内容
5. Tool 创建目录、写文件、校验 Mermaid、更新 `manifest.json`
6. Tool 返回结构化结果

职责边界：

- 总调度 Agent：决定做什么，负责任务编排
- 资源生成 Agent：负责产出导图内容
- Tool：负责写、验、记索引

### 2.2 文件系统数据流

思维导图资源目录结构：

```text
generative/
  user_{user_id}/
    manifest.json
    mindmap/
      {resource_id}/
        mindmap.json
        mindmap.mmd
```

数据流：

1. 调用方传入标准 payload
2. `generate_resource(payload, agent_adapter)` 读取 `resource_type`
3. 分发到 `generate_mindmap(payload, agent_adapter)`
4. `ensure_generative_workspace(user_id)` 创建：
   - `generative/user_{user_id}/`
   - `generative/user_{user_id}/mindmap/`
   - `manifest.json`
5. 资源生成 Agent 输出：
   - `title`
   - `root`
   - `nodes`
   - `mermaid`
6. Tool 生成 `resource_id`
7. Tool 创建资源目录：
   - `generative/user_{user_id}/mindmap/{resource_id}/`
8. Tool 写入：
   - `mindmap.json`
   - `mindmap.mmd`
9. Tool 执行 Mermaid 轻量校验
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
  "user_id": 3,
  "syllabus_id": 12,
  "resource_type": "mindmap",
  "topic": "分布式存储",
  "knowledge_items": ["HDFS", "HBase"],
  "hierarchy": {}
}
```

字段约束：

- `user_id`：必填，正整数
- `resource_type`：当前阶段必须为 `mindmap`
- `topic`：必填，非空字符串
- `syllabus_id`：可选，正整数
- `knowledge_items`：可选，列表
- `hierarchy`：可选，字典

### 3.2 Agent 输出收口

`agent_adapter.generate_mindmap(payload)` 必须返回 JSON 对象，推荐结构：

```json
{
  "title": "分布式存储 思维导图",
  "root": "分布式存储",
  "nodes": [
    {
      "label": "HDFS",
      "children": [
        {"label": "NameNode"},
        {"label": "DataNode"}
      ]
    }
  ],
  "mermaid": "mindmap\n  root((分布式存储))\n    HDFS\n      NameNode\n      DataNode"
}
```

约束：

- `mermaid` 必须非空
- `title` 缺失时允许回退到 `topic`
- `nodes` 缺失时允许回退为空列表
- Mermaid 校验独立于 `nodes` 执行

### 3.3 Tool 侧核心函数

#### `get_generative_user_root(user_id: int) -> Path`

输入：

- `user_id`

输出：

- `Path("generative/user_{user_id}")`

内部逻辑：

1. 校验 `user_id > 0`
2. 拼接 backend 根目录和 `BasePath.GENERATIVE_ROOT`
3. 返回绝对路径

#### `ensure_generative_workspace(user_id: int) -> dict`

输出：

```json
{
  "user_root": "generative/user_3",
  "mindmap_dir": "generative/user_3/mindmap",
  "manifest_path": "generative/user_3/manifest.json"
}
```

内部逻辑：

1. 创建用户根目录
2. 创建 `documents/mindmap/quiz/coding_practice` 子目录
3. 若 `manifest.json` 不存在，则初始化：

```json
{
  "version": "v1",
  "user_id": 3,
  "resource_count": 0,
  "updated_at": 1740000000,
  "resources": []
}
```

#### `validate_mermaid_text(text: str) -> dict`

输出：

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "method": "syntax",
  "diagram_type": "mindmap",
  "node_count": 4,
  "cleaned_text": "mindmap\n  root((分布式存储))\n    HDFS"
}
```

内部逻辑：

1. 去除 fenced code block
2. 读取首行图类型
3. 校验首行必须是：
   - `mindmap`
   - `flowchart`
   - `graph`
4. 校验非空节点或边
5. 返回校验结果

#### `generate_mindmap(payload: dict, agent_adapter: Any) -> dict`

输出：

```json
{
  "success": true,
  "resource_id": "mindmap-20260510-xxxxxx",
  "resource_type": "mindmap",
  "title": "分布式存储 思维导图",
  "topic": "分布式存储",
  "status": "ready",
  "resource_dir": "generative/user_3/mindmap/...",
  "json_path": "generative/user_3/mindmap/.../mindmap.json",
  "mermaid_path": "generative/user_3/mindmap/.../mindmap.mmd",
  "validation": {
    "valid": true,
    "method": "syntax",
    "diagram_type": "mindmap",
    "node_count": 4,
    "errors": [],
    "warnings": []
  }
}
```

内部逻辑：

1. 校验 payload
2. 调用 `agent_adapter.generate_mindmap(payload)`
3. 生成 `resource_id`
4. 创建资源目录
5. 组织 `mindmap.json`
6. 清洗并写入 `mindmap.mmd`
7. 调用 `validate_mermaid_text(...)`
8. 根据校验结果计算 `status`
   - 通过：`ready`
   - 不通过：`invalid`
9. 生成 manifest entry
10. 追加到 `manifest.json`
11. 返回统一结果

#### `generate_resource(payload: dict, agent_adapter: Any) -> dict`

输入：

```json
{
  "user_id": 3,
  "resource_type": "mindmap",
  "topic": "分布式存储"
}
```

内部逻辑：

1. 校验 `resource_type`
2. 当前阶段若为 `mindmap`，则分发到 `generate_mindmap(...)`
3. 其余类型返回受控失败或未实现异常

### 3.4 manifest entry 收口

建议当前 `manifest.json` 顶层结构为：

```json
{
  "version": "v1",
  "user_id": 3,
  "resource_count": 1,
  "updated_at": 1740000001,
  "resources": [
    {
      "resource_id": "mindmap-20260510-abc123",
      "resource_type": "mindmap",
      "title": "分布式存储 思维导图",
      "topic": "分布式存储",
      "user_id": 3,
      "syllabus_id": 12,
      "status": "ready",
      "resource_dir": "generative/user_3/mindmap/mindmap-20260510-abc123",
      "main_files": {
        "json_path": "generative/user_3/mindmap/.../mindmap.json",
        "mermaid_path": "generative/user_3/mindmap/.../mindmap.mmd"
      },
      "validation": {
        "valid": true,
        "method": "syntax",
        "diagram_type": "mindmap",
        "node_count": 4,
        "errors": [],
        "warnings": []
      },
      "metadata": {
        "knowledge_item_count": 2
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

1. `ensure_generative_workspace()` 能创建：
   - `generative/user_{user_id}`
   - `generative/user_{user_id}/mindmap`
   - `manifest.json`
2. `validate_mermaid_text()` 能：
   - 通过合法 Mermaid
   - 清洗 fenced code block
   - 拒绝空图和非法首行
3. `generate_mindmap()` 能写：
   - `mindmap.json`
   - `mindmap.mmd`
   - `manifest.json` 追加记录
4. 非法 Mermaid 能被标记为 `invalid`
5. 缺少 `topic` 时返回受控异常
6. `generate_resource()` 能正确分发到 `mindmap`
7. 未实现资源类型返回受控失败

当前不验证：

- 真实 Mermaid 渲染结果
- 真实 LLM 质量
- 前端展示
- SQL 持久化行为
