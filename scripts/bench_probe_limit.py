"""Compare graph probe speed: with vs without limit."""
import time, sys, json, base64, os, ssl
from pathlib import Path
sys.path.insert(0, ".")

import urllib3

# Load config (same as graph_task.refresh_graph_cache)
from config import ABUTION_CONFIG as _cfg
cfg = _cfg
if callable(cfg):
    try: cfg = cfg()
    except: cfg = {}
if not isinstance(cfg, dict):
    p = Path(__file__).resolve().parents[1] / "config.json"
    if p.exists():
        cfg = json.loads(p.read_text()).get("ABUTION_CONFIG") or {}
    else: cfg = {}

raw_url = str(cfg.get("abution_url") or "localhost:9996").strip().rstrip("/")
base_url = raw_url if raw_url.startswith(("http://","https://")) else ("https" if cfg.get("use_ssl") else "http") + "://" + raw_url
rest_url = base_url + "/rest"

if cfg.get("use_ssl") and cfg.get("allow_self_signed"):
    os.environ["PYTHONHTTPSVERIFY"] = "0"
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    sl = {"verify": False}
elif cfg.get("ssl_ca_cert"):
    sl = {"verify": cfg["ssl_ca_cert"]}
else:
    sl = {"verify": True}

auth = "Basic " + base64.b64encode(f"{cfg.get('username','abution')}:{cfg.get('password','abution')}".encode()).decode()
hdrs = {"Authorization": auth, "abution-graph-id": "RAG", "abution.graphId": "RAG"}

from abutionpy.abution_connector import AbutionConnector
conn = AbutionConnector(rest_url, headers=hdrs, client_class="requests", **sl)
cl = getattr(conn, "client", None)
se = getattr(cl, "_session", None)
if se: se.headers.update(hdrs); se.trust_env = False; se.verify = sl.get("verify", True)
g = conn.Graph("RAG")

# Test 1: traversal vertex query, NO limit
t0 = time.time()
try:
    r1 = g.V().ToList().exec()
    t1 = time.time() - t0
    print(f"NO  limit: {t1:.1f}s  count={len(r1) if isinstance(r1, list) else r1}")
except Exception as e:
    t1 = time.time() - t0
    print(f"NO  limit: {t1:.1f}s  ERROR: {e}")

# Test 2: traversal vertex query, WITH limit
t0 = time.time()
try:
    r2 = g.V().Limit(20000).ToList().exec()
    t2 = time.time() - t0
    print(f"WITH limit: {t2:.1f}s  count={len(r2) if isinstance(r2, list) else r2}")
except Exception as e:
    t2 = time.time() - t0
    print(f"WITH limit: {t2:.1f}s  ERROR: {e}")

print(f"\nRatio: {t2/t1:.1%}" if t1 else "")
