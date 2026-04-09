from config import MODEL_CONFIGS
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

    knowlion = KnowLion(MODEL_CONFIGS, graph_name=graph_name)
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
