## ADDED Requirements

### Requirement: Section dividers indicate scroll direction with text and arrow
Section dividers SHALL render centered text (12px/#94a3b8), a horizontal line (stroke=#cbd5e1), and one or two downward arrow polygons (fill=#94a3b8) (SVG lines 197-198, 315-317).

#### Scenario: First divider shows single down arrow with "探索更多" text
- **WHEN** Dashboard renders the divider between light viewport sections
- **THEN** it displays "向下滚动探索更多" with a horizontal line and one downward-pointing arrow polygon

#### Scenario: Second divider shows double down arrows with "知识全景" text
- **WHEN** Dashboard renders the divider before the Galaxy section
- **THEN** it displays "向下滚动探索知识全景" with a horizontal line and two downward-pointing arrow polygons

### Requirement: Dividers are visually centered in the viewport
Each divider SHALL be horizontally centered (textAnchor=middle) and positioned at the end of its preceding section.

#### Scenario: Divider renders centered between sections
- **WHEN** any SectionDivider renders
- **THEN** the text and line elements are centered with text-anchor="middle"
