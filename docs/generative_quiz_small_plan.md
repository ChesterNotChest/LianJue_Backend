# 题库资源小计划

## 1. 本轮目标

落地 `统一个性化资源生成 Agent` 的一种资源：`quiz`。

本轮只做后端静态资源链路，不做：

- 前端页面
- 真实模型 API 调用
- PDF 导出
- 个性化画像联动

## 2. 本轮范围

输入一个标准任务包，生成一份题库资源目录，目录中至少包含：

- `quiz.json`
- `quiz.md`

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
- 决定是否需要生成题库资源
- 组织标准任务包
- 调用资源生成 Agent
- 汇总生成结果

当前阶段：

- 仅在文档中定义边界
- 不在本轮代码中实现

### 资源生成 Agent

职责：

- 根据任务包生成题目内容
- 输出结构化题库 JSON

当前阶段：

- 通过 `agent_adapter.generate_quiz(payload)` 抽象
- 测试阶段使用 fake adapter

### Tool

职责：

- 创建目录
- 写入 `quiz.json`
- 渲染并写入 `quiz.md`
- 校验题库 schema
- 更新 `manifest.json`

## 4. 文件格式选择

本轮题库资源包含两类文件：

- `quiz.json`：结构化题库数据
- `quiz.md`：人读版 Markdown 题目文档

说明：

- `quiz.json` 是后续程序处理、校验、扩展的主数据源
- `quiz.md` 是当前阶段的直接展示与检查产物

## 5. 验证目标

本轮 pytest 至少验证：

- 工作空间与目录创建
- 题库 schema 轻量校验
- `quiz.json` 写入
- `quiz.md` 渲染写入
- manifest 追加
- 非法题结构状态收口为 `invalid`
