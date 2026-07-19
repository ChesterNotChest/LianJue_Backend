## ADDED Requirements

### Requirement: Activity panel is 280px wide with rounded white card
The activity panel SHALL render as a 280×460 white card (rx=12, fill=#fff, stroke=#f1f5f9) with title "学习活跃度" (14px/700/#0f172a) and subtitle "过去 7 天" (10px/#94a3b8) (SVG lines 73-75).

### Requirement: 7-day bar chart uses green bars with today highlighted in indigo
The bar chart SHALL display 7 vertical bars (26px wide each) representing the last 7 days of activity: today's bar in indigo (#6366f1, opacity=0.7), other active days in green (#22c55e, opacity 0.4-0.7 proportional to minutes), and inactive days in light gray (#f1f5f9) (SVG line 76).

#### Scenario: Monday has 42 minutes - bar is proportional
- **WHEN** a day has 42 minutes of activity
- **THEN** its bar height is ~42% of MAX_BAR_HEIGHT

### Requirement: Four stat rows show aggregated activity metrics
Four stat rows (each 248×42 rx=8 fill=#f8fafc) SHALL display: "7 天活跃天数" → count, "日均学习时长" → avg minutes, "30 天活跃天数" → count, "总学习时长" → total hours. Each row has label text (12px/#64748b) and value text (15px/800/#0f172a) right-aligned (SVG lines 77-80).

#### Scenario: 5 active days in 7 days shows "5 天"
- **WHEN** 5 of the past 7 days have activity > 0 minutes
- **THEN** the "7 天活跃天数" row value reads "5 天"
