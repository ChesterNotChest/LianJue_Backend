import os
import json
import time
import uuid
from pathlib import Path

OUTBOX_DIR = Path("./outbox/graphs")
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def enqueue_batch(graph_name: str, batch: list, meta: dict = None) -> str:
    """序列化图数据并保存到 outbox 目录，返回文件路径"""
    meta = meta or {}
    payload = {
        "graph": graph_name,
        "meta": meta,
        "batch": batch,
        "ts": int(time.time())
    }
    fname = f"graph_{graph_name}_{int(time.time())}_{uuid.uuid4().hex}.json"
    path = OUTBOX_DIR / fname
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        return str(path)
    except Exception:
        return ""


def list_outbox() -> list:
    return [str(p) for p in OUTBOX_DIR.iterdir() if p.is_file()]


def read_outbox_file(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def remove_outbox_file(path: str):
    try:
        os.remove(path)
    except Exception:
        pass


def enqueue_graph_creation(graph_name: str, schema: dict, meta: dict = None) -> str:
    """Persist a request to create a graph (schema) into outbox for later replay."""
    meta = meta or {}
    payload = {
        "type": "create_graph",
        "graph": graph_name,
        "meta": meta,
        "schema": schema,
        "ts": int(time.time())
    }
    fname = f"graph_create_{graph_name}_{int(time.time())}_{uuid.uuid4().hex}.json"
    path = OUTBOX_DIR / fname
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        return str(path)
    except Exception:
        return ""
