## ADDED Requirements

### Requirement: Course banner background is pure color without gradient overlay
The banner background SHALL be rendered as specified in `ref-course-thumbnails.svg` lines 13-14: a pure colored `<rect>` whose fill is determined by `PALETTE[hash%8]` (line 65), with a second `<rect>` at `y=height/2` with same fill to create a flat bottom. No `<defs>` gradient overlay, no text-shadow.

#### Scenario: Published course banner renders pure color background
- **WHEN** a published course thumbnail renders
- **THEN** the background is a single `<rect rx=12>` filled with the palette color
- **AND** a second `<rect>` at 50% height with the same fill covers the bottom half to flatten the bottom corners
- **AND** no `<linearGradient>` overlay `<rect>` exists in the SVG output

### Requirement: Decorative circles exist on all course banners
The banner SHALL include decorative circles as specified in `ref-course-thumbnails.svg`:
- Published (line 15): two circles — `cx=220 cy=40 r=70 fill=rgba(255,255,255,0.06)` and `cx=60 cy=90 r=100 fill=rgba(255,255,255,0.04)`
- Draft (line 53): one circle — `cx=200 cy=40 r=70 fill=rgba(255,255,255,0.05)`

#### Scenario: Published banner has two decorative circles
- **WHEN** a published course thumbnail renders
- **THEN** two `<circle>` elements are present in the SVG

#### Scenario: Draft banner has one decorative circle
- **WHEN** a draft course thumbnail renders
- **THEN** exactly one `<circle>` element is present in the SVG

### Requirement: Geometric patterns match SVG coordinate specifications
The banner SHALL render one of four geometric patterns selected by `(hash>>4) % 4` (line 66):
1. **diagonal** (line 16): two `<line>` elements — `(50,15)→(160,80)` stroke=`rgba(255,255,255,0.08)` width=2, and `(100,15)→(200,80)` stroke=`rgba(255,255,255,0.05)` width=2
2. **stacked** (line 36): three `<rect>` elements wrapped in `<g opacity=0.1 stroke=#fff stroke-width=3>` — `x=60 y=70 40×40 rx=4`, `x=120 y=55 40×40 rx=4`, `x=90 y=30 30×40 rx=4`, all `fill=none`
3. **ripple** (algorithm-derived, line 66 lists "波纹"): four concentric `<ellipse>` elements centered at `cx=180 cy=68` with `rx=40,72,104,140`, `ry=rx*0.42`, stroke=`rgba(255,255,255,0.12)`, opacity 0.6→0.24
4. **triangles** (algorithm-derived, line 66 lists "三角重叠"): four `<polygon>` elements with fill=`rgba(255,255,255,0.06)`, stroke=`rgba(255,255,255,0.14)`

#### Scenario: Diagonal geometry renders two lines at SVG-specified coordinates
- **WHEN** the selected geometry is "diagonal"
- **THEN** exactly two `<line>` elements are rendered with the specified endpoints and opacities

#### Scenario: Stacked geometry renders three rectangles at SVG-specified positions
- **WHEN** the selected geometry is "stacked"
- **THEN** exactly three `<rect>` elements are rendered at the specified coordinates within a group with `opacity=0.1`

### Requirement: Title and subtitle typography match SVG specification
Title SHALL be 22px font-weight 800 white with letter-spacing 2 for published cards (line 17), 20px font-weight 800 white for draft cards (line 54). Subtitle SHALL be 10px with `rgba(255,255,255,0.5)` for published (line 18), 10px with `rgba(255,255,255,0.4)` for draft showing "草稿 · 尚未发布" (line 55). No `textShadow` style attribute.

#### Scenario: Published title renders at 22px/800 white
- **WHEN** a published course thumbnail renders
- **THEN** the title text element has `fontSize="22"`, `fontWeight="800"`, `fill="white"`, `letterSpacing="2"`

#### Scenario: Draft subtitle shows fixed text
- **WHEN** a draft course thumbnail renders
- **THEN** the subtitle text reads "草稿 · 尚未发布" at `fontSize="10"` with `fill="rgba(255,255,255,0.4)"`

### Requirement: djb2 hash deterministically maps title to palette color and geometry
The function `djb2(title: string): number` SHALL produce a deterministic 32-bit unsigned integer from the title string. `PALETTE[hash % 8]` selects the background color from the 8-color array (line 65). `(hash >> 4) % 4` selects the geometry from the 4-element array (line 66). The same title string SHALL always produce the same color and geometry.

#### Scenario: Same title always produces same banner
- **WHEN** CourseThumbnail renders with title="大数据概论" twice
- **THEN** both renders produce the same background color and same geometry pattern
