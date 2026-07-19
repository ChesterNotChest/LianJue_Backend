## Why

`01-dashboard.svg` (332 行) 是 Dashboard 页面的权威视觉规范。当前实现与 SVG 存在以下结构性偏差：

1. **CourseCardGrid** — 卡片内缺少 week/semester 行、进度条、掌握统计行。这些在 SVG lines 36-40 明确定义。数据源需要从 study_graph API 获取。
2. **RecentResources** — 卡片结构与 SVG 不一致。SVG 定义 card 为 296×160 单体（上部 100px 缩略图 + 下部 60px 文本在同一 rect 内），而当前实现把 DocThumbnail 和文本分离为两个独立区域。
3. **RecommendedExploration** — 当前实现无缩略图图形，仅纯文本。SVG (lines 126-152) 定义了两种卡片：document 型（折角文档 + 92% badge）和 mindmap 型（节点树 + 85% badge），上部 100px 为类型色彩区域。
4. **GitHubProjects** — 当前实现使用白色卡片 + 细颜色条，SVG (lines 158-193) 定义上部 100px 为深色 `#1e293b` 区域，内含 `{ }` 水印 + 语言色条 + 语言标签。
5. **LifelongGraph** — 右侧课程统计卡片过于简化。SVG (lines 265-311) 定义每个卡片 472×108 rx=12，含 4px 彩色顶条、标题、标签 badge、已掌握/学习中/薄弱统计行、进度条、薄弱提示文本、"进入学习" 按钮。
6. **Section Dividers** — SVG 定义了两个滚动指示器（lines 197-198 和 315-317），当前缺失。
7. **Dashboard.tsx** — 存在重复的欢迎区域（lines 211-219，"你好, {userName}"），该元素在 SVG 中不存在（用户信息已在 Header 中）。

## What Changes

### 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/pages/Dashboard.tsx` | 修改 | 移除重复欢迎区域，添加 section dividers，增强数据加载 |
| `src/components/dashboard/CourseCardGrid.tsx` | 重写 | 逐元素对齐 SVG lines 28-67 |
| `src/components/dashboard/RecentResources.tsx` | 重写 | 逐元素对齐 SVG lines 70-121 |
| `src/components/dashboard/RecommendedExploration.tsx` | 重写 | 逐元素对齐 SVG lines 124-153 |
| `src/components/dashboard/GitHubProjects.tsx` | 重写 | 逐元素对齐 SVG lines 156-194 |
| `src/components/dashboard/LifelongGraph.tsx` | 重写 | 逐元素对齐 SVG lines 200-313 |
| `src/components/dashboard/GalaxyReveal.tsx` | 验证 | 确认已对齐 SVG lines 319-331 |

### SVG 元素逐行对照

#### 1. Header（lines 13-17）— 已基本对齐

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 13 | 渐变 bar | `x=0 y=0 w=1440 h=64 fill=url(#hdr)` — #4f46e5→#6366f1 | ✅ 已实现 |
| 15 | Logo | `x=40 y=40 fontSize=20 fontWeight=800 fill=#fff letterSpacing=1` "联觉 LianJue" | ✅ 已实现 |
| 16 | 头像圆 | `cx=1340 cy=32 r=16 fill=rgba(255,255,255,0.2)` | ✅ 已实现 |
| 16 | 头像字母 | `x=1340 y=37 fontSize=12 fontWeight=700 fill=#fff textAnchor=middle` "U" | ✅ 已实现 |
| 17 | 用户名 | `x=1364 y=28 fontSize=11 fill=rgba(255,255,255,0.9)` | ✅ 已实现 |
| 17 | 邮箱 | `x=1364 y=42 fontSize=9 fill=rgba(255,255,255,0.55)` | ✅ 已实现 |

