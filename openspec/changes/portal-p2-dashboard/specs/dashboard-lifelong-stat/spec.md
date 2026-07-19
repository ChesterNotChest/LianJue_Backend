## ADDED Requirements

### Requirement: Stats header bar aggregates all course mastery data
The stats header SHALL be a `1248×40 rx=8 fill=#f8fafc` bar showing: 课程数, 总节点, 已掌握 (green), 学习中 (indigo), 薄弱 (red), with vertical line dividers between each metric (SVG lines 210-219).

#### Scenario: Two courses with 33 total nodes show aggregated stats
- **WHEN** courseStats has 2 courses with combined nodes=33, mastered=12, learning=5, weak=16
- **THEN** the header displays "课程数 2 | 总节点 33 | 已掌握 12 学习中 5 薄弱 16"

### Requirement: Course stat card has 4px colored top bar
Each course stat card (472×108 rx=12) SHALL have a 4px rx=2 top bar in a deterministic color from COURSE_CARD_COLORS[index % colors.length] (SVG lines 268, 286).

#### Scenario: First course gets purple top bar
- **WHEN** the first course stat card renders
- **THEN** the top bar is fill=#6366f1

### Requirement: Course stat card shows mastery breakdown row
Each card SHALL display "已掌握 {n} 学习中 {n} 薄弱 {n} {percent}%" in a single row with 10px text (SVG lines 272-275).

#### Scenario: Card shows 12 mastered, 5 learning, 4 weak, 68%
- **WHEN** a course has mastered=12, learning=5, weak=4
- **THEN** the row displays "已掌握 12 学习中 5 薄弱 4 68%" with 68% in green

### Requirement: Progress bar fills proportionally to mastery percentage
Each card SHALL contain a 440×6 rx=3 progress bar: background #f1f5f9, fill in the card's accent color, width proportional to progress_percent (SVG lines 278, 296).

#### Scenario: 34% progress fills 149px of 440px bar
- **WHEN** progress_percent is 34
- **THEN** the fill rect has width = 440 * 0.34 ≈ 150px, fill=#f59e0b (amber)

### Requirement: Weak point note shows top weak node titles
Each card SHALL display "薄弱: {title1} · {title2}" at 10px/#94a3b8, positioned near the bottom of the card (SVG lines 280, 298).

#### Scenario: Card shows specific weak node names
- **WHEN** a course has weak_titles=["RowKey 热点", "预分区策略"]
- **THEN** the note reads "薄弱: RowKey 热点 · 预分区策略"

### Requirement: Empty placeholder card shown when fewer than 3 courses
When courseStats.length < 3, an empty placeholder card (472×108, dashed border, #f8fafc fill) SHALL be shown with centered motivational text and a "浏览可用学科" button (SVG lines 303-310).

#### Scenario: Only 2 courses - one placeholder card shown
- **WHEN** courseStats has 2 entries
- **THEN** a third card with dashed border and "新的学科等着你探索" is displayed

### Requirement: Action button navigates to subject home
Each card SHALL have an "进入学习" button (80×22 rx=6 fill=#f1f5f9) positioned at x=370 y=78 (right side of card), with 9px/#6366f1 text (SVG line 281).

#### Scenario: Clicking "进入学习" navigates to course home
- **WHEN** the user clicks "进入学习" on a course card
- **THEN** navigation to `/learn/{syllabus_id}/home` is triggered
