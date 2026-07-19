## Why

`02-course-home.svg`（140 行）是学科首页的权威视觉规范。当前 CourseLayout + SubjectHome 与 SVG 存在以下结构性偏差：

1. **CourseLayout 顶栏** — SVG line 7-10 定义顶栏 h=56、logo 16px/800/#6366f1、"/" 分隔符 #cbd5e1、课程标题 13px/600、返回链接 11px/#6366f1。当前顶栏使用不同的字号和布局。
2. **CourseSidebar 左侧导航** — SVG lines 13-28 定义 232px 宽面板，不含 CourseThumbnail banner（仅标题文字 + 状态 badge），导航项激活态为左侧 3px 紫色条 + 浅紫背景，标签为"学科首页/教学大纲/智能体/学习成长图谱/知识图谱"。当前侧栏含 CourseThumbnail banner（SVG 中不存在）、使用 lucide 图标（SVG 中不存在）、标签不同（"首页/大纲/..."）。
3. **CourseMaterials 数据源** — 当前从 syllabus_list 创建单条假数据，SVG 显示 3 张真实文档卡片。需要从 API 加载真实课程资料。
4. **BuddyFAB** — SVG lines 133-138 定义白色阴影圆 r=30 + #6366f1 内圆 r=28 + 表情（双眼+微笑弧）+ 红色通知 badge r=10 + 文字标签"学伴小觉"+"全天候陪伴"。当前 FAB 使用 MessageCircle 图标，无表情细节，无文字标签。

## What Changes

### 文件范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/layouts/CourseLayout.tsx` | 修改 | 顶栏逐元素对齐 SVG lines 7-10 |
| `src/layouts/CourseSidebar.tsx` | 重写 | 逐元素对齐 SVG lines 13-28 |
| `src/pages/SubjectHome.tsx` | 修改 | 课程资料数据源修正 |
| `src/components/subject/CourseMaterials.tsx` | 验证 | 确认 SVG lines 36-71 对齐 |
| `src/components/subject/GeneratedResources.tsx` | 验证 | 确认 SVG lines 77-100 对齐 |
| `src/components/subject/VideoGrid.tsx` | 验证 | 确认 SVG lines 106-129 对齐 |
| `src/components/buddy/BuddyFAB.tsx` | 重写 | 逐元素对齐 SVG lines 133-138 |

### SVG 元素逐行对照

#### 1. 顶栏（SVG lines 6-10）

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 7 | 顶栏底板 | `1440×56 fill=#fff stroke=#f1f5f9` | ❌ 高度/样式不同 |
| 8 | Logo | `x=32 y=36 fontSize=16 fontWeight=800 fill=#6366f1 letterSpacing=1` "联觉 LianJue" | ❌ 字号/颜色不同 |
| 9 | 分隔符 | `x=148 y=36 fontSize=13 fill=#cbd5e1` "/" | ❌ 缺失 |
| 9 | 课程标题 | `x=162 y=36 fontSize=13 fontWeight=600 fill=#0f172a` | ❌ 字号不同 |
| 10 | 返回链接 | `x=252 y=36 fontSize=11 fill=#6366f1` "← 返回首页" | ❌ 缺失 |

#### 2. 左侧导航（SVG lines 12-28）

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 13 | 侧栏底板 | `232×944 fill=#fff stroke=#f1f5f9` | 需验证 |
| 14 | 课程标题 | `x=20 y=88 fontSize=15 fontWeight=700 fill=#0f172a` | ❌ 当前含 CourseThumbnail |
| 15 | 状态 badge | `x=20 y=98 w=52 h=20 rx=5 fill=#ede9fe` + "已发布" 9px/600/#6366f1 | ❌ 当前用 emerald 色 |
| 17 | 激活项背景 | `rect 208×38 rx=8 fill=#6366f1 opacity=0.1` + 左条 `rect 3×38 rx=1.5 fill=#6366f1` | ❌ 缺少左条 |
| 18 | 激活项文字 | `x=40 y=162 fontSize=13 fontWeight=700 fill=#6366f1` "学科首页" | ❌ 标签不同 |
| 19-22 | 非激活项 | `x=40, fontSize=13, fill=#475569` "教学大纲/智能体/学习成长图谱/知识图谱" | ❌ 标签+样式不同 |
| 24 | 分隔线 | `line (20,350)→(212,350) stroke=#f1f5f9` | ✅ |
| 25 | "快捷入口" | `x=20 y=376 fontSize=11 fill=#94a3b8 fontWeight=600` | 需验证 |
| 26-27 | 快捷链接 | "课程进度" "我的测验" 12px/#475569 | ❌ 含图标 |

