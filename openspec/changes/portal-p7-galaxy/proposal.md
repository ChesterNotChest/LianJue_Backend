## Why

`06-galaxy.svg` 是知识图谱（Galaxy）页面的权威视觉规范。当前 FullGalaxy 和 KnowledgeGalaxyPage 数据流完整（syllabus_list → graph_ids → fetchGraphSnapshot → galaxyStore → useGraphMatch → NebulaOverlay → useHeartbeat），但以下视觉元素需对照 SVG 修正：

1. **深空子窗口边框**（SVG lines 33-35）— `1176×804 rx=14 fill=none stroke=#1e293b stroke-width=2`
2. **视图切换 pills**（SVG lines 64-67）— "银河" active (52×22 rx=11, blue glass) / "平面" inactive (48×22 rx=11, transparent)
3. **数据源 badge**（SVG line 70）— `240×18 rx=4 fill=rgba(0,0,0,0.3)` + info text 7px/#475569
4. **详情面板**（SVG lines 73-80）— dark glass `240×320 rx=12 fill=rgba(10,16,30,0.92)` + DOC badge + title + info bar
5. **NebulaOverlay stardust**（SVG lines 55-61）— glow filter + 5 highlight nodes (r=5, green/indigo/red) + connecting lines

## What Changes

### 文件范围

| 文件 | 操作 |
|------|------|
| `src/pages/FullGalaxy.tsx` | 深空边框 + 视图切换 pills + 数据源 badge |
| `src/pages/KnowledgeGalaxyPage.tsx` | 深空边框 + 视图切换 pills |
| `src/components/galaxy/DetailPanel.tsx` | 重写 dark glass 面板样式 |
| `src/components/galaxy/NebulaOverlay.tsx` | 验证 glow filter + stardust 节点 |

### 关键 SVG 元素对照

| 区域 | SVG 行 | 属性 |
|------|--------|------|
| Dark frame | 33-35 | `1176×804 rx=14 fill=none stroke=#1e293b w=2` + `fill=url(#spaceBg)` |
| Starfield | 38 | 10+ circles r=0.5-1, 3 色 (warm #f8d89c / cool #b8d9ff / mid #8ba4d6), op=0.3 |
| Spiral arms | 41-42 | 2 paths: blue #38bdf8 w=46 op=0.03 + purple #a78bfa w=40 op=0.025 |
| Center glow | 44 | 3 circles r=60/24/8 + glow filter |
| Knowledge clusters | 47-52 | RAG/Algorithm/Software/大数据概论 labels + circles r=14/8 |
| Stardust | 55-61 | 5 nodes r=5 + glow filter + lines, green mastered/indigo learning/red weak |
| View toggles | 64-67 | 银河 active `52×22 rx=11 fill=rgba(56,189,248,0.2) stroke=rgba(56,189,248,0.25)` |
| Data badge | 70 | `240×18 rx=4 fill=rgba(0,0,0,0.3)` + "data: knowledge-graph/snapshot · NebulaOverlay 匹配高亮" 7px/#475569 |
| Detail panel | 73-80 | `240×320 rx=12 fill=rgba(10,16,30,0.92)` + close btn + DOC badge 8px/700/#7dd3fc ls=1 + title 14px/800/#f8fafc + summary 10px/#b6c3d8 + info bar `212×28 rx=6 fill=rgba(14,165,233,0.12)` |

## Impact

- **修改文件**: 4 个
- **SVG 对照**: `06-galaxy.svg` 全量
