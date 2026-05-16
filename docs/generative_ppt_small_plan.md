# PPT 资源小计划

## 1. 本轮目标

落地 `统一个性化资源生成 Agent` 的一种资源：`ppt`。

本轮只做后端静态资源链路，不做：

- 前端页面
- 真实模型 API 调用
- 真实 `.pptx` 二进制导出
- 图片素材自动生成
- 动画、转场、模板主题真实渲染
- 个性化画像联动

## 2. 本轮范围

输入一个标准任务包，生成一份 PPT 资源目录，目录中至少包含：

- `ppt.json`
- `ppt.md`

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
- 决定是否需要生成 PPT 资源
- 组织标准任务包
- 调用资源生成 Agent
- 汇总生成结果

当前阶段：

- 仅在文档中定义边界
- 不在本轮代码中实现

### 资源生成 Agent

职责：

- 根据任务包生成结构化 PPT 内容
- 输出结构化资源 JSON

当前阶段：

- 通过 `agent_adapter.generate_ppt(payload)` 抽象
- 测试阶段使用 fake adapter

### Tool

职责：

- 创建目录
- 写入 `ppt.json`
- 渲染并写入 `ppt.md`
- 校验资源 schema
- 更新 `manifest.json`

## 4. 文件格式选择

本轮 PPT 资源包含两类文件：

- `ppt.json`：结构化幻灯片数据
- `ppt.md`：人读版 Markdown 幻灯片大纲

说明：

- `ppt.json` 是后续程序处理、校验、扩展的主数据源
- `ppt.md` 是当前阶段的直接展示与检查产物
- 第一版先严格收口到“可预览的结构化教学课件内容”，不直接生成 `.pptx`
- 后续如果要接真实导出器，应在当前 contract 之上新增“ppt 运行/导出工具”，而不是推翻当前数据结构

## 5. 验证目标

本轮 pytest 至少验证：

- 工作空间与目录创建
- PPT 资源 schema 轻量校验
- `ppt.json` 写入
- `ppt.md` 渲染写入
- manifest 追加
- 非法 PPT 结构状态收口为 `invalid`
