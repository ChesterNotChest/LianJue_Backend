## Why

`03-syllabus.svg`（91 行）是教学大纲页面的权威视觉规范。当前 SyllabusPage + SyllabusTimeline 已在前轮 fixup 中基本对齐，但 ActivityGantt（右侧活跃度面板）与 SVG lines 73-81 存在结构性偏差。

### 主要偏差

1. **ActivityGantt** — SVG 定义 280×460 rx=12 面板内含：7 天柱状图（7 个 rect，不同高度和 opacity）、4 行统计数据（每行 248×42 rx=8 fill=#f8fafc）。当前实现使用简单的 div + 百分比柱状图，与 SVG 的精确布局不一致。
2. **SyllabusTimeline** — 已在前轮对齐，需逐元素验证。

## What Changes

### 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/charts/ActivityGantt.tsx` | 重写 | 逐元素对齐 SVG lines 73-81 |
| `src/components/charts/SyllabusTimeline.tsx` | 验证 | 确认 SVG lines 43-69 对齐 |
| `src/pages/SyllabusPage.tsx` | 验证 | 确认数据流和布局对齐 |

### SVG 元素逐行对照

#### Stats Bar（SVG lines 35-41）— 已对齐

| SVG 行 | 元素 | 属性 | 状态 |
|--------|------|------|------|
| 35 | 容器 | `840×48 rx=10 fill=#fff stroke=#f1f5f9` | ✅ |
| 36 | 完成 | "完成" 9px/#94a3b8 + "{n}/{total} 周" 16px/800/#22c55e | ✅ |
| 37 | 分隔线 | `line` stroke=#f1f5f9 | ✅ |
| 38 | 当前 | "当前" 9px/#94a3b8 + "第 {n} 周" 16px/800/#6366f1 | ✅ |
| 39 | 分隔线 | `line` stroke=#f1f5f9 | ✅ |
| 40 | 进度条 | "整体进度" 9px + 进度条 200×8 rx=4 green gradient + "{n}%" | ✅ |

#### Timeline（SVG lines 43-69）— 需验证

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 43 | 纵向线 | `line x1=40 x2=40 stroke=#e2e8f0 w=2` |
| 44-46 | 已掌握周 | circle r=12 fill=#22c55e + card 740×58 rx=8 + left bar 4px green + title 13px/700 + desc 11px + "已掌握" 10px green |
| 52-54 | 当前周 | circle r=16 fill=#6366f1 + inner dot r=6 op=0.6 + card bold border + "进行中" 10px/#6366f1 |
| 56-58 | 待开始周 | circle r=12 fill=#fff stroke=#cbd5e1 + card fill=#fafafa + gray text + "待开始" |
| 64 | 折叠点 | 3 circles r=5 fill=#e2e8f0 for weeks 6-17 |
| 66-68 | 最后一周 | circle r=12 + card with "第 18 周 · 课程总结与项目答辩" |

#### Activity Panel（SVG lines 73-81）— **需重写**

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 73 | 面板 | `280×460 rx=12 fill=#fff stroke=#f1f5f9 filter=url(#ss)` |
| 74 | 标题 | `x=16 y=26 fontSize=14 fontWeight=700 fill=#0f172a` "学习活跃度" |
| 75 | 副标题 | `x=16 y=50 fontSize=10 fill=#94a3b8` "过去 7 天" |
| 76 | 7 天柱状图 | 7 个 rect: 26×16/38/20/50/30/12/6, fill=#22c55e op=0.4-0.7, 1 indigo bar |
| 77-80 | 4 行统计 | 每行 `248×42 rx=8 fill=#f8fafc`:
| | | Row 1: "7 天活跃天数" → "5 天"
| | | Row 2: "日均学习时长" → "42 分钟"
| | | Row 3: "30 天活跃天数" → "18 天"
| | | Row 4: "总学习时长" → "21 小时"

## Capabilities

### Modified Capabilities
- `activity-panel`: 学习活跃度面板 — SVG 精确 280px 面板，7 天柱状图 + 4 行统计（7天活跃/日均时长/30天活跃/总时长）。数据源: learning_profile_detail API。

## Impact

- **修改文件**: 1 个文件（ActivityGantt.tsx）
- **验证文件**: 2 个文件（SyllabusTimeline.tsx, SyllabusPage.tsx）
- **SVG 对照**: `03-syllabus.svg` 91 行全量
- **零新增 API 端点**
