## ADDED Requirements

### Requirement: Course card renders complete metadata section below banner
Each course card SHALL render, below the CourseThumbnail banner, the exact elements specified in `01-dashboard.svg` lines 36-42 (published) and lines 64-65 (draft).

#### Scenario: Published card shows week/semester, progress bar, mastery stats, action buttons
- **WHEN** a published course card renders with progress data available
- **THEN** the card displays: week/semester text (12px/700/#0f172a), status badge (48×20 rx=5), progress label + percentage, progress bar (352×6 rx=3), mastery stats line (10px/#94a3b8), "进入学习" button (96×26 rx=8 #6366f1), "管理" button (52×26 rx=8 #f1f5f9)

#### Scenario: Draft card shows only status text and disabled button
- **WHEN** a draft course card renders
- **THEN** the card displays "课程准备中" (12px/700/#94a3b8) and a disabled "等待中" button (96×26 rx=8, fill #f1f5f9, stroke #e2e8f0, text #94a3b8)

### Requirement: Progress bar reflects per-syllabus mastery data
The progress bar SHALL be computed from `SyllabusProgress.progress_percent` (mastered / total * 100). The bar consists of a background rect (352×6 rx=3 #f1f5f9) and a fill rect whose width is proportional to the percentage, with green (#22c55e) for ≥60%, amber (#f59e0b) for <60%.

#### Scenario: 68% progress shows green bar at 240px width
- **WHEN** progress_percent is 68
- **THEN** the fill rect has width = 352 * 0.68 ≈ 239px, fill #22c55e

### Requirement: Mastery stats line shows node counts and last active time
The stats line SHALL display "{mastered} 节点已掌握 · {weak} 薄弱 · {lastActiveText}" at 10px/#94a3b8, positioned at x=16 y=224 (or equivalent spacing below progress bar).

#### Scenario: Stats line shows 12 mastered, 4 weak, active 2 hours ago
- **WHEN** SyllabusProgress has mastered_nodes=12, weak_nodes=4, last_active_text="2小时前活跃"
- **THEN** the stats line reads "12 节点已掌握 · 4 薄弱 · 2小时前活跃"

### Requirement: Card background is white with border, draft uses dashed border
Published cards SHALL have `fill=#fff stroke=#e2e8f0`. Draft cards SHALL have `fill=#fafafa stroke=#e2e8f0 strokeDasharray=6,3` (SVG line 60).

#### Scenario: Draft card has dashed border and lighter background
- **WHEN** a draft course card renders
- **THEN** the card container has `fill=#fafafa stroke=#e2e8f0` with dashed stroke
