# Bug: 路径网刷新后不匹配已确认路径 — 状态机修复

## 根因
`/api/recommendations?limit=1` 按 `created_at DESC` 取最新 snapshot。
如果用户确认路径后又触发新的推荐生成（新 snapshot 的 status="proposed"），
最新 snapshot 不是 accepted 的那个。前端走到 NO 分支：
`highlightPath = best_path.path`，高亮算法推荐路径而非用户确认路径。

更深层：状态机不闭合。没有保证 accepted snapshot 的排他性，
没有阻止 active plan 期间生成新推荐，没有在 plan 结束时 expire snapshot。

## 修复：完整状态机

```
proposed ──accept──► accepted ──complete/abandon──► expired
                         │
                         └── guard: 禁止生成新推荐
```

### 后端 (snapshot.py)
1. **`expire_latest_snapshot(user_id, syllabus_id)`** — 最新非过期 snapshot → expired
2. **`_get_latest_non_expired_snapshot_id(...)`** — 查询 helper
3. **`accept_recommendation_snapshot_path` staleness guard** — 如果 accept 的不是最新 non-expired snapshot，拒绝并返回最新 snapshot
4. **`list_recommendation_snapshots(include_expired=False)`** — 默认排除 expired

### 后端 (learning_plan.py)
5. **`complete_learning_plan` / `abandon_learning_plan`** — 追加 `expire_latest_snapshot()` 调用

### 后端 (service.py)
6. **`run_recommendation_route_from_payload` guard** — active plan 存在时拒绝生成新推荐 (`error_code: "active_plan_exists"`)

### 前端 (MiniGraphPanel.tsx)
7. **polling**: 无 non-expired snapshot 时清空推荐视图（之前卡在 loading）
8. **handleConfirm**: 解析 response，处理 `stale_snapshot` — 自动加载最新 snapshot
9. **非 accepted snapshot**: 重置 confirmed/acceptedCandidateIndex 状态
