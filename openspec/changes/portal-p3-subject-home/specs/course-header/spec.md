## ADDED Requirements

### Requirement: Top bar is 56px high with white background
The course layout header SHALL be 56px high with white fill and bottom border stroke=#f1f5f9 (SVG line 7).

#### Scenario: Header renders at 56px height
- **WHEN** CourseLayout renders
- **THEN** the header has height 56px (h-14 in Tailwind) with bg-white and border-b border-[#f1f5f9]

### Requirement: Logo renders at 16px/800/indigo with letter spacing
The logo text "联觉 LianJue" SHALL render at 16px font-weight 800, fill #6366f1, letter-spacing 1 (SVG line 8).

### Requirement: Breadcrumb separator and course title match SVG
A "/" separator (13px/#cbd5e1) SHALL appear between the logo and the course title (13px/600/#0f172a) (SVG line 9).

### Requirement: Return link is in indigo
A "← 返回首页" link (11px/#6366f1) SHALL be positioned after the course title (SVG line 10).
