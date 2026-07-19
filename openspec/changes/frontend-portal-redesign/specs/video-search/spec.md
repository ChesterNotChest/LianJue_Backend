# External Search APIs

后端封装的外部检索 API：B站视频搜索 + GitHub 项目搜索。

## ADDED Requirements

### Requirement: Video search endpoint
系统 SHALL 提供 `POST /api/knowledge/video_search` 端点，接受搜索词和可选主题，返回归一化的视频结果列表。

#### Scenario: Basic keyword search
- **WHEN** 前端发送 `{query: "HBase RowKey 设计", max_results: 10}`
- **THEN** 系统返回 `{videos: [{title, thumbnail_url, video_url, duration, source, author}]}`，其中 `source` 为 `"bilibili"`
- **AND** 结果数量不超过 `max_results`

#### Scenario: Search with topic constraint
- **WHEN** 前端发送 `{query: "分布式存储", topic: "HBase", max_results: 8}`
- **THEN** 系统将 topic 与 query 组合后检索
- **AND** 返回结果与 topic 相关

#### Scenario: Empty results
- **WHEN** 检索无匹配结果
- **THEN** 返回 `{videos: []}`，不报错

### Requirement: Normalized video result schema
系统 SHALL 对每个视频结果返回统一 schema，屏蔽不同视频源的差异。

#### Scenario: B站 result normalization
- **WHEN** B站 API 返回原始数据
- **THEN** 系统提取并归一化为 `{title, thumbnail_url, video_url, duration, source: "bilibili", author, play_count?, description?}`

### Requirement: Reasonable timeout
所有外部搜索 SHALL 在 8 秒内返回结果，超时返回已有结果而非报错。

#### Scenario: Timeout fallback
- **WHEN** 外部 API 超过 8 秒未响应
- **THEN** 系统返回已获取的部分结果或空列表
- **AND** 不向前端抛出 5xx 错误

## GitHub Repository Search

### Requirement: GitHub search endpoint
系统 SHALL 提供 `POST /api/knowledge/github_search` 端点，按关键词和 Star 数检索 GitHub 仓库。

#### Scenario: Keyword search by stars
- **WHEN** 前端发送 `{query: "distributed storage", topic: "big-data", max_results: 6, min_stars: 50}`
- **THEN** 系统调用 GitHub Search API，按 stars 降序排列
- **AND** 返回 `{repos: [{full_name, description, html_url, stars, language, license}]}`

#### Scenario: Empty results or API unavailable
- **WHEN** GitHub API 不可用或超时
- **THEN** 整块不展示（前端隐藏），不影响页面其余部分
