from config import LITELLM_MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion
from repositories.graph_repo import (
    create_graph as create_graph_repo,
    get_graph_by_graphId,
    get_graph_by_id,
    list_graphs as list_graphs_repo,
)


def create_graph(graphId: str):
    """
    `graphId` is the graph name used by the graph database.
    `graph_id` is the local auto-increment primary key in MySQL.
    """
    if graphId is None:
        return None

    graph_name = str(graphId).strip()
    if not graph_name:
        return None

    graph = get_graph_by_graphId(graph_name)
    if graph:
        return graph

    knowlion = KnowLion(LITELLM_MODEL_CONFIGS, graph_name=graph_name)
    knowlion.init_graph()

    return create_graph_repo(graph_name)


def list_graphs_brief_info():
    return [
        {
            "graph_id": getattr(graph, "graph_id", None),
            "graph_name": getattr(graph, "graphId", None),
        }
        for graph in list_graphs_repo()
    ]


def get_graphId_by_graph_id(graph_id: int):
    graph = get_graph_by_id(graph_id)
    return graph.graphId if graph else None


def refresh_graph_cache(graphId: str) -> dict:
    """从 AbutionGraph 全量采集一个 graph 并写入缓存 JSON。静默执行，失败只写日志。"""
    import base64
    import json
    import os
    import ssl
    from datetime import datetime, timezone
    from pathlib import Path

    import urllib3

    # ── load config ──
    from config import ABUTION_CONFIG as _load_abution_config
    cfg = _load_abution_config
    if callable(cfg):
        try:
            cfg = cfg()
        except Exception:
            cfg = {}
    if not isinstance(cfg, dict):
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8")).get("ABUTION_CONFIG") or {}
        else:
            cfg = {}

    if not cfg:
        return {"success": False, "error": "ABUTION_CONFIG not found"}

    raw_url = str(cfg.get("abution_url") or "localhost:9996").strip().rstrip("/")
    base_url = raw_url if raw_url.startswith(("http://", "https://")) else (
        "https" if cfg.get("use_ssl") else "http"
    ) + "://" + raw_url
    rest_url = base_url.rstrip("/") + "/rest"

    if cfg.get("use_ssl") and cfg.get("allow_self_signed"):
        os.environ["PYTHONHTTPSVERIFY"] = "0"
        ssl._create_default_https_context = ssl._create_unverified_context
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ssl_kwargs = {"verify": False}
    elif cfg.get("ssl_ca_cert"):
        os.environ["SSL_CERT_FILE"] = str(cfg.get("ssl_ca_cert"))
        ssl_kwargs = {"verify": cfg["ssl_ca_cert"]}
    else:
        ssl_kwargs = {"verify": True}

    username = str(cfg.get("username") or "abution")
    password = str(cfg.get("password") or "abution")
    auth_value = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {"Authorization": auth_value, "abution-graph-id": graphId, "abution.graphId": graphId}

    try:
        from abutionpy.abution_connector import AbutionConnector
    except ImportError:
        return {"success": False, "error": "abutionpy not installed"}

    try:
        connector = AbutionConnector(rest_url, headers=headers, client_class="requests", **ssl_kwargs)
        # Mandatory: update the underlying requests session (original probe does this)
        client = getattr(connector, "client", None)
        session = getattr(client, "_session", None)
        if session is not None:
            session.headers.update(headers)
            session.trust_env = False
            if "verify" in ssl_kwargs:
                session.verify = ssl_kwargs["verify"]
    except Exception as e:
        return {"success": False, "error": f"AbutionGraph connection failed: {e}"}

    graph = connector.Graph(graphId)
    errors = []

    # Multi-path probe, identical to original probe_abution_rag.py
    probes = {}

    def try_probe(name, fn):
        try:
            probes[name] = {"ok": True, "_raw": fn()}
        except Exception as e:
            errors.append(f"{name}: {e}")
            probes[name] = {"ok": False, "error": str(e)}

    # Vertices — traversal API returns full vertex objects, Gremlin is fallback
    try_probe("traversal_vertices", lambda: graph.V().ToList().exec())
    try_probe("gremlin_vertices", lambda: connector.execute_gremlin("g.V().valueMap(true)", to_objects=True))

    # Edges — traversal returns full edge objects, Gremlin is fallback
    try_probe("traversal_edges", lambda: graph.E().ToList().exec())
    try_probe(
        "gremlin_edges",
        lambda: connector.execute_gremlin(
            "g.E().project('id','label','out','in').by(id()).by(label()).by(outV().id()).by(inV().id())",
            to_objects=True,
        ),
    )

    # Pick first successful vertex probe
    raw_nodes = None
    for key in ("traversal_vertices", "gremlin_vertices"):
        if probes[key].get("ok") and isinstance(probes[key].get("_raw"), list):
            raw_nodes = probes[key]["_raw"]
            break

    raw_edges_raw = None
    for key in ("traversal_edges", "gremlin_edges"):
        if probes[key].get("ok") and isinstance(probes[key].get("_raw"), list):
            raw_edges_raw = probes[key]["_raw"]
            break

    if not raw_nodes or not isinstance(raw_nodes, list):
        return {"success": False, "error": "; ".join(errors) if errors else "no vertex data from any probe"}
    if not raw_edges_raw:
        raw_edges_raw = []

    # ── normalize ──
    nodes = []
    for item in (raw_nodes if isinstance(raw_nodes, list) else []):
        src = item if isinstance(item, dict) else (vars(item) if hasattr(item, "__dict__") else {})
        nid = src.get("vertex") or src.get("id") or src.get("vertexId") or src.get("elementId") or str(abs(hash(repr(item))))
        label = src.get("label") or src.get("_label") or src.get("type") or "entity"
        props = src.get("properties") if isinstance(src.get("properties"), dict) else src
        title = ""
        for k in ("title", "name", "concept", "text", "content"):
            v = props.get(k)
            if isinstance(v, str) and v.strip():
                title = v.strip()
                break
        nodes.append({
            "id": str(nid),
            "title": title or str(nid),
            "group": str(label),
            "meta": {k: v for k, v in props.items()
                     if k not in {"vector", "vectors", "vector_paras", "embedding", "importance"}
                     and isinstance(v, (str, int, float, bool, type(None)))}
            if len(props) > 8 else props,
        })

    edges = []
    for item in (raw_edges_raw if isinstance(raw_edges_raw, list) else []):
        src = item if isinstance(item, dict) else (vars(item) if hasattr(item, "__dict__") else {})
        out_v = src.get("source") or src.get("outV") or src.get("out") or src.get("from")
        in_v = src.get("target") or src.get("inV") or src.get("in") or src.get("to")
        if not out_v or not in_v:
            continue
        label = src.get("label") or src.get("_label") or src.get("type") or "edge"
        edges.append({
            "id": str(src.get("id") or f"{out_v}->{in_v}:{label}"),
            "source": str(out_v),
            "target": str(in_v),
            "type": str(label),
            "directed": True,
        })

    snapshot = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "layout": {"mode": "spiral", "radius": 5200},
        "nodes": nodes,
        "edges": edges,
        "recommendations": [],
    }

    cache_dir = Path(__file__).resolve().parents[1] / "data" / "knowledge_graph"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{graphId.lower()}_probe_full_result.json"
    result = {"target": {"graphId": graphId, "base_url": base_url}, "graphSnapshot": snapshot}
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update DB snapshot_cache_path
    try:
        from schemas.graph import Graph
        from extensions import db
        g = Graph.query.filter_by(graphId=graphId).first()
        if g:
            g.snapshot_cache_path = str(cache_path.relative_to(Path(__file__).resolve().parents[1]))
            db.session.commit()
    except Exception:
        pass

    return {"success": True, "path": str(cache_path), "node_count": len(nodes), "edge_count": len(edges)}


def get_galaxy_version() -> str | None:
    """所有缓存 JSON 中最新 mtime 的 hash，用于前端心跳 diff。"""
    import hashlib
    import os
    from pathlib import Path as _Path

    data_dir = _Path(__file__).resolve().parents[1] / 'data' / 'knowledge_graph'
    if not data_dir.exists():
        return None
    latest = 0
    for f in data_dir.glob('*_full_result.json'):
        try:
            mt = int(os.path.getmtime(f))
            if mt > latest:
                latest = mt
        except Exception:
            pass
    return hashlib.md5(str(latest).encode()).hexdigest()[:12] if latest else None
