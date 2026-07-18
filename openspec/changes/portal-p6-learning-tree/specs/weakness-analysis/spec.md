## ADDED Requirements

### Requirement: Weakness analysis card uses red color theme
The weakness analysis card (304×172 rx=12) SHALL have a red header (fill=#fef2f2) with title "薄弱点分析" (11px/700/#ef4444) and subtitle showing weak cluster count (9px/#94a3b8) (SVG lines 117-121).

### Requirement: Red-highlighted weak items show mastery score
Top weak items SHALL render as red-bordered cards (284×36 rx=6 fill=#fef2f2 stroke=#fecaca) with a red circle indicator (r=5 fill=#ef4444 op=0.15), title (11px/600/#0f172a), description (9px/#64748b), and mastery score right-aligned (8px/#ef4444) (SVG lines 124-138).

### Requirement: Lower-priority weak items use white card with amber indicator
Items beyond the top 2 SHALL use a white card (284×32 rx=6 fill=#fff stroke=#f1f5f9) with an amber circle indicator (r=5 fill=#f59e0b op=0.15) (SVG lines 140-146).

### Requirement: Maximum 3 weak items displayed
The section SHALL display at most 3 weak items as shown in the SVG (lines 124-146).