#### 2. 页面标题区（lines 19-26）

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 19 | 标题 | `x=80 y=118 fontSize=28 fontWeight=800 fill=#0f172a` "我的学习" | ✅ 已实现 |
| 19 | 副标题 | `x=80 y=142 fontSize=14 fill=#64748b` "继续你的学习旅程" | ✅ 已实现 |
| 21-25 | 搜索框 | `280×36 rx=10 fill=#fff stroke=#e2e8f0` + 搜索图标 + placeholder "搜索课程..." | ✅ 已实现 |
| 26 | 创建按钮 | `x=1240 y=106 w=120 h=38 rx=10 fill=#6366f1` "+ 创建新学科" 13px/700 | ✅ 已实现 |

**问题**: Dashboard.tsx lines 211-219 有重复的欢迎区域（"你好, {userName}"），SVG 中不存在。

#### 3. Course Cards（lines 28-67）— 3 张卡片，需重写

##### Card 1: 已发布 diagonal（lines 30-42）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 30 | 卡片底板 | `384×266 rx=14 fill=#fff stroke=#e2e8f0 filter=url(#cs)` |
| 31 | Banner | `384×136 rx=14 fill=#4f46e5` + 底部平铺 `rect y=68 h=68 fill=#4f46e5` |
| 32 | 装饰圆 1 | `cx=320 cy=40 r=80 fill=rgba(255,255,255,0.06)` |
| 32 | 装饰圆 2 | `cx=80 cy=100 r=120 fill=rgba(255,255,255,0.04)` |
| 33 | 斜线 1 | `line (60,20)→(200,100) stroke=rgba(255,255,255,0.08) strokeWidth=2` |
| 33 | 斜线 2 | `line (120,20)→(240,100) stroke=rgba(255,255,255,0.06) strokeWidth=2` |
| 34 | 标题 | `x=192 y=82 fontSize=28 fontWeight=800 fill=#fff textAnchor=middle letterSpacing=2` |
| 35 | 副标题 | `x=192 y=108 fontSize=12 fill=rgba(255,255,255,0.5) textAnchor=middle` |
| 36 | 周/学期 | `x=16 y=158 fontSize=12 fontWeight=700 fill=#0f172a` "18 周 · 2025秋" |
| 37 | 状态 badge | `x=240 y=154 w=48 h=20 rx=5 fill=#ede9fe` + text "已发布" 9px/600/#6366f1 |
| 38 | "学习进度" | `x=16 y=188 fontSize=11 fill=#64748b` |
| 38 | 进度 % | `x=356 y=188 fontSize=11 fontWeight=700 fill=#22c55e textAnchor=end` "68%" |
| 39 | 进度条底 | `x=16 y=196 w=352 h=6 rx=3 fill=#f1f5f9` |
| 39 | 进度条填充 | `x=16 y=196 w=240 h=6 rx=3 fill=url(#pg)` — green gradient |
| 40 | 统计行 | `x=16 y=224 fontSize=10 fill=#94a3b8` "12 节点已掌握 · 4 薄弱 · 2小时前活跃" |
| 41 | "进入学习" | `x=16 y=234 w=96 h=26 rx=8 fill=#6366f1` + text 12px/700/white |
| 42 | "管理" | `x=120 y=234 w=52 h=26 rx=8 fill=#f1f5f9` + text 10px/#64748b |

