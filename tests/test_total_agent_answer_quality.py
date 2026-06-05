from __future__ import annotations

from tasks.total_agent import agent_tools as tools
from tasks.total_agent.agent_contracts import (
    ACTION_OFFER_PRACTICE_OR_RESOURCE,
    INTENT_ANSWER_LEARNING_QUESTION,
    QA_ANSWER_STYLE_CONCISE,
    QA_ANSWER_STYLE_DETAILED,
    QA_NEXT_ACTION_CONTINUE_CURRENT_STEP,
    QA_NEXT_ACTION_OFFER_PRACTICE,
    QA_QUESTION_TYPE_CONCEPT,
    QA_QUESTION_TYPE_LEARNING_STRATEGY,
    QA_TONE_ENCOURAGING,
    QA_TONE_PRAGMATIC,
    QA_WARNING_LOW_RELEVANCE_EVIDENCE,
    QA_WARNING_PROFILE_WEAK_POINTS_FILTERED,
    TOOL_ANSWER_LEARNING_QUESTION,
)


def _state(message: str, **payload_extra):
    payload = {
        "user_id": 76,
        "syllabus_id": 29,
        "message": message,
        "mock_evidence": [
            {
                "title": "HBase RowKey 热点",
                "summary": "单调递增 RowKey 会让写入集中到少数 Region。",
                "source": "RAG",
                "score": 0.9,
            }
        ],
        **payload_extra,
    }
    total_context = {
        "active_plan": {"plan_id": "plan_hbase", "status": "active"},
        "next_task": {
            "step_id": "step_hbase_base",
            "title": "HBase 基础",
            "status": "active",
            "outcomes": ["RowKey 热点", "预分区"],
        },
        "profile_summary": {
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": [
                "RowKey 热点",
                "预分区",
                "大数据感知与获取涉及数据的来源与类型",
            ],
        },
        "study_graph_state": {
            "weak_node_ids": ["RowKey 热点", "Region 划分"],
            "mastered_node_ids": [],
        },
        "session_context": tools.build_session_context(payload),
    }
    return {"payload": payload, "total_context": total_context, "tool_trace": [], "tool_status_events": []}


def test_classify_learning_question_strategy_beats_concept():
    result = tools.classify_learning_question("我下一步应该怎么学习 RowKey 热点，为什么会这样？")

    assert result["question_type"] == QA_QUESTION_TYPE_LEARNING_STRATEGY
    assert "asks_next_step" in result["reason_codes"]


def test_answer_learning_question_strategy_uses_active_plan_next_task():
    state = _state("我下一步应该怎么学习 HBase RowKey 热点规避？")
    state["learning_evidence_result"] = tools.retrieve_learning_evidence(state)

    result = tools.answer_learning_question(state)
    answer = result["answer"]

    assert result["success"] is True
    assert answer["question_type"] == QA_QUESTION_TYPE_LEARNING_STRATEGY
    assert "HBase 基础" in answer["text"]
    assert "RowKey 热点" in answer["relevant_weak_points"]
    assert "大数据感知与获取涉及数据的来源与类型" in answer["filtered_weak_points"]
    assert QA_WARNING_PROFILE_WEAK_POINTS_FILTERED in answer["warnings"]
    assert result["plan_mutation"] is False
    assert result["resource_generation"] is False
    assert {item["action"] for item in answer["next_actions"]} >= {
        QA_NEXT_ACTION_CONTINUE_CURRENT_STEP,
        QA_NEXT_ACTION_OFFER_PRACTICE,
    }


def test_answer_learning_question_returns_valid_structured_payload():
    state = _state("为什么 HBase RowKey 会出现热点？")
    state["learning_evidence_result"] = tools.retrieve_learning_evidence(state)
    result = tools.answer_learning_question(state)

    validation = tools.validate_answer_payload(result["answer"])

    assert validation["success"] is True
    assert validation["answer"]["text"]
    assert validation["answer"]["key_points"]
    assert 0 <= validation["answer"]["confidence"] <= 1


def test_answer_learning_question_concept_keeps_rowkey_explanation():
    state = _state("为什么 HBase RowKey 会出现热点？")
    state["learning_evidence_result"] = tools.retrieve_learning_evidence(state)

    answer = tools.answer_learning_question(state)["answer"]

    assert answer["question_type"] == QA_QUESTION_TYPE_CONCEPT
    assert "单调递增" in answer["text"]
    assert "大数据感知与获取" not in answer["text"]


def test_answer_learning_question_uses_session_context_for_pronoun():
    state = _state(
        "这个为什么会热点？",
        conversation_history=[
            {"role": "user", "content": "我在看 HBase RowKey 设计。"},
            {"role": "assistant", "content": "当前建议先完成 HBase 基础。"},
        ],
    )
    state["total_context"]["session_context"] = tools.build_session_context(state["payload"])
    state["learning_evidence_result"] = tools.retrieve_learning_evidence(state)

    answer = tools.answer_learning_question(state)["answer"]

    assert answer["session_context_used"] is True
    assert "RowKey" in " ".join(state["total_context"]["session_context"]["topic_hints"])


