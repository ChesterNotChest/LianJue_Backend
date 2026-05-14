# 思维导图测试说明

## 1. 测试目标

验证思维导图资源链路在不依赖真实 LLM 的情况下，可以稳定完成：

- 工作空间创建
- Mermaid 校验
- 资源文件落盘
- manifest 记录
- 错误状态收口

## 2. 测试方式

测试使用 fake agent adapter，不调用真实 API。

fake agent 只负责模拟返回：

- 合法的 `title/root/nodes/mermaid`
- 非法的 `mermaid`

## 3. 当前覆盖点

当前 `tests/test_generative_task.py` 已覆盖：

- `ensure_generative_workspace()` 创建 `generative/user_{user_id}`、资源目录和 `manifest.json`
- `manifest.json` 顶层版本、计数、更新时间字段
- `validate_mermaid_text()` 处理合法 Mermaid 和 fenced code block
- `generate_mindmap()` 生成：
  - `mindmap.json`
  - `mindmap.mmd`
  - `manifest.json` 记录
- 旧 manifest 读取时的字段补齐
- 非法 Mermaid 会被标记为 `invalid`
- 缺少 `topic` 时抛出受控异常

## 4. 这些测试证明什么

这些测试证明的是：

- 输入输出收口稳定
- Agent 与 Tool 边界稳定
- 文件系统结构稳定
- 后续接真实模型时，不需要重写落盘和校验逻辑

## 5. 当前不验证什么

当前测试不验证：

- 真实 Mermaid 渲染成功率
- 真实 LLM 内容质量
- 前端展示效果
- 总调度 Agent 与资源生成 Agent 的完整协作链