##### Card 2: 已发布 stacked（lines 44-56）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 45 | 卡片底板 | `384×266 rx=14 fill=#fff stroke=#e2e8f0 filter=url(#cs)` |
| 46 | Banner | `384×136 rx=14 fill=#0f766e` + 底部平铺 `rect y=68 h=68 fill=#0f766e` |
| 47 | 装饰圆 1 | `cx=320 cy=40 r=80 fill=rgba(255,255,255,0.06)` |
| 47 | 装饰圆 2 | `cx=80 cy=80 r=100 fill=rgba(255,255,255,0.04)` |
| 48 | 堆叠矩形 | 3 rect: `x=60,y=80 40×40` + `x=120,y=60 40×40` + `x=90,y=40 30×40`, rx=4, stroke=#fff w=3, op=0.1 |
| 49 | 标题 | `x=192 y=82 fontSize=28 fontWeight=800 fill=#fff textAnchor=middle letterSpacing=2` "Python" |
| 50 | 副标题 | `x=192 y=108 fontSize=12 fill=rgba(255,255,255,0.5) textAnchor=middle` "程序设计 · Software" |
| 51 | 周/学期 | `x=16 y=158 fontSize=12 fontWeight=700 fill=#0f172a` "12 周 · 2025秋" |
| 52 | "学习进度" | `x=16 y=188 fontSize=11 fill=#64748b` |
| 52 | 进度 % | `x=356 y=188 fontSize=11 fontWeight=700 fill=#f59e0b textAnchor=end` "34%" |
| 53 | 进度条底 | `x=16 y=196 w=352 h=6 rx=3 fill=#f1f5f9` |
| 53 | 进度条填充 | `x=16 y=196 w=120 h=6 rx=3 fill=#f59e0b` — amber |
| 54 | 统计行 | `x=16 y=224 fontSize=10 fill=#94a3b8` "5 节点已掌握 · 8 薄弱 · 昨天活跃" |
| 55 | "进入学习" | `x=16 y=234 w=96 h=26 rx=8 fill=#6366f1` |
| 56 | "管理" | `x=120 y=234 w=52 h=26 rx=8 fill=#f1f5f9` |

##### Card 3: 草稿（lines 59-66）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 60 | 卡片底板 | `384×266 rx=14 fill=#fafafa stroke=#e2e8f0 strokeDasharray=6,3` |
| 61 | Banner | `384×136 rx=14 fill=#94a3b8` + 底部平铺 `rect y=68 h=68 fill=#94a3b8` |
| 62 | 标题 | `x=192 y=82 fontSize=28 fontWeight=800 fill=#fff textAnchor=middle` "Machine Learning" |
| 63 | 副标题 | `x=192 y=108 fontSize=12 fill=rgba(255,255,255,0.4) textAnchor=middle` "草稿 · 尚未发布" |
| 64 | 状态文本 | `x=16 y=158 fontSize=12 fontWeight=700 fill=#94a3b8` "课程准备中" |
| 65 | 按钮 | `x=16 y=234 w=96 h=26 rx=8 fill=#f1f5f9 stroke=#e2e8f0` + text "等待中" 12px/700/#94a3b8 |

#### 4. Recent Resources（lines 70-121）— 4 张卡片，需重写

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 70 | 标题 | `x=0 y=0 fontSize=16 fontWeight=700 fill=#0f172a` "最近资源" |
| 70 | 副标题 | `x=0 y=18 fontSize=12 fill=#94a3b8` "跨课程最近生成的学习材料" |
| 71 | 刷新按钮 | `x=1200 y=4 w=60 h=24 rx=6 fill=#f1f5f9` + 刷新图标 + "刷新" 10px/#64748b |
| 73-83 | Card 1 Mindmap | `296×160 rx=10 fill=#fff stroke=#e2e8f0 filter=url(#ts)` |
| 74 | 上部区域 | `296×100 rx=10 fill=#ecfdf5` + 底部平铺 `rect y=50 h=50 fill=#ecfdf5` |
| 75-78 | 思维导图 SVG | 中心圆 r=14 + 内点 r=4 + 上分支 line+circle + 左下分支 line+circle + 右下分支 line+circle |
| 79 | 下部区域 | `296×60 rx=10 fill=#fff` + 底部平铺 `rect y=110 h=50 fill=#fff` |
| 80-82 | 文本 | title 12px/700, type·course 10px, time·match 9px |
| 85-93 | Card 2 Quiz | `296×160 rx=10`, 上部 `#fffbeb`, "?" 水印 28px/800 op=0.12, 2 选项框 96×16 rx=4, 下部 white |
| 96-106 | Card 3 PPT | `296×160 rx=10`, 上部 `#fef2f2`, 幻灯片预览 116×64 rx=6, title+text lines+mini chart, 下部 white |
| 109-120 | Card 4 Coding | `296×160 rx=10`, 上部 `#1e293b`, 5 行 monospace 代码 9px 语法着色, 下部 white |