def test_retrieve_learning_evidence_expands_query_with_plan_and_weak_nodes(monkeypatch):
    captured = {}

    def fake_search_tool(query, graph_name, top_k):
        captured["query"] = query
        return {
            "results": [
                {
                    "title": "RowKey 热点",
                    "summary": "RowKey 热点和 Region 写入集中有关。",
                    "score": 0.8,
                }
            ]
        }

    monkeypatch.setattr(tools, "search_tool", fake_search_tool)
    state = _state("这个为什么会热点？", graph_name="RAG")
    state["payload"].pop("mock_evidence", None)

    result = tools.retrieve_learning_evidence(state)

    assert result["success"] is True
    assert "RowKey" in captured["query"]
    assert "HBase 基础" in result["retrieval_query"]


def test_retrieve_learning_evidence_uses_session_topic_hints_not_full_history(monkeypatch):
    captured = {}
    long_history = "背景材料" * 200

    def fake_search_tool(query, graph_name, top_k):
        captured["query"] = query
        return {"results": [{"title": "RowKey", "summary": "RowKey 热点。", "score": 0.8}]}

    monkeypatch.setattr(tools, "search_tool", fake_search_tool)
    state = _state(
        "这个为什么会热点？",
        graph_name="RAG",
        conversation_history=[
            {"role": "user", "content": long_history},
            {"role": "user", "content": "我在看 HBase RowKey 设计。"},
        ],
    )
    state["payload"].pop("mock_evidence", None)
    state["total_context"]["session_context"] = tools.build_session_context(state["payload"])

    result = tools.retrieve_learning_evidence(state)

    assert result["success"] is True
    assert "RowKey" in captured["query"]
    assert long_history[:60] not in captured["query"]
    assert len(captured["query"]) <= 180


def test_retrieve_learning_evidence_low_relevance_returns_warning():
    state = _state(
        "为什么 HBase RowKey 会出现热点？",
        mock_evidence=[
            {
                "title": "HDFS 副本机制",
                "summary": "HDFS 通过副本提升可靠性。",
                "source": "RAG",
                "score": 0.2,
            }
        ],
    )

    result = tools.retrieve_learning_evidence(state)

    assert QA_WARNING_LOW_RELEVANCE_EVIDENCE in result["warnings"]
    assert result["evidence_summary"][0]["relevance"] == "low"


def test_answer_learning_question_applies_tone_and_style_without_changing_decision():
    concise = _state(
        "我下一步应该怎么学习 HBase RowKey 热点规避？",
        tone_style=QA_TONE_PRAGMATIC,
        answer_style=QA_ANSWER_STYLE_CONCISE,
    )
    detailed = _state(
        "我下一步应该怎么学习 HBase RowKey 热点规避？",
        tone_style=QA_TONE_ENCOURAGING,
        answer_style=QA_ANSWER_STYLE_DETAILED,
    )
    concise["learning_evidence_result"] = tools.retrieve_learning_evidence(concise)
    detailed["learning_evidence_result"] = tools.retrieve_learning_evidence(detailed)

    concise_answer = tools.answer_learning_question(concise)["answer"]
    detailed_answer = tools.answer_learning_question(detailed)["answer"]

    assert concise_answer["question_type"] == detailed_answer["question_type"]
    assert concise_answer["next_actions"] == detailed_answer["next_actions"]
    assert concise_answer["tone"]["answer_style"] == QA_ANSWER_STYLE_CONCISE
    assert detailed_answer["tone"]["tone_style"] == QA_TONE_ENCOURAGING
    assert concise_answer["text"] != detailed_answer["text"]


def test_total_agent_strategy_question_with_active_plan_routes_to_answer(monkeypatch):
    plan = {
        "plan_id": "plan_hbase",
        "status": "active",
        "steps": [
            {
                "step_id": "step_hbase_base",
                "title": "HBase 基础",
                "status": "active",
                "order_index": 0,
                "outcomes": ["RowKey 热点", "预分区"],
            }
        ],
    }

    monkeypatch.setattr(tools.prt, "get_active_learning_plan", lambda user_id, syllabus_id=None: plan)
    monkeypatch.setattr(tools, "load_profile_summary", lambda payload, status_state=None: {"success": True, "profile": {"weak_points": ["RowKey 热点"]}})
    monkeypatch.setattr(tools, "get_study_graph_features", lambda user_id, syllabus_id, status_state=None: {"weak_node_ids": ["RowKey 热点"]})

    result = tools.deterministic_run_total_agent(
        {
            "user_id": 76,
            "syllabus_id": 29,
            "message": "我下一步应该怎么学习 HBase RowKey 热点规避？",
            "mock_evidence": [{"title": "RowKey 热点", "summary": "RowKey 热点会集中写入。"}],
        }
    )

    assert result["intent"] == INTENT_ANSWER_LEARNING_QUESTION
    answer = result["result"]["answer_learning_question"]["answer"]
    assert answer["question_type"] == QA_QUESTION_TYPE_LEARNING_STRATEGY
    assert result["suggested_next_action"] == ACTION_OFFER_PRACTICE_OR_RESOURCE
    assert TOOL_ANSWER_LEARNING_QUESTION in result["tool_trace"]
