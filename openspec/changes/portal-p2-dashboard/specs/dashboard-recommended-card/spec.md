## ADDED Requirements

### Requirement: Recommended exploration cards have type-colored top section with preview graphic
Each recommended card SHALL be a `296×160 rx=10` card with a 100px top section showing a document or mindmap preview graphic and a match percentage badge, plus a 60px bottom section with title and description (SVG lines 126-152).

#### Scenario: Document recommendation shows folded-corner document preview
- **WHEN** a document-type recommendation renders
- **THEN** the top section has fill=#eff6ff, contains a 256×72 rx=6 white document area with 4 text-line rects and a fold-corner polygon, plus a match badge (20×20 rx=6) in the top-right corner

#### Scenario: Mindmap recommendation shows node-link diagram
- **WHEN** a mindmap-type recommendation renders
- **THEN** the top section has fill=#ecfdf5, contains a center circle r=18 with inner dot r=5 and 3 branch lines with endpoint circles, plus a match badge

### Requirement: Match percentage badge uses type-appropriate color
The match badge (20×20 rx=6) SHALL use blue (#3b82f6) for document results and green (#059669) for mindmap results, with opacity=0.15 background and 9px/700 text.

#### Scenario: 92% match document shows blue badge
- **WHEN** a document recommendation has match_score 92
- **THEN** the badge has fill=#3b82f6 opacity=0.15 and text "92%" in #3b82f6

### Requirement: Bottom section shows title and source description
The bottom 60px SHALL display title (12px/700/#0f172a) and a description line (10px/#64748b) showing the recommendation source/reason (SVG lines 137-138, 150-151).

#### Scenario: Recommendation card shows "基于薄弱点" reason
- **WHEN** a recommendation has a reason field
- **THEN** the description line includes the recommendation reason text
