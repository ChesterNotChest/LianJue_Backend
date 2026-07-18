## Context

AgentLayout 是智能体页面的三栏布局（LeftSidebar + Chat + RightSidebar），内含 AgentChatPanel、BuddyFloatWindow、BuddyPopupBubble。`04-agent.svg` 定义了完整规范。

## 函数级收口

### StatsBar (NEW)
- **输入**: `{mastery, activeDays, weakCount, currentStep}`
- **输出**: `820×44 rx=10 fill=#fff` 含 4 列 + dividers
- **数据源**: learning_profile_detail API

### AgentChatPanel — Inline Recommendation Card
- **验证项**: 紫色头部 rect + Mini D3 inline (5 nodes with colors) + 3 candidate path buttons + "确认路径 A" button + "查看全屏图谱" button
- **对照**: SVG lines 62-93

### RightSidebar — LearningPlan
- `296×210 rx=10` 面板，纵向时间线，已完成绿圆 r=7，当前紫圆 r=10+内点，待开始灰圆 r=7
- **对照**: SVG lines 104-111

### RightSidebar — Profile
- `296×172 rx=10`，雷达图 + 实践能力/理论理解/解题速度 bar + 薄弱点 text + 学习风格
- **对照**: SVG lines 115-131

### BuddyFloatWindow
- `340×420 rx=14`，紫色头部 (rx=14 fill=#ede9fe) + 表情 + "学伴小觉" + 悬浮窗 badge + 最小化/关闭按钮
- 消息区: 主动提醒(amber) + 用户消息(indigo op=0.1) + 小觉回复(gray) + memory tag(purple border)
- 输入栏: `316×38 rx=10` + 发送按钮
- **对照**: SVG lines 141-197

### BuddyPopupBubble
- `280×72 rx=12 fill=#fff stroke=#6366f1 w=1.5`
- 表情小头像 + "小觉" + "现在 · 自动弹出" + 消息文本
- 指向 FAB 的三角 polygon
- 关闭按钮 ✕
- **对照**: SVG lines 200-212
