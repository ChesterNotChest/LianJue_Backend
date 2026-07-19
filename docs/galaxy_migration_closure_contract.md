# Galaxy Migration Closure Contract

本文档收口银河迁移的全部剩余实现。目标是让知识银河在联觉首页正确渲染，包括 ID namespace、
学科节点、Para 隐藏管线、Subject2Doc 边精确性、邻域详情面板、星云高亮对齐，以及
心跳驱动的自动差异刷新。

## 目标

- 学科节点正确渲染在银河中心位置，点击后边线精准连接所属 Doc 节点。
- Para 节点作为隐藏证据层，通过 Doc2Entity 虚拟边和 relatedParas 注入参与详情面板。
- 不同 graph 的节点 ID 通过 namespace 前缀保证唯一，无 React key 冲突。
- 选中节点后右侧详情面板展示邻域跳转按钮和相关段落。
- 星云高亮云团与被匹配节点球体坐标严格对齐。
- 总 Agent 操作后前端心跳自动检测数据版本变化，差异时重拉对应数据。

## 阶段 1：后端给节点注入 graphId

**文件**：`blueprint/user_api.py::_read_snapshot`

**问题**：前端 `buildSubjectGraphSnapshot` 依赖 `node.meta.graphId` 做 namespace 分组和
Subject2Doc 边过滤。`_read_snapshot` 当前只注入了顶层 `syllabusList`，未给每个节点 meta 标注 graphId，
全空时 namespace 静默失效。

**函数收口**：
```python
def _read_snapshot(name: str) -> dict | None:
    """返回 snapshot dict，每个节点 meta 注入 graphId。"""
    cache_path = _resolve_cache_path(name)
    if not cache_path: return None
    raw = json.loads(cache_path.read_text(encoding='utf-8'))
    if isinstance(raw, dict) and 'graphSnapshot' in raw:
        raw = raw['graphSnapshot']
    if isinstance(raw, dict) and 'nodes' in raw:
        raw = dict(raw)
        raw['syllabusList'] = _build_syllabus_list(name)
        for node in raw.get('nodes', []):
            if isinstance(node, dict):
                node.setdefault('meta', {})['graphId'] = name
        return raw
    return None
```

**验证**：`curl /api/knowledge-graph/snapshot?graph_ids=RAG`，返回的每个节点 `meta.graphId` === `"RAG"`。

---

## 阶段 2：Subject2Doc 边精确性

**文件**：`src/api/knowledgeGraphApi.ts::buildSubjectGraphSnapshot`

**问题**：当前每个 Subject 连到所有 Doc (`visibleNodes.filter(n => n.group === "Doc")`)，
不区分 graph 归属。大数据概论的学科节点会连到 Algorithm graph 的无关 Doc。

**函数收口**：
- 新增常量：无。
- 从 `syllabusListPerGraph` 构建逆向映射 `subjectGraphIds: Map<string, Set<string>>`（subject key → 所属 graphId 集合）。
- Subject2Doc 边创建时增加 `allowedGraphs.has(doc.meta.graphId)` 过滤。

```typescript
// 新增：建构 inverse map
const subjectGraphIds = new Map<string, Set<string>>();
for (const [gid, syllabi] of Object.entries(syllabusListPerGraph)) {
  for (const s of syllabi) {
    const key = `syllabus:${s.syllabus_id}`;
    const set = subjectGraphIds.get(key) ?? new Set();
    set.add(gid);
    subjectGraphIds.set(key, set);
  }
}

// 修改 Subject2Doc 边创建
for (const [nodeId, info] of subjectMap.entries()) {
  subjectNodes.push({ ... });
  const allowedGraphs = subjectGraphIds.get(nodeId) ?? new Set();
  for (const doc of visibleNodes.filter(n => n.group === "Doc")) {
    if (allowedGraphs.has(String(doc.meta?.graphId ?? ""))) {
      subjectEdges.push({
        id: `sub2doc:${edgeIdx++}`, source: nodeId, target: doc.id,
        type: "Subject2Doc", directed: true, weight: 2.8,
      });
    }
  }
}
```

**验证**：浏览器中点击"大数据概论"学科节点，边线仅连到 RAG graph 下的 Doc；点击"学科18"，
边线仅连到 Algorithm graph 下的 Doc。

---

## 阶段 3：心跳版本端点

**文件**：`blueprint/user_api.py` 新增 `GET /api/status/version`；
`tasks/graph_task.py` 新增 `get_galaxy_version()`；
`tasks/study_graph/service.py` 暴露 `get_tree_updated_at()`。

**目的**：前端心跳轮询用轻量端点获取四维版本摘要，有差异时触发对应数据重拉。
不创建新 SSE 通道，不复用 `tool_status_events`。

**常量**：无新增常量定义。

