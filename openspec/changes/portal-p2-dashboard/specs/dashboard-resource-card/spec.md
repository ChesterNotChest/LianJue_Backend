## ADDED Requirements

### Requirement: Resource card is a single rounded container with top color section and bottom text section
Each resource card SHALL be a single `296×160 rx=10` rounded rect (`fill=#fff stroke=#e2e8f0`) containing two internal regions: a 100px top section filled with the type-specific background color, and a 60px bottom section with white background containing title, type label, and timestamp (SVG lines 73-120).

#### Scenario: Mindmap card has green top section and mindmap SVG icon
- **WHEN** RecentResources renders a resource with type="mindmap"
- **THEN** the top 100px has fill=#ecfdf5 (with bottom half flat), a mindmap node-link icon (center circle r=14, 3 branches), and the bottom 60px has white background with title, type info, and timestamp

#### Scenario: Quiz card has amber top section and question mark watermark
- **WHEN** RecentResources renders a resource with type="quiz"
- **THEN** the top 100px has fill=#fffbeb, displays a "?" watermark at 28px/800 opacity=0.12, and two option boxes (96×16 rx=4) with one highlighted

### Requirement: Refresh button at section header matches SVG specification
The section header SHALL include a refresh button `60×24 rx=6 fill=#f1f5f9` containing a refresh icon and "刷新" text at 10px/#64748b (SVG line 71).

#### Scenario: Clicking refresh reloads resource list
- **WHEN** the user clicks the refresh button
- **THEN** the onRefresh callback is invoked, re-fetching resources from the API

### Requirement: Bottom text section shows title, type label, and relative time
The bottom 60px section SHALL display: title (12px/700/#0f172a), type label + topic (10px/#64748b), and relative time + match percentage (9px/#94a3b8), matching SVG lines 80-82, 91-93, 104-106, 117-119.

#### Scenario: Coding card bottom section shows title, type, time
- **WHEN** a coding_practice resource card renders
- **THEN** the bottom section shows the resource title, "编程练习 · Python", and "1周前" with match percentage if available

### Requirement: Each resource type has a distinct top section SVG icon
The top 100px color section SHALL contain an inline SVG icon matching the resource type: mindmap (center r=14 + branches), quiz ("?" watermark + options), ppt (slide preview 116×64 rx=6), coding (monospace code text), documents (folded-corner document).

#### Scenario: PPT card shows slide preview with title bar and mini chart
- **WHEN** a ppt resource card renders
- **THEN** the top section contains a 116×64 rx=6 slide area with title bar, text lines, and a mini chart (40×10 rx=3)
