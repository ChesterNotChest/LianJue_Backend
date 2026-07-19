## Context

Galaxy 页面含 FullGalaxy（终生图谱）和 KnowledgeGalaxyPage（单课程知识图谱），两者共享数据流和视觉组件。

## 数据流

```
FullGalaxy / KnowledgeGalaxyPage
  │
  ├── POST /api/syllabus_list → syllabuses → extract graph_ids
  ├── POST /api/knowledge_graph/snapshot {graph_ids} → galaxyStore.snapshot
  ├── GET /api/study_graph/detail → treeResponseToGraph() → studyNodes
  │
  ├── useGraphMatch(studyNodes, galaxyNodes) → matched pairs
  ├── NebulaOverlay({matches, boost}) → stardust highlighting
  └── useHeartbeat → auto-refresh every 30s
```

## 函数级收口

### GalaxyViewport（NEW — 深空子窗口包装器）
- **输入**: children, `width=1176, height=804`
- **输出**: dark frame + space background
- **内部逻辑**:
  1. 外层 border: `rect 1176×804 rx=14 fill=none stroke=#1e293b strokeWidth=2`
  2. 内层 background: `rect 1176×804 rx=14 fill=url(#spaceBg)` — linearGradient #03040a→#080c1a

### ViewToggles（MODIFIED）
- **状态**: `viewMode: "galaxy" | "flat"`
- **输出**:
  - 银河 active: `52×22 rx=11 fill=rgba(56,189,248,0.2) stroke=rgba(56,189,248,0.25)` + text 9px/700/#38bdf8
  - 平面 inactive: `48×22 rx=11 fill=rgba(255,255,255,0.03)` + text 9px/#475569

### DataSourceBadge（NEW）
- **输出**: `240×18 rx=4 fill=rgba(0,0,0,0.3)` + text "data: knowledge-graph/snapshot · NebulaOverlay 匹配高亮" 7px/#475569 textAnchor=middle

### DetailPanel（MODIFIED）
- **输入**: `{node: GalaxyNode | null, onClose}`
- **输出**: `240×320 rx=12 fill=rgba(10,16,30,0.92) stroke=rgba(56,189,248,0.08)`
- **内部逻辑**:
  1. Close button: `16×16 rx=8 fill=rgba(255,255,255,0.06)` + text "x" 10px/#64748b
  2. DOC badge: text "DOC" 8px/700/#7dd3fc letterSpacing=1
  3. Title: `14px/800/#f8fafc` — node title
  4. Summary: `10px/#b6c3d8` — node summary
  5. Info bar: `212×28 rx=6 fill=rgba(14,165,233,0.12)` + "RAG / Doc / N links" 9px/#d7f1ff
  6. Divider line
