## ADDED Requirements

### Requirement: All five resource types have a white card background with colored stroke border
Each DocThumbnail SHALL render a white `<rect rx=10>` with a type-specific stroke color (lines 7, 26, 44, 59, 79 in `ref-doc-thumbnails.svg`):
- documents: `stroke="#bfdbfe"`
- mindmap: `stroke="#a7f3d0"`
- quiz: `stroke="#fde68a"`
- coding_practice: `stroke="#c4b5fd"`
- ppt: `stroke="#fecaca"`

#### Scenario: Document thumbnail has blue border
- **WHEN** DocThumbnail renders with type="documents"
- **THEN** the outer card has `fill="#fff"` and `stroke="#bfdbfe"`

### Requirement: Every type has a 3px top color bar matching the accent color
Each DocThumbnail SHALL render a `<rect height=3 rx=1.5>` at the top of the card with the type's accent color (lines 8, 27, 45, 60, 80):
- documents: `fill="#2563eb"`
- mindmap: `fill="#059669"`
- quiz: `fill="#d97706"`
- coding_practice: `fill="#7c3aed"`
- ppt: `fill="#dc2626"`

#### Scenario: Quiz thumbnail has amber top bar
- **WHEN** DocThumbnail renders with type="quiz"
- **THEN** a 3px tall rect with `fill="#d97706"` spans the full card width

### Requirement: Every type has a bottom label badge with type name
Each DocThumbnail SHALL render a label badge at the bottom (lines 20-21, 38-39, 53-54, 73-74, 92-93): `<rect width=56 height=16 rx=5>` with `fill={accent} opacity=0.1` centered horizontally, containing a `<text>` element at 9px font-weight 600 with the Chinese type name.

#### Scenario: Mindmap thumbnail has "思维导图" label
- **WHEN** DocThumbnail renders with type="mindmap"
- **THEN** the bottom badge contains the text "思维导图" at `fontSize=9 fontWeight=600 fill="#059669"`

### Requirement: Document template renders folded-corner document icon
The documents template SHALL render (lines 9-18):
- An inner document area `<rect>` at x=16 y=16, 118×100, rx=4, fill=`#eff6ff`, stroke=`#bfdbfe`
- A fold-corner `<polygon>` at points="134,16 134,36 114,36" fill=`#bfdbfe`
- Two fold-edge `<line>` elements at stroke=`#93c5fd` stroke-width=0.5
- Six text-line `<rect>` elements at y=32,42,52,62,72,82 with widths 60,80,50,70,40,65, rx=2, fill=`#93c5fd` (first) or `#bfdbfe` (rest)
- A separator `<line>` at y=128 stroke=`#eff6ff`

#### Scenario: Document thumbnail shows six text lines
- **WHEN** DocThumbnail renders with type="documents"
- **THEN** there are exactly six text-line `<rect>` elements inside the document area

### Requirement: Mindmap template renders node-link tree icon
The mindmap template SHALL render (lines 28-37):
- A center circle: `cx=75 cy=60 r=22 fill=#ecfdf5 stroke=#059669 strokeWidth=2`
- An inner dot: `cx=75 cy=60 r=7 fill=#059669 opacity=0.5`
- An upward branch: `<line>` (75,38)→(75,18) opacity=0.4 + `<circle>` cx=75 cy=14 r=10 opacity=0.6
- A left-down branch: `<line>` (75,82)→(38,106) opacity=0.35 + `<circle>` cx=34 cy=110 r=8 opacity=0.5 + a sub-branch `<line>` (34,110)→(14,130) opacity=0.2 + `<circle>` cx=12 cy=132 r=6 opacity=0.35
- A right-down branch: `<line>` (75,82)→(112,106) opacity=0.35 + `<circle>` cx=116 cy=110 r=8 opacity=0.5

#### Scenario: Mindmap thumbnail has 3 primary branches
- **WHEN** DocThumbnail renders with type="mindmap"
- **THEN** there are exactly three primary `<line>` elements branching from the center circle

### Requirement: Quiz template renders question-mark watermark and three option boxes
The quiz template SHALL render (lines 46-52):
- A "?" `<text>` element: `x=75 y=46 fontSize=24 fontWeight=800 fill=#d97706 opacity=0.15`
- Three option `<rect>` elements, each 114×22 rx=6:
  - A: `x=18 y=58 fill=#f8fafc stroke=#e2e8f0`
  - B: `x=18 y=84 fill=#fffbeb stroke=#d97706` (highlighted)
  - C: `x=18 y=110 fill=#f8fafc stroke=#e2e8f0`
- Each option contains a `<text>` element at font-size 9

#### Scenario: Quiz thumbnail has highlighted correct option
- **WHEN** DocThumbnail renders with type="quiz"
- **THEN** the middle option (B) has `fill="#fffbeb"` and `stroke="#d97706"` distinct from the gray options

### Requirement: Coding practice template renders code editor with syntax-colored text
The coding practice template SHALL render (lines 61-72):
- An editor background: `<rect>` at x=14 y=16, 122×90, rx=6, fill=`#1e293b`
- A tab bar: `<rect>` at x=14 y=16, 122×14, rx=6, fill=`#334155` + a second `<rect>` at y=22 to flatten bottom
- Three window control dots: `<circle>` at cx=24/34/44 cy=23 r=3 fill=red/amber/green opacity=0.6
- Six code `<text>` elements using fontSize=8 font-family=monospace:
  - `def` fill=`#a78bfa` at (26,44)
  - `solve` fill=`#38bdf8` at (42,56)
  - `(n: int):` fill=`#94a3b8` at (62,68)
  - `if` fill=`#c084fc` at (30,82)
  - `n <= 1:` fill=`#94a3b8` at (38,94)
  - `return` fill=`#c084fc` at (30,106)

#### Scenario: Coding thumbnail shows monospace code text
- **WHEN** DocThumbnail renders with type="coding_practice"
- **THEN** six `<text>` elements exist with `fontFamily="monospace"` and distinct fill colors

### Requirement: PPT template renders slide thumbnail with navigation dots
The PPT template SHALL render (lines 81-91):
- A slide area: `<rect>` at x=16 y=16, 118×72, rx=6, fill=`#fef2f2`
- A title bar: `<rect>` at x=28 y=26, 94×12, rx=3, fill=`#dc2626` opacity=0.15
- "Slide Title" `<text>` at x=75 y=36 fontSize=9 fontWeight=700 fill=`#dc2626`
- Two text-line `<rect>` elements at y=44 (width 40) and y=52 (width 55), fill=`#fca5a5`
- A mini chart `<rect>` at x=75 y=62, 50×20, rx=4, fill=`#dc2626` opacity=0.1 stroke=`#fca5a5`
- Three navigation dots `<circle>` at y=104: cx=52 r=4 opacity=0.5, cx=75 r=4 opacity=0.2, cx=98 r=4 opacity=0.2

#### Scenario: PPT thumbnail has three slide navigation dots
- **WHEN** DocThumbnail renders with type="ppt"
- **THEN** there are exactly three navigation dot `<circle>` elements near the bottom
