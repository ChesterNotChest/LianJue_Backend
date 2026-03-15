from repositories.graph_repo import get_graph_by_id, create_graph

def create_graph(graphId):
    if not get_graph_by_id(graphId):
        return create_graph(graphId)
    return get_graph_by_id(graphId)


def get_graphId_by_graph_id(graph_id: int):
    graph = get_graph_by_id(graph_id)
    return graph.graphId if graph else None