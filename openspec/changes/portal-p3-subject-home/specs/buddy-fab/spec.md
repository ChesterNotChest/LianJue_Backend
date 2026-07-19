## ADDED Requirements

### Requirement: FAB has white shadow outer circle and indigo inner circle
The FAB SHALL render a white outer circle (r=30 fill=#fff with shadow filter) and an indigo inner circle (r=28 fill=#6366f1) (SVG line 134).

### Requirement: FAB shows face expression with two eyes and smile
The FAB inner circle SHALL contain a face: two white eyes (circles r=3.5 at cx=-6 and cx=6, cy=-3, opacity=0.9) and a smile arc (path "M-8,8 Q0,18 8,8" stroke=#fff strokeWidth=2 opacity=0.6 strokeLinecap=round) (SVG lines 135-136).

### Requirement: Notification badge is a red circle with count
When unreadCount > 0, a red badge circle (r=10 fill=#ef4444) SHALL appear at the top-right of the FAB (cx=20 cy=-20), containing the count as white text (9px/700 textAnchor=middle) (SVG line 137).

### Requirement: FAB has text label to the left
A text label SHALL appear to the left of the FAB: "学伴小觉" (11px/#6366f1) and "全天候陪伴" (10px/#94a3b8), right-aligned (textAnchor=end) (SVG line 139).