**关键差异**: SVG 侧栏不含 CourseThumbnail banner、不含 lucide 图标、激活态有左侧 3px 色条。

#### 3. 课程资料（SVG lines 32-71）

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 33 | 标题 | `x=0 y=14 fontSize=18 fontWeight=700 fill=#0f172a` "课程资料" | ✅ |
| 34 | 副标题 | `x=0 y=32 fontSize=12 fill=#94a3b8` "知识文档与参考资料" | ✅ |
| 37 | 卡片 | `252×135 rx=10 fill=#fff stroke=#e2e8f0` + `3px top bar fill=#64748b` | ✅ |
| 38-44 | 文档 SVG | 内部区 220×90 rx=4 + 折角 polygon + 4 行文字 rect | ✅ |
| 45-46 | 文本 | 标题 12px/700 + "文档" 10px 右对齐 | ✅ |

**主要问题**: 数据源——当前只从 syllabus_list 构造单条假数据，需要从实际文档 API 加载。

#### 4. AI 生成资源（SVG lines 74-100）— 基本对齐

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 74 | 标题 | "AI 生成资源" 18px/700 | ✅ |
| 78 | 卡片 | `252×124 rx=10` + 3px 彩色顶条 | ✅ |
| 79-82 | 图标 + 文字 | 左侧类型 SVG + 右侧标题/类型·匹配/描述 | ✅ |

#### 5. 相关视频（SVG lines 103-129）— 基本对齐

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 103 | 标题 | "相关视频" 18px/700 | ✅ |
| 107-108 | 卡片 | `252×172 rx=10` + 深色缩略图 108px | ✅ |
| 109 | 播放按钮 | polygon 三角 + 时长 text 9px | ✅ |

#### 6. BuddyFAB（SVG lines 132-138）

| SVG 行 | 元素 | 属性 | 实现状态 |
|--------|------|------|---------|
| 134 | 外圆 | `cx=0 cy=0 r=30 fill=#fff filter=url(#ss)` — 白色阴影底 | ❌ 缺失 |
| 134 | 内圆 | `cx=0 cy=0 r=28 fill=#6366f1` | ❌ 用纯色 56px 圆替代 |
| 135 | 左眼 | `cx=-6 cy=-3 r=3.5 fill=#fff opacity=0.9` | ❌ MessageCircle 图标替代 |
| 135 | 右眼 | `cx=6 cy=-3 r=3.5 fill=#fff opacity=0.9` | ❌ |
| 136 | 微笑 | `path M-8,8 Q0,18 8,8 stroke=#fff w=2 op=0.6` | ❌ |
| 137 | 通知 badge | `cx=20 cy=-20 r=10 fill=#ef4444` + "1" 9px/700/white | ❌ 红点替代 |
| 139 | 文字标签 | "学伴小觉" 11px/#6366f1 + "全天候陪伴" 10px/#94a3b8 | ❌ 缺失 |

## Capabilities

### Modified Capabilities
- `course-layout-header`: 顶栏逐元素对齐 SVG——56px 高、logo 16px/800/ls=1/#6366f1、"/" 分隔符 #cbd5e1、课程标题 13px/600、返回链接 11px/#6366f1
- `course-sidebar`: 侧栏移除 CourseThumbnail banner，仅标题文字+badge；导航项激活态加左侧 3px 色条；移除 lucide 图标；标签对齐 SVG
- `buddy-fab`: 重写为 SVG 表情风格——白色阴影外圆 + indigo 内圆 + 双眼 + 微笑弧 + 红色数字 badge + 文字标签
- `subject-home-materials`: 数据源从 syllabus_list 改为知识文档 API 调用

## Impact

- **修改文件**: 7 个文件（见上表）
- **不修改文件**: GeneratedResources.tsx、VideoGrid.tsx（已验证对齐）
- **SVG 对照**: `02-course-home.svg` 140 行全量
- **零新增 API 端点**: 所有数据可从现有 API 获取
