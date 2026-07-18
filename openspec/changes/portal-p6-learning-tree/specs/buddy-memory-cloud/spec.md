## ADDED Requirements

### Requirement: Memory cloud is full-width (880px)
The memory section SHALL be a full-width card (880×76 rx=12 fill=#fff stroke=#e2e8f0) (SVG line 221).

### Requirement: Tag pills use rx=6 rectangular shape with dual color
Each memory tag SHALL be a rectangular pill (rx=6, height=24px, auto-width) with purple fill (#ede9fe) for weak_pattern and green fill (#dcfce7) for strengths. Text SHALL be 10px with matching color (#7c3aed purple / #16a34a green) (SVG lines 226-231).

#### Scenario: Weak pattern tag renders in purple
- **WHEN** a memory tag has category "weak_pattern"
- **THEN** the pill has fill=#ede9fe and text color #7c3aed

#### Scenario: Strength tag renders in green
- **WHEN** a memory tag has category "strength"
- **THEN** the pill has fill=#dcfce7 and text color #16a34a

### Requirement: "+N 条更早" shown when more than 6 tags
When tags exceed 6, SHALL display "+N 条更早" text (10px/#94a3b8) after the visible tags (SVG line 232).