**核心结构**: 每张卡片是**单体**——上部 100px（类型色彩 + SVG 图标）和下部 60px（文本）在同一个 `rect rx=10` 内。

#### 5. Recommended Exploration（lines 124-153）— 2 张卡片，当前无缩略图

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 124 | 标题 | `x=0 y=0 fontSize=16 fontWeight=700 fill=#0f172a` "推荐探索" |
| 124 | 副标题 | `x=0 y=18 fontSize=12 fill=#94a3b8` "基于薄弱点 · knowledge/search · 匹配度排序" |
| 126-139 | Card 1 Document | `296×160 rx=10 fill=#fff stroke=#e2e8f0 filter=url(#ts)` |
| 127 | 上部区域 | `296×100 rx=10 fill=#eff6ff` + 底部平铺 `rect y=50 h=50 fill=#eff6ff` |
| 128 | 文档预览 | `256×72 rx=6 fill=#fff stroke=#bfdbfe` — 内部文档区 |
| 129-132 | 4 行文字 rect | w=60/80/50/70 rx=2 fill=#93c5fd/#bfdbfe |
| 133 | 折角 polygon | `points="276,14 276,34 256,34" fill=#bfdbfe` |
| 134-135 | 匹配度 badge | `20×20 rx=6 fill=#3b82f6 op=0.15` + "92%" 9px/700/#3b82f6 |
| 136 | 下部区域 | `296×60 rx=10 fill=#fff` + 底部平铺 |
| 137-138 | 文本 | title 12px/700 + description 10px/#64748b |
| 141-152 | Card 2 Mindmap | `296×160 rx=10`, 上部 `#ecfdf5`, 中心圆 r=18 + 内点 r=5 + 3 分支, 85% badge `fill=#059669 op=0.15` |

**注意**: 推荐探索的卡片结构与 DocThumbnail 不同——它们是横向 296×160 布局，缩略图在左侧上方而非居中。

