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


def test_syllabus_adapter_maps_period_as_semantic_weekly_knowledge_nodes():
    syllabus = {
        "title": "大数据概论",
        "period": [
            {
                "week_index": "5",
                "content": "大数据存储与管理：分布式文件系统及主流技术HDFS",
                "enhanced_content": "HDFS 是 Hadoop 的分布式文件系统。",
                "importance": "high",
            },
            {
                "week_index": "6",
                "content": "大数据存储与管理：分布式数据库中典型技术HBase",
                "enhanced_content": "HBase 是高可靠、高性能、面向列、可伸缩的分布式数据库。",
                "importance": "high",
            },
        ],
    }

    learning_tree = syllabus_json_to_learning_tree(syllabus)

    assert learning_tree
    assert "week_5" not in learning_tree
    assert "week_6" not in learning_tree
    hbase_node_id = next(node_id for node_id, node in learning_tree.items() if "HBase" in node["title"])
    hbase_node = learning_tree[hbase_node_id]
    assert hbase_node["node_source"] == "syllabus_period"
    assert hbase_node["decomposition_method"] == "period_anchor"
    assert hbase_node["reliability"] == 0.8
    assert hbase_node["week_index"] == "6"
    assert hbase_node["importance"] == "high"
    assert hbase_node["difficulty"] == 3.0
    assert any("HBase" in outcome for outcome in hbase_node["outcomes"])
    assert hbase_node["prerequisites"]
    assert hbase_node["prerequisites"][0] in learning_tree
    concept_nodes = [node for node in learning_tree.values() if node.get("node_source") == "syllabus_period_concept"]
    assert any(node["title"] == "HBase" for node in concept_nodes)


def test_syllabus_adapter_period_fallback_is_marked_when_no_semantic_title():
    learning_tree = syllabus_json_to_learning_tree({"period": [{"week_index": "1"}]})

    assert "period_1" in learning_tree
    assert learning_tree["period_1"]["node_source"] == "syllabus_period_fallback"
    assert learning_tree["period_1"]["decomposition_method"] == "period_anchor"
    assert learning_tree["period_1"]["fallback_tag"] == "period_title_fallback"


def test_syllabus_adapter_decomposes_period_into_concept_nodes_for_recommendation():
    syllabus = {
        "period": [
            {
                "week_index": "6",
                "content": "大数据存储与管理：分布式数据库中典型技术HBase",
                "enhanced_content": "HBase 运行在 HDFS 之上，涉及 RowKey 设计、Region 划分、预分区和热点规避。",
                "importance": "high",
            }
        ]
    }

    learning_tree = syllabus_json_to_learning_tree(syllabus)
    concept_nodes = {
        node["title"]: (node_id, node)
        for node_id, node in learning_tree.items()
        if node.get("node_source") == "syllabus_period_concept"
    }

    assert {"HBase", "HDFS", "RowKey", "Region", "预分区", "热点规避"}.issubset(set(concept_nodes))
    rowkey_id, rowkey = concept_nodes["RowKey"]
    assert rowkey["source_period"]["week_index"] == "6"
    assert rowkey["confidence"] >= 0.75
    assert rowkey["implied"] is False
    assert rowkey["decomposition_method"] == "rule_fallback"
    assert rowkey["fallback_tag"] == "period_concept_rule_fallback"
    assert rowkey["reliability"] == 0.55
    assert "RowKey" in rowkey["outcomes"]
    assert any(prerequisite in learning_tree for prerequisite in rowkey["prerequisites"])
    assert rowkey_id in learning_tree


def test_syllabus_adapter_adds_low_confidence_implied_hbase_concepts():
    syllabus = {
        "period": [
            {
                "week_index": "6",
                "content": "大数据存储与管理：分布式数据库中典型技术HBase",
                "enhanced_content": "HBase 是高可靠、高性能、面向列、可伸缩的分布式数据库。",
            }
        ]
    }

    learning_tree = syllabus_json_to_learning_tree(syllabus)
    concept_nodes = [
        node
        for node in learning_tree.values()
        if node.get("node_source") == "syllabus_period_concept"
    ]
    rowkey = next(node for node in concept_nodes if node["title"] == "RowKey")

    assert rowkey["implied"] is True
    assert rowkey["confidence"] == 0.55
    assert rowkey["matched_by"] == ["implied_by:HBase"]
    assert rowkey["decomposition_method"] == "rule_fallback"
    assert rowkey["fallback_tag"] == "period_concept_rule_implied_fallback"
    assert rowkey["reliability"] == 0.35


def test_syllabus_adapter_uses_agent_concepts_when_injected():
    syllabus = {
        "period": [
            {
                "week_index": "6",
                "content": "大数据存储与管理：分布式数据库中典型技术HBase",
                "enhanced_content": "HBase 涉及 RowKey、Region 和热点规避。",
            }
        ]
    }

    def fake_decomposer(payload):
        return {
            "concepts": [
                {
                    "title": "HBase",
                    "source_period": {"week_index": "6", "title": "HBase"},
                    "confidence": 0.9,
                    "matched_by": ["period.enhanced_content"],
                },
                {
                    "title": "RowKey",
                    "source_period": {"week_index": "6", "title": "HBase"},
                    "prerequisite_titles": ["HBase"],
                    "confidence": 0.86,
                    "matched_by": ["rag.paragraph"],
                    "reason": "RowKey controls HBase row access.",
                },
            ],
            "edges": [{"source_title": "HBase", "target_title": "RowKey", "confidence": 0.8}],
        }

    learning_tree = syllabus_json_to_learning_tree(syllabus, concept_decomposer=fake_decomposer)
    concept_nodes = {
        node["title"]: node
        for node in learning_tree.values()
        if node.get("node_source") == "syllabus_period_concept"
    }

    assert set(concept_nodes) == {"HBase", "RowKey"}
    assert concept_nodes["RowKey"]["decomposition_method"] == "agent"
    assert concept_nodes["RowKey"]["fallback_tag"] == ""
    assert concept_nodes["RowKey"]["reliability"] == 0.86
    assert concept_nodes["RowKey"]["reason"] == "RowKey controls HBase row access."
    assert any(learning_tree[prerequisite]["title"] == "HBase" for prerequisite in concept_nodes["RowKey"]["prerequisites"])
