## Context

GraphModal 是全屏图谱弹窗，显示 D3 force/tree 布局的完整知识图谱。`ref-graph-modal.svg` 定义了 overlay + 画布 + 控制面板的视觉规范。

## 数据流

```
GraphModal
  ├── useGraphModalStore → {open, title, nodes, edges, layout, highlightPath, candidates}
  ├── nodes/edges → D3GraphViewer
  └── candidates → CandidatePathSelector (overlay)
```

## 函数级收口

### GraphModal
- **输入**: `{open, onClose, title, nodes, edges, layout, highlightPath, children}`
- **输出**: Fullscreen overlay + D3 canvas + close button
- **Overlay**: `fill=rgba(0,0,0,0.7)` backdrop
- **Canvas**: `fill=#03040a` dark background
- **Close**: top-right button
- **Title bar**: top-left, light text on dark
- **Control panel**: bottom-right toolbar (zoom, layout toggle, snapshot)

### CandidatePathSelector (when candidates exist)
- Bottom-right overlay card `w-64 max-h-[60vh] bg-white/90 backdrop-blur rounded-xl`
- Lists candidate paths with rank + select button