**端点**：
```python
@bp.route('/status/version', methods=['GET'])
def status_version_api():
    user_id = request.args.get('user_id', type=int)
    syllabus_id = request.args.get('syllabus_id', type=int)

    version = {
        'galaxy_version': get_galaxy_version(),           # max(generatedAt) hash
        'study_graph_version': None,
        'plan_version': None,
        'recommendation_version': None,
    }

    if user_id and syllabus_id:
        from tasks.study_graph.service import get_tree_updated_at
        tree_ts = get_tree_updated_at(user_id, syllabus_id)
        if tree_ts is not None:
            version['study_graph_version'] = str(tree_ts)

        from tasks.personal_recommendation_task import get_active_learning_plan
        plan = get_active_learning_plan(user_id, syllabus_id)
        if plan:
            version['plan_version'] = plan.get('plan_id') or 'active'

        from tasks.personal_recommendation.snapshot import list_recommendation_snapshots
        snapshots = list_recommendation_snapshots(user_id, syllabus_id)
        if snapshots:
            version['recommendation_version'] = (snapshots[0].get('recommendation_id') or '')

    return jsonify({'success': True, 'version': version})
```

**`get_galaxy_version()`**（`graph_task.py`）：
```python
def get_galaxy_version() -> str | None:
    """Hash of most recent cache file mtime across all graphs."""
    import hashlib, os
    data_dir = Path(__file__).resolve().parents[1] / 'data' / 'knowledge_graph'
    if not data_dir.exists(): return None
    latest = 0
    for f in data_dir.glob('*_full_result.json'):
        mt = int(os.path.getmtime(f))
        if mt > latest: latest = mt
    return hashlib.md5(str(latest).encode()).hexdigest()[:12] if latest else None
```

**验证**：`curl /api/status/version` 返回 `{"success":true,"version":{"galaxy_version":"abc123",...}}`。

---

## 阶段 4：前端心跳 Hook

**文件**：`src/hooks/useHeartbeat.ts`（新文件）

**目的**：拨测 `/api/status/version`，差异时触发回调，300s 无变化自动停止。

**接口**：
```typescript
interface VersionState {
  galaxy_version: string | null;
  study_graph_version: string | null;
  plan_version: string | null;
  recommendation_version: string | null;
}

function useHeartbeat(
  userId: number | undefined,
  syllabusId: number | undefined,
  active: boolean,               // SSE 活跃时启用
  onChange: (changed: Set<'galaxy' | 'study_graph' | 'plan' | 'recommendation'>) => void,
  intervalMs?: number,           // 默认 5000
  idleTimeoutMs?: number,        // 默认 300000
): void
```

**内部逻辑**：
1. `active === true` 时启动 5s 定时器。
2. 每次 tick 调用 `fetch(apiUrl('/api/status/version?...'))`。
3. 与上次 `VersionState` 逐字段 diff，差异项传给 `onChange`。
4. 有变化 → 重置 idle 计时器；无变化 → 累计 idle。
5. idle 超过 300s → `clearInterval` 停止。
6. `active` 变 false 或组件卸载 → 停止。

**验证**：在 `SubjectOverview` 中 `console.log` 回调，总 Agent 操作后心跳触发 `onChange`。

---

## 阶段 5：集成心跳到首页

**文件**：`src/pages/SubjectOverview.tsx`

**目的**：银河首页监听心跳差异，对应重拉数据。

**收口**：
```typescript
const handleVersionChange = useCallback((changed: Set<string>) => {
  if (changed.has('galaxy')) {
    // 重拉 galaxy snapshot
    fetchGraphSnapshot(graphIds).then(setSnapshot);
  }
  if (changed.has('study_graph')) {
    // 重拉终生学习图谱
    fetch(apiUrl(`/api/study_graph/detail?user_id=${student?.userId}`))
      .then(r => r.json()).then(d => { if (d.success) ... });
  }
}, [graphIds, student]);

useHeartbeat(student?.userId, undefined, !!snapshot, handleVersionChange);
```

**验证**：总 Agent 完成学习操作后，心跳检测 `study_graph_version` 变化 → 左栏 mini 学习图自动刷新 → 星云高亮更新。

---

## 验收标准

- `curl /api/knowledge-graph/snapshot?graph_ids=RAG` 每个节点 meta 含 `graphId: "RAG"`。
- 浏览器 Console 无 `Encountered two children with the same key`。点击学科节点，边线精准指向所属 graph 的 Doc。
- 右侧面板选中节点后有邻域按钮和相关段落。
- 星云高亮云团中心与被匹配节点球体重合。
- `curl /api/status/version` 返回四维版本。
- 总 Agent 操作后 5s 内前端心跳检测到版本变化并触发重拉。
- 300s 无变化后心跳停止。
- `npm run build` 通过，无 TypeScript 错误。