#### 6. GitHub Projects（lines 156-194）— 3 张卡片，布局完全不同

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 156 | 标题 | `x=0 y=0 fontSize=16 fontWeight=700 fill=#0f172a` "实训项目" |
| 156 | 副标题 | `x=0 y=18 fontSize=12 fill=#94a3b8` "GitHub 开源项目 · 按相关度与 Star 数检索" |
| 157 | 刷新按钮 | `60×24 rx=6 fill=#f1f5f9` + 刷新图标 |
| 159-169 | Card 1 HBase | `296×160 rx=10 fill=#fff stroke=#e2e8f0 filter=url(#ts)` |
| 160 | 上部区域 | `296×100 rx=10 fill=#1e293b` + 底部平铺 |
| 161 | `{ }` 水印 | `x=148 y=50 fontSize=18 fontFamily=monospace fontWeight=700 fill=#f8fafc op=0.15` |
| 162 | 语言色条 | `x=20 y=60 w=80 h=4 rx=2 fill=#b07219 op=0.6` — Java 色 |
| 162 | 语言标签 | `x=108 y=64 fontSize=9 fontFamily=monospace fill=#94a3b8` "Java" |
| 163 | 第二色条 | `x=140 y=60 w=60 h=4 rx=2 fill=#38bdf8 op=0.4` |
| 164 | 下部区域 | `296×60 rx=10 fill=#fff` + 底部平铺 |
| 165-168 | 文本 | repo name 10px monospace/#6366f1 + description 11px/700 + lang·license 9px + stars 10px/700/amber |
| 171-181 | Card 2 Hadoop | 同结构，Java，14.8k ★ |
| 183-193 | Card 3 Spark | 同结构，Scala (#c22d40)，40.1k ★ |

#### 7. Section Dividers（lines 197-198, 315-317）— 缺失

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 197 | Divider 1 | "向下滚动探索更多" 12px/#94a3b8 + 水平线 + 下箭头 polygon |
| 316-317 | Divider 2 | "向下滚动探索知识全景" 12px/#94a3b8 + 水平线 + 双下箭头 |

#### 8. Lifelong Learning Graph（lines 200-313）— 需重写右侧卡片

##### 主容器（lines 200-219）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 201 | Section 背景 | `1440×520 fill=#f1f5f9` |
| 203 | 标题 | `x=0 y=0 fontSize=16 fontWeight=700 fill=#0f172a` "终身学习图谱" |
| 204 | 副标题 | `x=0 y=18 fontSize=12 fill=#94a3b8` |
| 207 | 主容器 | `1280×420 rx=14 fill=#fff stroke=#e2e8f0 filter=url(#cs)` |
| 210-219 | Stats Header | `1248×40 rx=8 fill=#f8fafc`; 5 个指标 「课程数 2 | 总节点 33 | 已掌握 12 学习中 5 薄弱 16」用 `line` 分隔 |

##### 左侧 D3 图（lines 222-262）— 已基本对齐

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 223 | 图容器 | `760×350 rx=14 fill=#fff stroke=#e2e8f0` |
| 224 | 标题栏 | `760×36 rx=14 fill=#fafafa` + "终身学习图谱" 13px/700 + 副文本 |
| 230-247 | 节点 | central hub r=22, 绿色节点 r=16/13 (mastered), 紫色节点 r=13 (learning), 红色虚线节点 r=13 (weak) |
| 249-254 | 边 | 多条 `<line>` 连接节点 |
| 256-259 | 图例 | 3 项: 已掌握(绿)/学习中(紫)/薄弱(红虚线) |

##### 右侧课程卡片（lines 265-311）— **需重写**

###### Card 1: 大数据概论（lines 267-281）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 267 | 卡片 | `472×108 rx=12 fill=#fff stroke=#e2e8f0` |
| 268 | 顶条 | `472×4 rx=2 fill=#6366f1` — 紫色 4px |
| 269 | 标题 | `x=16 y=26 fontSize=13 fontWeight=700 fill=#0f172a` "大数据概论" |
| 270 | 标签 badge | `x=120 y=16 w=36 h=16 rx=4 fill=#ede9fe` + "RAG" 8px/#6366f1 |
| 272 | 已掌握 | `x=0 y=0 fontSize=10 fill=#64748b` "已掌握 12" |
| 272 | 学习中 | `x=90 y=0 fontSize=10 fill=#64748b` "学习中 5" |
| 273 | 薄弱 | `x=180 y=0 fontSize=10 fill=#64748b` "薄弱 4" |
| 274 | 进度 % | `x=250 y=0 fontSize=10 fontWeight=700 fill=#22c55e` "68%" |
| 278 | 进度条底 | `440×6 rx=3 fill=#f1f5f9` |
| 278 | 进度条填充 | `440×6 rx=3 fill=#22c55e` — 填充比例 |
| 280 | 薄弱提示 | `x=16 y=90 fontSize=10 fill=#94a3b8` "薄弱: RowKey 热点 · 预分区策略" |
| 281 | "进入学习" | `x=370 y=78 w=80 h=22 rx=6 fill=#f1f5f9` + text 9px/#6366f1 |

###### Card 2: Python（lines 284-299）— 同结构，amber 顶条

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 285 | 卡片 | `472×108 rx=12` |
| 286 | 顶条 | `472×4 rx=2 fill=#f59e0b` — amber |
| 287 | 标题 | "Python 程序设计" |
| 288 | 标签 badge | `w=52 fill=#fef3c7` + "Software" 8px/#d97706 |
| 290-294 | 统计 | 已掌握 5 / 学习中 3 / 薄弱 8 / 34% |
| 296 | 进度条填充 | `fill=#f59e0b` — amber |
| 298 | 薄弱提示 | "薄弱: 装饰器 · 生成器" |

###### Card 3: 空占位（lines 303-310）

| SVG 行 | 元素 | 属性 |
|--------|------|------|
| 304 | 卡片 | `472×108 rx=12 fill=#f8fafc stroke=#e2e8f0 strokeDasharray=5,3` |
| 305 | 标题 | `x=236 y=44 fontSize=14 fontWeight=700 fill=#cbd5e1 textAnchor=middle` "新的学科等着你探索" |
| 306 | 副文本 | `x=236 y=64 fontSize=11 fill=#d1d5db textAnchor=middle` "完成一门课程后，开始新的学习旅程" |
| 308 | 按钮 | `w=150 h=22 rx=6 fill=#e2e8f0` + "浏览可用学科" 9px/#94a3b8 |

#### 9. Galaxy Reveal（lines 319-331）— 已基本对齐

| SVG 行 | 元素 | 属性 | 状态 |
|--------|------|------|------|
| 320 | 渐变背景 | `1440×540 fill=url(#spaceR)` — 4-stop gradient | ✅ |
| 321 | 星星 | 8+ circles，3 色 (warm/cool/mid) | ✅ 50 stars seeded |
| 322 | 星云 1 | path stroke=#38bdf8 w=50 op=0.03 | ✅ |
| 323 | 星云 2 | path stroke=#a78bfa w=44 op=0.025 | ✅ |
| 324 | 中心光晕 | 3 circles r=60/26/8 | ✅ |
| 327-328 | 知识标签 | RAG/Algorithm/Software 节点 r=14 + text | ✅ |
| 330 | "知识全景" | `x=720 y=260 fontSize=18 fontWeight=800 fill=rgba(248,250,252,0.4) letterSpacing=3` | ✅ |
| 331 | CTA | "进入全屏知识总览" 13px rgba(129,140,248,0.6) | ✅ |

## Capabilities

### New Capabilities
- `dashboard-course-card`: 完整课程卡片——banner + week/semester + 状态 badge + 进度条 + 掌握统计 + 操作按钮。数据源: syllabus_list API + study_graph per-syllabus query。
- `dashboard-recent-resource-card`: 单体资源卡片——上部 100px 类型色区（含 DocThumbnail 风格 SVG）+ 下部 60px 文本区。数据源: generative_list API。
- `dashboard-recommended-card`: 推荐探索卡片——上部 100px 文档/思维导图预览 + 匹配度 badge + 下部文本。数据源: knowledge/search API。
- `dashboard-github-card`: GitHub 项目卡片——上部 100px 深色代码区（含 `{ }` 水印 + 语言色条）+ 下部文本 + star 计数。数据源: knowledge/github_search API。
- `dashboard-lifelong-course-stat`: 终身图谱课程统计卡片——472×108，4px 顶条 + 标题 + badge + 统计行 + 进度条 + 薄弱提示 + 操作按钮。数据源: study_graph API sibling_trees。
- `dashboard-section-divider`: 滚动指示器——文本 + 水平线 + 下箭头。

### Modified Capabilities
- `CourseCardGrid`: 从仅 banner+按钮扩展为完整卡片（banner + metadata + progress + stats + buttons）
- `RecentResources`: 从分离式布局改为 SVG 单体卡片结构
- `RecommendedExploration`: 从纯文本卡片改为带缩略图预览的视觉卡片
- `GitHubProjects`: 从白色浅色卡片改为深色代码风格卡片
- `LifelongGraph`: 右侧课程统计卡片从简化版改为 SVG 精确版

## Impact

- **修改文件**: 7 个文件（见上表）
- **不修改文件**: GalaxyReveal.tsx（已验证对齐），CourseThumbnail.tsx，DocThumbnail.tsx（由 portal-p1-thumbnails 覆盖）
- **SVG 对照**: `01-dashboard.svg` 332 行全量
- **数据源变更**: study_graph API 需要 per-syllabus 查询以获取进度和掌握统计
- **零新增 API 端点**: 所有数据可从现有 API 获取
