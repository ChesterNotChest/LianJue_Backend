from tasks.personal_recommendation.graph_builder import build_recommendation_graph_tree


def test_graph_builder_does_not_mutate_learning_tree():
    tree = {
        "n1": {"title": "A", "prerequisites": [], "outcomes": ["a"]},
        "n2": {"title": "B", "prerequisites": [], "outcomes": ["b"]},
    }
    original = {key: dict(value) for key, value in tree.items()}

    result = build_recommendation_graph_tree(
        tree,
        rag_overlay={"temporary_edges": [{"source": "n1", "target": "n2"}]},
    )

    assert tree == original
    assert result["n2"]["prerequisites"] == ["n1"]


def test_graph_builder_adds_rag_temporary_edges_as_soft_edges():
    tree = {
        "n1": {"title": "A", "prerequisites": [], "outcomes": ["a"]},
        "n2": {"title": "B", "prerequisites": [], "outcomes": ["b"]},
    }

    result = build_recommendation_graph_tree(
        tree,
        rag_overlay={"temporary_edges": [{"source": "n1", "target": "n2"}]},
    )

    assert "n1" in result["n2"]["prerequisites"]
    assert result["n2"]["edge_sources"]["n1"] == "rag"
    assert result["n2"]["edge_confidence"]["n1"] < 1.0


def test_graph_builder_marks_syllabus_edges_as_high_confidence():
    tree = {
        "n1": {"title": "A", "prerequisites": [], "outcomes": ["a"]},
        "n2": {"title": "B", "prerequisites": ["n1"], "outcomes": ["b"]},
    }

    result = build_recommendation_graph_tree(tree)

    assert result["n2"]["edge_sources"]["n1"] == "syllabus"
    assert result["n2"]["edge_confidence"]["n1"] == 1.0


def test_graph_builder_applies_study_graph_state_as_readonly_annotations():
    tree = {
        "n1": {"title": "A", "prerequisites": [], "outcomes": ["a"]},
        "n2": {"title": "B", "prerequisites": [], "outcomes": ["b"]},
    }

    result = build_recommendation_graph_tree(
        tree,
        study_graph_state={"completed_node_ids": ["n1"], "blocked_node_ids": ["n2"]},
    )

    assert result["n1"]["study_graph_state"] == "completed"
    assert result["n2"]["study_graph_state"] == "blocked"
