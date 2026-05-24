# 代码实操案例资源小计划

## 1. 本轮目标

落地 `统一个性化资源生成 Agent` 的一种资源：`coding_practice`。

本轮只做后端静态资源链路，不做：

- 前端页面
- 真实模型 API 调用
- 多语言真实运行沙箱
- 大型项目实验报告教学
- 个性化画像联动

## 2. 本轮范围

输入一个标准任务包，生成一份代码实操案例资源目录，目录中至少包含：

- `practice.json`
- `practice.md`
- `code/main.py`

并同步更新用户级 `manifest.json`。

顶层允许直接演进为更完整的索引对象，例如：

- `version`
- `resource_count`
- `updated_at`
- `resources`

## 3. 角色边界

### 总调度 Agent

职责：

- 接收学生请求或系统事件
- 决定是否需要生成代码实操案例资源
- 组织标准任务包
- 调用资源生成 Agent
- 汇总生成结果

当前阶段：

- 仅在文档中定义边界
- 不在本轮代码中实现

### 资源生成 Agent

职责：

- 根据任务包生成结构化代码实操案例内容
- 输出结构化资源 JSON

当前阶段：

- 通过 `agent_adapter.generate_coding_practice(payload)` 抽象
- 测试阶段使用 fake adapter

### Tool

职责：

- 创建目录
- 写入 `practice.json`
- 写入代码文件
- 渲染并写入 `practice.md`
- 校验资源 schema
- 对 Python 代码做本地确定性语法校验
- 更新 `manifest.json`

## 4. 文件格式选择

本轮代码实操案例资源包含三类文件：

- `practice.json`：结构化代码实操案例数据
- `practice.md`：人读版 Markdown 实操文档
- `code/main.py`：主示例代码文件

说明：

- `practice.json` 是后续程序处理、校验、扩展的主数据源
- `practice.md` 是当前阶段的直接展示与检查产物
- `code/main.py` 是当前阶段“带注释可运行代码”的主落盘文件
- 第一版先严格收口到一般教学型单文件 Python 示例，避免多文件工程把范围做散

## 5. 验证目标

本轮 pytest 至少验证：

- 工作空间与目录创建
- 代码实操案例 schema 轻量校验
- `practice.json` 写入
- `practice.md` 渲染写入
- `code/main.py` 写入
- manifest 追加
- 合法 Python 代码通过语法校验
- 非法 Python 代码状态收口为 `invalid`
