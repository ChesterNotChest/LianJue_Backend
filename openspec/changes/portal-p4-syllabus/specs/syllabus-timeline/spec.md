## ADDED Requirements

### Requirement: Vertical timeline line connects all week nodes
A vertical line (stroke=#e2e8f0, width=2) SHALL run from the first week to the last week, with week circles placed on the line (SVG line 43).

### Requirement: Mastered weeks have green circle with checkmark
Mastered weeks SHALL display a green circle (r=12, fill=#22c55e, border=3px white) with a white checkmark icon, a white card (740×58 rx=8) with a 4px green left bar, title (13px/700/#0f172a), description (11px/#64748b), and "已掌握" label (10px/#22c55e, right-aligned) (SVG lines 44-50).

### Requirement: Current week has larger indigo circle with inner dot
The current week SHALL display a larger indigo circle (r=16, fill=#6366f1, border=3px white) with an inner white dot (r=6, opacity=0.6), a white card with indigo border (1.5px) and 4px indigo left bar, and "进行中" label (10px/#6366f1) (SVG lines 52-54).

### Requirement: Pending weeks have gray hollow circle and muted card
Pending weeks SHALL display a hollow circle (r=12, fill=#fff, stroke=#cbd5e1, width=2), a card with fill=#fafafa and muted text (#94a3b8/#cbd5e1), and "待开始" label (10px/#94a3b8) (SVG lines 56-58).

### Requirement: Future weeks beyond 3 after current are collapsed into dots
Weeks beyond `currentIdx + 3` SHALL be collapsed into 3 small gray dots (r=5, fill=#e2e8f0) with "..." text, except the last week which is always shown (SVG lines 64-68).
