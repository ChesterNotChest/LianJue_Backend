from types import SimpleNamespace
from unittest.mock import patch

from utils.job_checker import JobChecker


class FakeConnector:
    def __init__(self, remote_names=None, schema_names=None):
        self.remote_names = set(remote_names or [])
        self.schema_names = set(schema_names or [])

    def list_graph(self):
        return [{"graphId": name} for name in sorted(self.remote_names)]

    def get_schema(self, graph_name):
        if graph_name in self.schema_names:
            return {"graphId": graph_name, "schema": {}}
        raise RuntimeError(f"graph not found: {graph_name}")


class FakeKnowLion:
    remote_names = set()
    schema_names = set()
    init_calls = []

    def __init__(self, model_configs, graph_name):
        self.graph_name = graph_name
        self.gdb_client = FakeConnector(
            remote_names=self.__class__.remote_names,
            schema_names=self.__class__.schema_names,
        )

    def init_graph(self):
        self.__class__.init_calls.append(self.graph_name)


def setup_function():
    FakeKnowLion.remote_names = set()
    FakeKnowLion.schema_names = set()
    FakeKnowLion.init_calls = []


def test_extract_remote_graph_names_handles_nested_payloads():
    checker = JobChecker()
    payload = {
        "data": [
            {"graphId": "graph_a"},
            {"graph_name": "graph_b"},
            {"items": [{"name": "graph_c"}]},
        ]
    }

    names = checker._extract_remote_graph_names(payload)

    assert names == {"graph_a", "graph_b", "graph_c"}


def test_ensure_remote_graphs_exist_only_initializes_missing_graphs():
    checker = JobChecker()
    FakeKnowLion.remote_names = {"existing_graph"}
    FakeKnowLion.schema_names = {"existing_graph"}

    local_graphs = [
        SimpleNamespace(graphId="existing_graph"),
        SimpleNamespace(graphId="missing_graph"),
    ]

    with patch("utils.job_checker.list_local_graphs", return_value=local_graphs), patch(
        "utils.job_checker.KnowLion", FakeKnowLion
    ):
        checker._ensure_remote_graphs_exist()

    assert FakeKnowLion.init_calls == ["missing_graph"]


def test_ensure_remote_graphs_exist_skips_when_remote_listing_fails():
    checker = JobChecker()

    class FailingKnowLion:
        init_calls = []

        def __init__(self, model_configs, graph_name):
            self.graph_name = graph_name
            self.gdb_client = SimpleNamespace(
                list_graph=lambda: (_ for _ in ()).throw(RuntimeError("timeout"))
            )

        def init_graph(self):
            self.__class__.init_calls.append(self.graph_name)

    local_graphs = [SimpleNamespace(graphId="missing_graph")]

    with patch("utils.job_checker.list_local_graphs", return_value=local_graphs), patch(
        "utils.job_checker.KnowLion", FailingKnowLion
    ):
        checker._ensure_remote_graphs_exist()

    assert FailingKnowLion.init_calls == []
