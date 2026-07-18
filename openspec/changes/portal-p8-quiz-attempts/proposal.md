## Why

`08-quiz-attempts.svg`（180 行）是我的测验页面的权威视觉规范。当前 QuizAttempts 需对照 SVG 重写测验卡片为三栏布局。

### 关键 SVG 元素对照

| 区域 | SVG 行 | 属性 |
|------|--------|------|
| Stats bar | 31-38 | `880×48 rx=10` 4 列: 可用测验 3 / 已完成 2 green / 平均得分 75% green / 薄弱知识点 4 red |
| Quiz Card 容器 | 43, 105, 153 | `880×200 rx=12 fill=#fff stroke=#e2e8f0` |
| **Left** 测验标识 | 46-56 | `280×168 rx=8 fill=#fef3c7` + "测验" 10px/600/#f59e0b + title 16px/700 + desc 11px + "开始测验" btn `100×28 rx=8 fill=#f59e0b` + "查看详情" btn `72×28 rx=8 fill=#fff stroke=#e2e8f0` |
| **Middle** 成绩摘要 | 59-86 | "成绩摘要" header + **Best** card `160×48 rx=8 fill=#dcfce7 stroke=#bbf7d0` (绿底: 最佳/分数/正确数/第N次) + **Recent** card `160×48 rx=8 fill=#f8fafc stroke=#e2e8f0` (灰底: 最近/分数/提交次数) + **薄弱点** `344×44 rx=6 fill=#fef2f2` (red tag chips) |
| **Right** 提交历史 | 89-100 | "提交历史" header + 3 entries: `160×28 rx=6` (green circle if ≥70%, red if <70%), "第N次 · X%" + score right-aligned |
| Untouched card | 152-169 | `880×120 rx=12`, dashed border, gray placeholder, "开始测验" btn `100×28 rx=8 fill=#6366f1` |

### Quiz Card 2 变体
- Best card: amber variant `fill=#fef3c7 stroke=#fde68a`（用于 70% 中等分数）
- Weak points: Combiner + Partitioner tags

## What Changes

| 文件 | 操作 |
|------|------|
| `src/pages/QuizAttempts.tsx` | 重写 QuizCard 为 SVG 三栏布局 |

## Impact

- **修改文件**: 1 个
- **数据源**: `generative_list` (type=quiz) + `quiz_attempts` API
- **SVG 对照**: `08-quiz-attempts.svg` 180 行全量
