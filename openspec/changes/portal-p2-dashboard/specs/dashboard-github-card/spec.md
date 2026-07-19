## ADDED Requirements

### Requirement: GitHub project cards have dark top section with code styling
Each GitHub card SHALL be a `296×160 rx=10` card with a 100px dark section (fill=#1e293b) containing a `{ }` watermark, language color bar, and language label, plus a 60px white bottom section with repo metadata (SVG lines 158-193).

#### Scenario: Java project shows Java-colored language bar
- **WHEN** a GitHub repo with language="Java" renders
- **THEN** the top section contains a `{ }` text watermark (18px monospace 700 #f8fafc op=0.15), an 80×4 rx=2 bar filled with #b07219 (Java color), and "Java" label text (9px monospace #94a3b8)

#### Scenario: Scala project shows Scala-colored language bar
- **WHEN** a GitHub repo with language="Scala" renders
- **THEN** the top section contains an 80×4 rx=2 bar filled with #c22d40 (Scala color) and "Scala" label

### Requirement: Bottom section shows repo full name, description, and metadata
The bottom 60px SHALL display: repo full_name (10px monospace #6366f1), description (11px/700 #0f172a), language·license metadata (9px #94a3b8), and star count (10px/700 #f59e0b, right-aligned) (SVG lines 165-168).

#### Scenario: Apache Hadoop shows 14.8k stars
- **WHEN** a repo with full_name="apache/hadoop" and stars=14800 renders
- **THEN** the star count displays "14.8k ★" in amber (#f59e0b), right-aligned at the bottom-right corner

### Requirement: Star count formatting uses k notation for 1000+
Stars SHALL be formatted as "N.Nk ★" for repos with ≥1000 stars, otherwise "{n} ★".

#### Scenario: 520 stars renders without k notation
- **WHEN** a repo has 520 stars
- **THEN** the star count displays "520 ★"
