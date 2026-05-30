from tasks.personal_recommendation.syllabus_adapter import syllabus_json_to_learning_tree


def test_map_list_nodes():
    syllabus = [
        {"id": "n1", "title": "Intro", "prerequisites": [], "outcomes": ["a"], "duration": 2},
        {"id": "n2", "title": "Next", "prerequisites": ["n1"], "outcomes": ["b"], "duration": 3, "difficulty": 2},
    ]
    learning_tree = syllabus_json_to_learning_tree(syllabus)
    assert isinstance(learning_tree, dict)
    assert "n1" in learning_tree and "n2" in learning_tree
    assert learning_tree["n1"]["outcomes"] == ["a"]
    assert learning_tree["n2"]["prerequisites"] == ["n1"]


def test_map_dict_nodes():
    syllabus = {
        "n1": {"title": "A", "outcomes": ["x"]},
        "n2": {"title": "B", "prerequisites": ["n1"], "learning_time_est": 1.5},
    }
    learning_tree = syllabus_json_to_learning_tree(syllabus)
    assert isinstance(learning_tree, dict)
    assert learning_tree["n2"]["prerequisites"] == ["n1"]
    assert learning_tree["n2"]["learning_time_est"] == 1.5


def test_unknown_shape_returns_empty():
    assert syllabus_json_to_learning_tree(None) == {}
    assert syllabus_json_to_learning_tree({"foo": "bar"}) == {}


def test_map_dict_nodes_normalizes_string_and_invalid_numbers():
    syllabus = {
        "n1": {"title": "A", "prerequisites": "root", "outcomes": "skill_a", "duration": "oops", "difficulty": "bad"},
    }
    learning_tree = syllabus_json_to_learning_tree(syllabus)
    assert learning_tree["n1"]["prerequisites"] == ["root"]
    assert learning_tree["n1"]["outcomes"] == ["skill_a"]
    assert learning_tree["n1"]["learning_time_est"] == 1.0
    assert learning_tree["n1"]["difficulty"] == 1.0


def test_syllabus_adapter_expands_nested_chapters_sections_topics():
    syllabus = {
        "chapters": [
            {
                "id": "chapter_1",
                "title": "Machine Learning",
                "sections": [
                    {
                        "id": "section_1",
                        "title": "Supervised Learning",
                        "topics": [
                            {"id": "topic_1", "title": "Linear Regression", "outcomes": ["linear_regression"]},
                        ],
                    }
                ],
            }
        ]
    }

    learning_tree = syllabus_json_to_learning_tree(syllabus)

    assert set(learning_tree) == {"chapter_1", "section_1", "topic_1"}
    assert learning_tree["section_1"]["prerequisites"] == ["chapter_1"]
    assert learning_tree["topic_1"]["prerequisites"] == ["section_1"]
    assert learning_tree["chapter_1"]["outcomes"] == ["Machine Learning"]


def test_syllabus_adapter_preserves_explicit_prerequisites():
    syllabus = {
        "chapters": [
            {
                "id": "chapter_1",
                "title": "Chapter",
                "sections": [
                    {"id": "section_1", "title": "Section", "prerequisites": ["external"]},
                ],
            }
        ]
    }

    learning_tree = syllabus_json_to_learning_tree(syllabus)

    assert learning_tree["section_1"]["prerequisites"] == ["external"]


def test_syllabus_adapter_uses_title_as_fallback_outcome():
    learning_tree = syllabus_json_to_learning_tree([{"id": "n1", "title": "Directory"}])

    assert learning_tree["n1"]["outcomes"] == ["Directory"]
