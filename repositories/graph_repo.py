from ..extensions import db
from ..schemas.graph import Graph

def get_graph_by_id(graph_id):
    '''
    此处graph_id是数据库自增id，graphId是面向图数据库的graph名称。
    '''
    return Graph.query.filter_by(graph_id=graph_id).first()

def get_graph_by_graphId(graphId):
    '''
    此处graphId是面向图数据库的graph名称，graph_id是数据库自增id。
    '''
    return Graph.query.filter_by(graphId=graphId).first()

def create_graph(graphId):
    new_graph = Graph(graphId=graphId)
    db.session.add(new_graph)
    db.session.commit()
    return new_graph

def remove_graph(graph_id):
    graph = get_graph_by_id(graph_id)
    if graph:
        db.session.delete(graph)
        db.session.commit()
        return True
    return False