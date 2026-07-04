import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks import personal_recommendation_task as prt
from tasks import total_agent_task as tat
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_runtime as tar
from tasks.total_agent import agent_tools as tagt


ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "total_agent"
WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"


def _normalize_model_for_dashscope():
    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        tar.get_total_agent.cache_clear()
        profile_runtime.get_learning_profile_agent.cache_clear()


def _reset_artifact_root(name: str) -> Path:
    root = ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> None:
    (root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def db_total_agent_profile_case():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent profile integration smoke test.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    app = create_app()
    with app.app_context():
        suffix = os.urandom(4).hex()
        user = User(
            user_name=f"total-agent-profile-{suffix}",
            password_hash="pytest-not-used",
            email=f"total-agent-profile-{suffix}@example.com",
        )
        syllabus = Syllabus.query.filter_by(syllabus_path=WORKING_SYLLABUS_PATH).first()
        created_syllabus = False
        if syllabus is None:
            syllabus = Syllabus(title="大数据概论", syllabus_path=WORKING_SYLLABUS_PATH)
            db.session.add(syllabus)
            created_syllabus = True
        db.session.add(user)
        db.session.commit()
        relation = UserSyllabus(user_id=user.user_id, syllabus_id=syllabus.syllabus_id, syllabus_permission="user")
        db.session.add(relation)
        db.session.commit()
        try:
            yield user, syllabus, relation
        finally:
            db.session.rollback()
            UserSyllabus.query.filter_by(user_id=user.user_id, syllabus_id=syllabus.syllabus_id).delete()
            User.query.filter_by(user_id=user.user_id).delete()
            if created_syllabus:
                Syllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
            db.session.commit()


def _recommendation_fixture() -> dict:
    return {
        "success": True,
        "best_path": {
            "path": ["hbase_intro", "rowkey_design"],
            "skills": ["hbase", "rowkey"],
        },
        "candidates": [
            {
                "path": ["hbase_intro", "rowkey_design"],
                "skills": ["hbase", "rowkey"],
            }
        ],
        "graph": {
            "nodes": [
                {"id": "hbase_intro", "title": "HBase Basics", "outcomes": ["hbase"]},
                {"id": "rowkey_design", "title": "HBase RowKey Design", "outcomes": ["rowkey_design"]},
            ],
            "edges": [{"source": "hbase_intro", "target": "rowkey_design"}],
        },
    }


def _fake_generation(request_payload: dict) -> dict:
    return {
        "success": True,
        "resources": [
            {
                "resource_id": "documents-total-agent-llm-choice",
                "resource_type": "documents",
                "status": "ready",
                "topic": request_payload.get("topic"),
            }
        ],
    }


def _trace_agent_tools(monkeypatch):
    trace = []
    tool_outputs = []

    def wrap(tool_name, func):
        def traced(state):
            result = func(state)
            trace[:] = list(state.get("tool_trace") or [])
            tool_outputs.append({"tool": tool_name, "result": result})
            return result

        return traced

    monkeypatch.setattr(tar, "tool_load_total_context", wrap(tac.TOOL_LOAD_TOTAL_CONTEXT, tagt.tool_load_total_context))
    monkeypatch.setattr(tar, "tool_get_next_learning_task", wrap(tac.TOOL_GET_NEXT_LEARNING_TASK, tagt.tool_get_next_learning_task))
    monkeypatch.setattr(
        tar,
        "tool_generate_current_step_resource",
        wrap(tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE, tagt.tool_generate_current_step_resource),
    )
    monkeypatch.setattr(
        tar,
        "tool_run_learning_recommendation",
        wrap(tac.TOOL_RUN_LEARNING_RECOMMENDATION, tagt.tool_run_learning_recommendation),
    )
    tar.get_total_agent.cache_clear()
    return trace, tool_outputs


@pytest.mark.llm
def test_total_agent_real_llm_selects_continue_tool_chain(monkeypatch, tmp_path):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent tool-choice smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("agent_choice_continue")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)
    trace, tool_outputs = _trace_agent_tools(monkeypatch)

    accepted = prt.accept_recommendation_path(
        user_id=8,
        syllabus_id=20,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True

    try:
        result = tat.run_total_agent_agent(
            {
                "user_id": 8,
                "syllabus_id": 20,
                "message": "请继续学习当前步骤，并给我一份文档资料",
                "resource_types": ["documents"],
            }
        )
    finally:
        tar.get_total_agent.cache_clear()

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert result["tool_trace"] == tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE]
    assert result["suggested_next_action"] == tac.ACTION_RECORD_LEARNING_FEEDBACK
    _write_artifact(
        artifact_root,
        "agent_choice_continue_result.json",
        {
            "test_name": "test_total_agent_real_llm_selects_continue_tool_chain",
            "expected_tool_order": tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE],
            "tool_trace": trace,
            "tool_outputs": tool_outputs,
            "result": result,
        },
    )


