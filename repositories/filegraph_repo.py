from extensions import db
from schemas.filegraph import FileGraph

def add_binding(file_id, graph_id):
    new_binding = FileGraph(file_id=file_id, graph_id=graph_id)
    db.session.add(new_binding)
    db.session.commit()
    return new_binding

def remove_binding(file_id, graph_id):
    binding = FileGraph.query.filter_by(file_id=file_id, graph_id=graph_id).first()
    if binding:
        db.session.delete(binding)
        db.session.commit()
        return True
    return False

def get_bindings_by_file_id(file_id):
    return FileGraph.query.filter_by(file_id=file_id).all()

def get_bindings_by_graph_id(graph_id):
    return FileGraph.query.filter_by(graph_id=graph_id).all()

def list_files_by_graph(graph_id):
    bindings = get_bindings_by_graph_id(graph_id)
    return [binding.file_id for binding in bindings]

def list_graphs_by_file(file_id):
    bindings = get_bindings_by_file_id(file_id)
    return [binding.graph_id for binding in bindings]