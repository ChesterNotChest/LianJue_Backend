import os
import time
from types import SimpleNamespace

import pytest

from config import ABUTION_CONFIG, LITELLM_MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion


def _pick_graph_name() -> str:
    # Reuse existing graph when configured, fallback to a harmless probe graph name.
    return os.getenv("PTTEST_GRAPH_NAME", "RAG")


def _is_remote_abution(url: str) -> bool:
    text = (url or "").strip().lower()
    if not text:
        return False
    if "localhost" in text or "127.0.0.1" in text:
        return False
    return True


def test_pttest_unit_remote_url_detection():
    assert _is_remote_abution("play.edgerunners.cn:30649") is True
    assert _is_remote_abution("https://example.com") is True
    assert _is_remote_abution("localhost:9996") is False
    assert _is_remote_abution("127.0.0.1:9996") is False


@pytest.mark.remote_db
def test_pttest_integration_remote_graph_list():
    if os.getenv("RUN_REMOTE_DB_TESTS") != "1":
        pytest.skip("Set RUN_REMOTE_DB_TESTS=1 to run remote graph DB integration test.")

    cfg = ABUTION_CONFIG or {}
    abution_url = str(cfg.get("abution_url", ""))
    if not _is_remote_abution(abution_url):
        pytest.skip("ABUTION_CONFIG.abution_url is not remote; skipping remote integration test.")

    graph_name = _pick_graph_name()
    start = time.perf_counter()
    knowlion = KnowLion(LITELLM_MODEL_CONFIGS or {}, graph_name)

    payload = knowlion.gdb_client.list_graph()
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert payload is not None
    assert isinstance(payload, (list, dict))

    # Expose basic telemetry in pytest output for report generation.
    print(f"PTTEST_REMOTE_DB abution_url={abution_url}")
    print(f"PTTEST_REMOTE_DB graph_name={graph_name}")
    print(f"PTTEST_REMOTE_DB payload_type={type(payload).__name__}")
    if isinstance(payload, list):
        print(f"PTTEST_REMOTE_DB graph_count={len(payload)}")
    print(f"PTTEST_REMOTE_DB elapsed_ms={elapsed_ms:.2f}")
