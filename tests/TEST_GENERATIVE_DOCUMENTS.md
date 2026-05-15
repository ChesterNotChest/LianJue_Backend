# 文档资源测试说明

## 1. 测试目标

验证文档资源链路在不依赖真实 LLM 的情况下，可以稳定完成：

- 文档 schema 校验
- `document.json` 写入
- `document.md` 渲染写入
- manifest 记录
- 错误状态收口

## 2. 测试方式

测试使用 fake agent adapter，不调用真实 API。

fake agent 只负责模拟返回：

- 合法的结构化文档 JSON
- 非法的结构化文档 JSON

## 3. 当前覆盖点

当前 `tests/test_generative_task.py` 已覆盖：

- `validate_document_payload()` 对合法文档通过校验
- `generate_structured_document()` 生成：
  - `document.json`
  - `document.md`
  - `manifest.json` 记录
- 非法 document 结构会被标记为 `invalid`
- `generate_resource()` 能正确分发到 `documents`

## 4. 这些测试证明什么

这些测试证明的是：

- 输入输出收口稳定
- Agent 与 Tool 边界稳定
- 文档结构校验逻辑稳定
- 文件系统结构稳定
- 后续接真实模型时，不需要重写落盘和校验逻辑

## 5. 当前不验证什么

当前测试不验证：

- 真实 LLM 内容质量
- 真实 PDF 导出结果
- 前端展示效果
- 总调度 Agent 与资源生成 Agent 的完整协作链