@pytest.mark.llm
def test_total_agent_reads_real_profile_agent_output_for_resource_strategy(
    monkeypatch,
    tmp_path,
    db_total_agent_profile_case,
):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent profile integration smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("real_profile_to_total_agent")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)
    user, syllabus, relation = db_total_agent_profile_case

    profile = lpt.get_or_build_learning_profile(
        user.user_id,
        syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=[
            "我最近在学大数据概论，HBase 的 RowKey 热点总是搞不懂。",
            "我希望两周内掌握 HBase 和预分区策略，并多做一点练习。",
        ],
        learning_goal="掌握大数据概论中的 HBase RowKey 设计",
        learning_records=[
            {
                "event_type": "study_session",
                "duration_minutes": 42,
                "meta": {"topic": "HBase"},
            }
        ],
        answer_records=[
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
        resource_usage=[
            {
                "resource_id": "video_hbase_rowkey",
                "action": "complete",
                "duration_seconds": 900,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
    )
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(profile, dict), profile
    assert isinstance(persisted, dict), profile
    assert persisted.get("profile_saved") is True

    accepted = prt.accept_recommendation_path(
        user_id=user.user_id,
        syllabus_id=syllabus.syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True

    result = tat.run_total_agent(
        {
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "message": "请继续学习当前步骤，并给我一点练习",
        }
    )
    profile_summary = result["result"]["context"]["profile_summary"]
    resource_strategy = result["result"]["resource_generation"]["resource_strategy"]

    assert result["success"] is True
    assert profile_summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert profile_summary["weak_points"] or profile_summary["learning_goal"]
    assert resource_strategy["profile_source"] == tac.PROFILE_SOURCE_PERSISTED

    _write_artifact(
        artifact_root,
        "real_profile_to_total_agent_result.json",
        {
            "test_name": "test_total_agent_reads_real_profile_agent_output_for_resource_strategy",
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "personal_profile_path": relation.personal_profile_path,
            "built_profile": profile,
            "persisted_profile": persisted,
            "total_agent_result": result,
            "profile_summary": profile_summary,
            "resource_strategy": resource_strategy,
        },
    )


# ═══════════════════════════════════════════════════════════════════
# Mock 管道测试（无 LLM，可进 CI）
# ═══════════════════════════════════════════════════════════════════


def test_total_agent_stream_pipeline_with_mock(monkeypatch):
    """用 mock agent.iter() 验证流式管道完整逻辑。

    覆盖：事件类型映射、产出顺序、status_callback → tool_status 桥接、
    final 结果构建。无需真实 LLM。
    """
    from tasks.common.status_events import STATUS_RUNNING, STATUS_SUCCEEDED, create_status_event

    # ── mock 构造块 ──────────────────────────────────────────
    class _ListIter:
        """模拟 AsyncIterator，产出列表中的每个元素。"""

        def __init__(self, items):
            self._items = list(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    class _FakeStream:
        """模拟 AgentStream：stream_text(delta=True) + 直接迭代产出 tool 事件。"""

        def __init__(self, texts=None, tool_call_groups=None):
            self._texts = list(texts or []) or [""]
            self._tool_events = []
            for i in range(len(self._texts)):
                tcs = (tool_call_groups or [])[i] if i < len(tool_call_groups or []) else []
                for tc in tcs:
                    self._tool_events.append(_PartStart(tc, part_kind="tool-call"))
            self._tool_pos = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def stream_text(self, delta=False):
            full = "".join(self._texts)
            if delta:
                for ch in full:
                    yield ch
            else:
                yield full

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._tool_pos >= len(self._tool_events):
                raise StopAsyncIteration
            evt = self._tool_events[self._tool_pos]
            self._tool_pos += 1
            return evt

    class _PartStart:
        def __init__(self, part, part_kind):
            self.event_kind = "part_start"
            self.part = _FakePart(part, part_kind)

    class _FakePart:
        def __init__(self, data, kind):
            self.part_kind = kind
            if kind == "text":
                self.content = data
            elif kind == "tool-call":
                self.tool_name = getattr(data, "tool_name", "")
                self.tool_call_id = getattr(data, "tool_call_id", "")
                self.args = getattr(data, "args", None)

    class _FakeToolGroup:
        """模拟 CallToolsNode.stream() 返回的嵌套迭代器的内层。"""

        def __init__(self, events):
            self._events = list(events)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._events:
                raise StopAsyncIteration
            return self._events.pop(0)

    class FunctionToolCallEvent:
        def __init__(self, tool_name="", tool_call_id="", args=None):
            self.tool_name = tool_name
            self.tool_call_id = tool_call_id
            self.args = args

    class FunctionToolResultEvent:
        def __init__(self, tool_name="", tool_call_id="", result=None):
            self.tool_name = tool_name
            self.tool_call_id = tool_call_id
            self.result = result

    class _FakeToolCallPart:
        def __init__(self, tool_name="", tool_call_id="", args=None):
            self.tool_name = tool_name
            self.tool_call_id = tool_call_id
            self.args = args

    # ── 带 status_callback 注入的 CallToolsNode ──────────────
    class CallToolsNode:
        """模拟 CallToolsNode：在 tool_start / tool_end 之间触发 status_callback。"""

        def __init__(self, tool_specs):
            # tool_specs: [(tool_name, args, result, succeed), ...]
            self._tool_specs = tool_specs
            self._callback = None

        def stream(self, ctx):
            return _FakeToolStream(self._tool_specs, self._callback)

    class _FakeToolStream:
        """模拟 pydantic_ai CallToolsNode.stream()：扁平事件流。"""

        def __init__(self, tool_specs, callback):
            self._events = []
            for tool_name, args, result, succeed in tool_specs:
                self._events.append(FunctionToolCallEvent(tool_name, f"call_{tool_name}", args))
                if callback:
                    callback(create_status_event(
                        agent="total_agent", stage=tool_name,
                        status=STATUS_RUNNING, message=f"调用 {tool_name}",
                    ))
                self._events.append(FunctionToolResultEvent(tool_name, f"call_{tool_name}", result))
                if callback:
                    callback(create_status_event(
                        agent="total_agent", stage=tool_name,
                        status=STATUS_SUCCEEDED if succeed else "failed",
                        message=f"{tool_name} 完成",
                    ))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._events:
                raise StopAsyncIteration
            return self._events.pop(0)

    class ModelRequestNode:
        """模拟 pydantic_ai ModelRequestNode / EndNode。"""

        def __init__(self, texts=None, tool_call_groups=None):
            self._stream = _FakeStream(texts=texts, tool_call_groups=tool_call_groups)

        def stream(self, ctx):
            return self._stream

    # ── 组装 mock agent ─────────────────────────────────────
    # 工具管线：load_total_context → generate_current_step_resource
    TOOL_SPECS = [
        (
            tac.TOOL_LOAD_TOTAL_CONTEXT,
            {},
            {
                "success": True,
                "context": {
                    "user_id": 1,
                    "syllabus_id": 20,
                    "profile_summary": {"learning_goal": "掌握 RowKey 设计"},
                },
            },
            True,
        ),
        (
            tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE,
            {},
            {
                "success": True,
                "resources": [
                    {
                        "resource_id": "doc-mock-001",
                        "resource_type": "documents",
                        "status": "ready",
                    }
                ],
            },
            True,
        ),
    ]

    def _build_fake_agent():
        """每次调用 get_total_agent() 时创建新的 mock agent。"""

        class _FakeAgent:
            def iter(self, prompt, deps=None, message_history=None):
                # 从 deps.state 拿到真实的 status_callback
                callback = None
                if deps and hasattr(deps, "state"):
                    callback = deps.state.get("status_callback")

                # 构建节点
                text_node = ModelRequestNode(
                    texts=[
                        "好的，我来查看你的学习进度，",
                        "当前步骤是 RowKey 设计，为你生成针对性资料。",
                    ],
                    tool_call_groups=[
                        [],
                        [_FakeToolCallPart(tool_name=tac.TOOL_LOAD_TOTAL_CONTEXT, tool_call_id="call_load_ctx", args={})],
                    ],
                )

                tools_node = CallToolsNode(TOOL_SPECS)
                tools_node._callback = callback  # 注入 callback

                end_node = ModelRequestNode()  # EndNode 无 stream 事件

                fake_output = tac.TotalAgentResult(
                    success=True,
                    intent=tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE,
                    tool_trace=[t[0] for t in TOOL_SPECS],
                    suggested_next_action=tac.ACTION_RECORD_LEARNING_FEEDBACK,
                )
                return _FakeRun([text_node, tools_node, end_node], fake_output)

        return _FakeAgent()

    class _FakeRun:
        def __init__(self, nodes, fake_output=None):
            self._nodes = nodes
            self.ctx = object()
            self.result = _FakeResult(fake_output)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._nodes:
                raise StopAsyncIteration
            return self._nodes.pop(0)

    class _FakeResult:
        def __init__(self, output):
            self.output = output

    # ── 注入 mock agent ─────────────────────────────────────
    monkeypatch.setattr(tar, "get_total_agent", _build_fake_agent)
    # 同时绕过 build_total_agent_user_prompt 对 payload 中 intent 字段的依赖
    monkeypatch.setattr(
        tar,
        "build_total_agent_user_prompt",
        lambda state: json.dumps({"user_id": 1, "message": "mock test"}),
    )

    # ── 运行 ────────────────────────────────────────────────
    events = []

    async def _collect():
        async for event in tar.run_total_agent_agent(
            {"user_id": 1, "syllabus_id": 20, "message": "继续学习"},
            stream=True,
        ):
            events.append(event)

    asyncio.run(_collect())

    # ── 断言 ────────────────────────────────────────────────
    types = [e["type"] for e in events]

    # 1. 事件类型覆盖
    assert tac.STREAM_EVENT_TEXT_START in types, "应产出 text_start"
    assert tac.STREAM_EVENT_TEXT_DELTA in types, "应产出 text_delta"
    assert tac.STREAM_EVENT_TOOL_START in types, "应产出 tool_start"
    assert tac.STREAM_EVENT_TOOL_END in types, "应产出 tool_end"
    assert tac.STREAM_EVENT_TOOL_STATUS in types, "应产出 tool_status（callback 桥接）"

    # 2. 最后一个是 final
    assert types[-1] == tac.STREAM_EVENT_FINAL, f"最后事件应为 final，实际: {types[-1]}"

    # 3. tool_start 与 tool_end 一一对应
    tool_starts = {e["data"]["tool_name"] for e in events if e["type"] == tac.STREAM_EVENT_TOOL_START}
    tool_ends = {e["data"]["tool_name"] for e in events if e["type"] == tac.STREAM_EVENT_TOOL_END}
    assert tool_starts == tool_ends, f"tool 配对不完整: starts={tool_starts}, ends={tool_ends}"

    # 4. 每个 tool_start 都有 running + succeeded/failed 两个 tool_status
    tool_status_stages = [e["data"]["stage"] for e in events if e["type"] == tac.STREAM_EVENT_TOOL_STATUS]
    for tool_name in tool_starts:
        assert tool_status_stages.count(tool_name) == 2, (
            f"{tool_name} 应有 2 个 tool_status（running + result），实际: "
            f"{tool_status_stages.count(tool_name)}"
        )

    # 5. tool_call 事件（由 response.tool_calls 驱动，mock 可选）

    # 6. 事件时间戳单调不降
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps), "事件应按时序产出"

    # 7. final 包含正确数据（intent/success 来自 model_output）
    final = events[-1]["data"]
    assert final["success"] is True
    assert final["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert final["suggested_next_action"] == tac.ACTION_RECORD_LEARNING_FEEDBACK
    assert isinstance(final["tool_trace"], list)

    # 8. text_delta 拼接后包含关键词
    full_text = "".join(
        e["data"].get("content_delta", "")
        for e in events
        if e["type"] == tac.STREAM_EVENT_TEXT_DELTA
    )
    assert "RowKey" in full_text, f"text_delta 拼接结果应包含课程主题词，实际: {full_text!r}"
