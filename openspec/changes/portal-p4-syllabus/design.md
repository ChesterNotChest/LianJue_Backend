## Context

SyllabusPage 渲染在 CourseLayout 内（左侧 232px 侧栏 + 顶栏由 portal-p3 覆盖）。页面由 StatsBar + SyllabusTimeline + ActivityPanel 三部分组成。

SyllabusTimeline 已在前轮 fixup 中对齐 SVG，ActivityGantt 需要重写为 SVG 精确的 ActivityPanel。

## Goals / Non-Goals

**Goals:**
- 重写 ActivityGantt → ActivityPanel，逐元素对齐 SVG lines 73-81
- 验证 SyllabusTimeline 与 SVG lines 43-69 对齐
- 验证 StatsBar 与 SVG lines 35-41 对齐

**Non-Goals:**
- 不修改 CourseLayout（portal-p3 覆盖）

## 影响文件范围

| 文件 | 操作 |
|------|------|
| `src/components/charts/ActivityGantt.tsx` | 重写为 ActivityPanel |
| `src/pages/SyllabusPage.tsx` | 导入路径更新 |

## 函数-API 级完整数据流

```
CourseLayout → <Outlet /> → SyllabusPage
  │
  ├── POST /api/learning_profile_detail {user_id, syllabus_id}
  │     → {profile: {learning_records, resource_usage}}
  │     → setProfile()
  │
  ├── POST /api/syllabus_detail {syllabus_id}
  │     → {syllabus: {weeks: [{week_index, competance, content, ...}]}}
  │     → setSyllabus()
  │
  └── Render:
        ├── StatsBar ({completed, total, current, progress%})
        ├── SyllabusTimeline ({weeks})
        └── ActivityPanel ({profile})
```

## 函数级收口与内部逻辑

### ActivityPanel.tsx (NEW — 替代 ActivityGantt)

#### `ActivityPanel({ profile }: { profile: LearningProfile | null }): JSX.Element`
- **输入**: LearningProfile（含 learning_records, resource_usage）
- **输出**: `280×460` 面板
- **内部逻辑**:
  1. 若 profile 为 null: 显示空状态
  2. 从 learning_records + resource_usage 按星期几分天聚合分钟数 → 7 天 minutes 数组
  3. 计算: `activeDays7d = count(days with minutes > 0)`
  4. 计算: `avgDailyMin = total7d / max(activeDays7d, 1)`
  5. 计算: `activeDays30d` (从 profile 提取，若无则显示 "-")
  6. 计算: `totalHours` (从 profile 提取，若无则显示 "-")
  7. 柱状图: 7 个 rect，高度比例 = (minutes / maxMinutes)，min 6px max 50px
     - 今天: indigo (#6366f1) op=0.7
     - 其他活跃天: green (#22c55e) op 0.4-0.7 (按比例)
     - 无数据天: gray (#f1f5f9)
  8. 4 行统计: 每行 `248×42 rx=8 fill=#f8fafc`
     - Row 1: "7 天活跃天数" 12px/#64748b → "{n} 天" 15px/800/#0f172a
     - Row 2: "日均学习时长" → "{n} 分钟" 
     - Row 3: "30 天活跃天数" → "{n} 天"
     - Row 4: "总学习时长" → "{n} 小时"

#### 柱状图 Bar 规格
```ts
const MAX_BAR_HEIGHT = 50;  // SVG: bar y=6, h=50
const MIN_BAR_HEIGHT = 6;   // SVG: bar y=50, h=6
const BAR_WIDTH = 26;       // SVG: each bar 26px wide
const BAR_GAP = 5;          // SVG: 31-26=5 gap
```

#### 渲染层序
1. 面板底板: `rect 280×460 rx=12 fill=#fff stroke=#f1f5f9`
2. 标题: "学习活跃度" 14px/700/#0f172a
3. 副标题: "过去 7 天" 10px/#94a3b8
4. 7 天柱状图: 7 bars + 星期标签
5. 4 行统计卡片

**对照**: SVG lines 73-81

### SyllabusTimeline — 验证

- 纵向线: stroke=#e2e8f0 w=2 (SVG line 43)
- 绿色已完成圆 r=12 + 白色对勾 (SVG lines 44, 48)
- 蓝色当前圆 r=16 + 内点 r=6 (SVG line 52)
- 灰色待开始圆 r=12 (SVG lines 56, 60, 66)
- 折叠点: 3 个小圆 r=5 fill=#e2e8f0 (SVG line 64)
- 周卡片: rx=8 + 左侧 4px 色条 + title 13px/700 + desc 11px + 状态标签
- **验证项**: 圆大小、颜色、卡片样式、折叠逻辑

### SyllabusPage StatsBar — 验证

- `840×48 rx=10 fill=#fff stroke=#f1f5f9`
- 3 列等分 + 垂直分隔线
- 完成: 绿色数字 + "/N 周"
- 当前: 蓝色 "第 N 周"
- 进度: green gradient bar + "{n}%"

## Decisions

### Decision 1: 7 天柱状图从 learning_records 实时计算
- **选择**: 不从后端获取预聚合数据，从 raw records 按星期几分天聚合
- **理由**: learning_records 已包含 started_at 和 duration，足够按天分组

### Decision 2: 柱状图高度按比例映射
- **选择**: `height = max(MIN_BAR_HEIGHT, (minutes / maxMinutes) * MAX_BAR_HEIGHT)`
- **理由**: SVG 定义柱状图高度范围 6px-50px，按比例保持视觉比例
