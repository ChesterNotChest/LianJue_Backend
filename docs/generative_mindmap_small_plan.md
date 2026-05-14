# 思维导图小计划

## 1. 本轮目标

落地 `统一个性化资源生成 Agent` 的一种资源：`mindmap`。

本轮只做后端静态资源链路，不做：

- 前端页面
- 真实模型 API 调用
- PNG / SVG 实际渲染导出
- 个性化画像联动

## 2. 本轮范围

输入一个标准任务包，生成一份思维导图资源目录，目录中至少包含：

- `mindmap.json`
- `mindmap.mmd`

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
- 决定是否需要生成思维导图
- 组织标准任务包
- 调用资源生成 Agent
- 汇总生成结果

当前阶段：

- 仅在文档中定义边界
- 不在本轮代码中实现

### 资源生成 Agent

职责：

- 根据任务包生成思维导图内容
- 输出结构化导图数据和 Mermaid 文本

当前阶段：

- 通过 `agent_adapter.generate_mindmap(payload)` 抽象
- 测试阶段使用 fake adapter

### Tool

职责：

- 创建目录
- 写入文件
- 校验 Mermaid
- 更新 `manifest.json`

## 4. 文件格式选择

本轮主导图源文件使用 `.mmd`，不是 `.md`。

- `mindmap.json`：结构化节点数据
- `mindmap.mmd`：Mermaid 源文件

## 5. 验证目标

本轮 pytest 至少验证：

- 工作空间与目录创建
- Mermaid 轻量语法校验
- 资源文件写入
- manifest 追加
- 非法 Mermaid 状态收口为 `invalid`
