## Why

`04-agent.svg`（222 行）是智能体页面的权威视觉规范。当前 AgentLayout + AgentChatPanel 已在前轮 fixup 中对齐了顶栏（含 SSE 指示器）和三栏布局，但以下区域仍需对照 SVG 修正：

1. **Stats Bar**（SVG lines 31-39）— 820×44 rx=10 统计条：综合掌握度 68%、7天活跃、薄弱点、当前步骤
2. **Inline Recommendation Card**（SVG lines 62-93）— 聊天流中的推荐路径卡片：紫色头部 + Mini D3 路径图 + 3 条候选路径 + 操作按钮 + 说明文本
3. **Right Panel - Learning Plan**（SVG lines 104-111）— 296×210 学习计划：纵向时间线，green/indigo/gray 步骤圆
4. **Right Panel - Profile**（SVG lines 115-131）— 296×172 学习画像：雷达图 + 3 条能力 bar + 薄弱点
5. **Right Panel - Knowledge Base**（SVG lines 134-137）— 296×42 知识库搜索（可折叠）
6. **Buddy Float Window**（SVG lines 141-197）— 340×420 学伴对话窗：紫色头部 + 消息列表 + memory tag + 输入栏
7. **Auto-popup Bubble**（SVG lines 200-212）— 280×72 自动弹出气泡 + 指向 FAB 的三角

## What Changes

### 文件范围

| 文件 | 操作 |
|------|------|
| `src/layouts/AgentLayout.tsx` | Stats bar 新增 |
| `src/components/chat/AgentChatPanel.tsx` | Inline 推荐卡片验证 |
| `src/layouts/RightSidebar.tsx` | 重写为含 LearningPlan + Profile + KnowledgeBase |
| `src/components/buddy/BuddyFloatWindow.tsx` | 重写对齐 SVG head+message+memory+input |
| `src/components/buddy/BuddyPopupBubble.tsx` | 重写对齐 SVG 弹出气泡 |

## Impact

- **修改文件**: 5 个文件
- **SVG 对照**: `04-agent.svg` 222 行全量
