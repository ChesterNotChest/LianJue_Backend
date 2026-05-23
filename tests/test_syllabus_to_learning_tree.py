import json
import os

from tasks.syllabus_to_learning_tree import syllabus_json_to_learning_tree


def test_map_list_nodes():
    syllabus = [
        {"id": "n1", "title": "Intro", "prerequisites": [], "outcomes": ["a"], "duration": 2},
        {"id": "n2", "title": "Next", "prerequisites": ["n1"], "outcomes": ["b"], "duration": 3, "difficulty": 2},
    ]
    lt = syllabus_json_to_learning_tree(syllabus)
    assert isinstance(lt, dict)
    assert "n1" in lt and "n2" in lt
    assert lt["n1"]["outcomes"] == ["a"]
    assert lt["n2"]["prerequisites"] == ["n1"]


def test_map_dict_nodes():
    syllabus = {
        "n1": {"title": "A", "outcomes": ["x"]},
        "n2": {"title": "B", "prerequisites": ["n1"], "learning_time_est": 1.5},
    }
    lt = syllabus_json_to_learning_tree(syllabus)
    assert isinstance(lt, dict)
    assert lt["n2"]["prerequisites"] == ["n1"]
    assert lt["n2"]["learning_time_est"] == 1.5


def test_unknown_shape_returns_empty():
    assert syllabus_json_to_learning_tree(None) == {}
    assert syllabus_json_to_learning_tree({"foo": "bar"}) == {}
