from extensions import db
from schemas.syllabusgraph import SyllabusGraph


def create_syllabus_graph(syllabus_id: int, graph_id: int):
    """Create an association between a syllabus and a graph."""
    binding = SyllabusGraph(syllabus_id=syllabus_id, graph_id=graph_id)
    db.session.add(binding)
    db.session.commit()
    return binding


def remove_syllabus_graph(syllabus_id: int = None, graph_id: int = None):
    """Remove associations matching syllabus_id and/or graph_id. If both provided, remove the exact binding."""
    q = SyllabusGraph.query
    if syllabus_id is not None:
        q = q.filter_by(syllabus_id=syllabus_id)
    if graph_id is not None:
        q = q.filter_by(graph_id=graph_id)
    items = q.all()
    if not items:
        return 0
    count = 0
    for it in items:
        db.session.delete(it)
        count += 1
    db.session.commit()
    return count


def get_syllabus_graph_by_id(id: int):
    return SyllabusGraph.query.get(id)


def list_graphs_by_syllabus(syllabus_id: int):
    rows = SyllabusGraph.query.filter_by(syllabus_id=syllabus_id).all()
    return [r.graph_id for r in rows]


def list_syllabi_by_graph(graph_id: int):
    rows = SyllabusGraph.query.filter_by(graph_id=graph_id).all()
    return [r.syllabus_id for r in rows]
