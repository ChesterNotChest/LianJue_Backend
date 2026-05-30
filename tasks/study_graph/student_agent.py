"""Student agent orchestration for study graph construction.

This agent consumes a fixed dispatch payload, calls RAG/search, derives study
graph change candidates, submits them, and reads back the tree/features.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks.common.search_tool import search_tool
from tasks.study_graph.normalizer import normalize_knowledge_title
from tasks.study_graph.service import (
    build_study_graph_changes_from_student_payload,
    get_learning_tree_features,
    get_student_learning_tree,
    get_student_learning_tree_context,
    submit_learning_tree_changes,
)


class StudentAgentDeps(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)


class StudentAgentResult(BaseModel):
    success: bool = True
    tree_id: Optional[str] = None
    tree: Optional[dict] = None
    features: Optional[dict] = None
    changes: Optional[list[dict]] = None
    tool_trace: list[str] = Field(default_factory=list)
    error_message: str = ""
    error_code: str = ""


def _normalize_rag_context_items(payload: Dict[str, Any], runtime_rag_context: Any) -> list[dict]:
    merged: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    def append_item(title: Any, summary: Any) -> None:
        title_text = str(title or "").strip()
        summary_text = str(summary or "").strip()
        if not title_text and not summary_text:
            return
        if not title_text:
            title_text = str(payload.get("learning_goal") or payload.get("question") or summary_text[:48]).strip()
        if not summary_text:
            summary_text = title_text
        dedupe_key = (normalize_knowledge_title(title_text), summary_text)
        if dedupe_key in seen_keys:
            return
        seen_keys.add(dedupe_key)
        merged.append({"title": title_text, "summary": summary_text})

    for item in payload.get("rag_context") or []:
        if isinstance(item, dict):
            append_item(item.get("title"), item.get("summary") or item.get("content"))
        else:
            append_item(payload.get("learning_goal") or payload.get("question"), item)

    if isinstance(runtime_rag_context, dict):
        for item in runtime_rag_context.get("results") or []:
            if isinstance(item, dict):
                append_item(item.get("title") or payload.get("learning_goal") or payload.get("question"), item.get("summary") or item.get("content"))
            else:
                append_item(payload.get("learning_goal") or payload.get("question"), item)
        for item in runtime_rag_context.get("paragraphs") or []:
            append_item(payload.get("learning_goal") or payload.get("question"), item)

    return merged


def _extract_parent_candidate_child_titles(payload: Dict[str, Any]) -> list[str]:
    child_titles: list[str] = []

    def append_unique(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in child_titles:
            child_titles.append(text)

    for item in payload.get("detected_topics") or []:
        if isinstance(item, dict):
            append_unique(item.get("title"))
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        append_unique(item.get("topic"))
        meta_points = item.get("meta", {}).get("knowledge_points") if isinstance(item.get("meta"), dict) else []
        if isinstance(meta_points, list):
            for point in meta_points:
                append_unique(point)
    return child_titles


def _merge_parent_candidates(payload: Dict[str, Any], runtime_tree_context: Any) -> list[dict]:
    merged: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    def append_candidate(parent_title: Any, child_title: Any, *, existing_node_id: Any = None, score: Any = None, matched_by: Any = None) -> None:
        parent_text = str(parent_title or "").strip()
        child_text = str(child_title or "").strip()
        if not parent_text or not child_text:
            return
        pair_key = (normalize_knowledge_title(parent_text), normalize_knowledge_title(child_text))
        if not pair_key[0] or not pair_key[1] or pair_key in seen_pairs or pair_key[0] == pair_key[1]:
            return
        seen_pairs.add(pair_key)
        candidate = {"title": parent_text, "child_title": child_text}
        if existing_node_id not in (None, ""):
            candidate["existing_node_id"] = existing_node_id
        if score not in (None, ""):
            candidate["score"] = score
        if matched_by not in (None, ""):
            candidate["matched_by"] = matched_by
        merged.append(candidate)

    for item in payload.get("parent_candidates") or []:
        if isinstance(item, dict):
            append_candidate(
                item.get("title"),
                item.get("child_title"),
                existing_node_id=item.get("existing_node_id"),
                score=item.get("score"),
                matched_by=item.get("matched_by"),
            )

    ranked_candidates = runtime_tree_context.get("ranked_candidates") if isinstance(runtime_tree_context, dict) else []
    child_titles = _extract_parent_candidate_child_titles(payload)
    for child_title in child_titles:
        child_norm = normalize_knowledge_title(child_title)
        if any(normalize_knowledge_title(item.get("child_title") or "") == child_norm for item in merged):
            continue
        for candidate in ranked_candidates or []:
            if not isinstance(candidate, dict):
                continue
            append_candidate(
                candidate.get("title"),
                child_title,
                existing_node_id=candidate.get("node_id"),
                score=candidate.get("score"),
                matched_by=candidate.get("matched_by"),
            )
            if any(normalize_knowledge_title(item.get("child_title") or "") == child_norm for item in merged):
                break

    return merged


def get_student_learning_graph(user_id: int, syllabus_id: int, include_debug: bool = False) -> dict:
    """Read the complete study graph bundle without invoking the LLM agent."""
    tree_result = get_student_learning_tree(user_id, syllabus_id, include_debug=include_debug)
    features_result = get_learning_tree_features(user_id, syllabus_id)
    success = bool(tree_result.get("success")) and bool(features_result.get("success"))
    return {
        "success": success,
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "tree_id": (features_result.get("tree_id") or (tree_result.get("tree") or {}).get("tree_id")),
        "tree": tree_result.get("tree"),
        "features": {key: value for key, value in features_result.items() if key != "success"},
        "debug": tree_result.get("debug", {}) if include_debug else {},
        "error_message": tree_result.get("error_message") or features_result.get("error_message") or "",
        "error_code": tree_result.get("error_code") or features_result.get("error_code") or "",
    }


def _build_student_agent_model() -> OpenAIModel:
    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    model_name = str(text_config.get("model_name") or "").strip()
    if not model_name:
        raise RuntimeError('missing MODEL_CONFIGS["text"]["model_name"] for student agent')
    base_url = str(text_config.get("api_base") or text_config.get("base_url") or "").strip() or None
    api_key = str(text_config.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip() or None
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    return OpenAIModel(model_name, provider=provider)


@lru_cache(maxsize=1)
def get_student_agent() -> Agent:
    agent = Agent(
        model=_build_student_agent_model(),
        deps_type=StudentAgentDeps,
        output_type=StudentAgentResult,
        system_prompt=(
            "你是建树 Student Agent。你必须根据输入 payload 自己调用工具完成知识成长树更新。"
            "标准顺序通常是：先做 RAG/search，再读取成长树上下文，再生成成长树变更候选，"
            "再提交成长树变更，最后读取成长树或摘要特征。你只能返回符合 StudentAgentResult 的 JSON。"
        ),
        name="student_agent",
        description="Student graph construction agent",
        retries=2,
        defer_model_check=True,
    )

    @agent.tool(sequential=True)
    def rag_search(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("rag_search")
        payload = ctx.deps.payload
        question = str(payload.get("question") or payload.get("learning_goal") or "").strip()
        if not question:
            question = str(payload.get("subject_title") or "").strip()
        graph_name = str((payload.get("source") or {}).get("graph_name") or "RAG").strip() or "RAG"
        result = search_tool(
            question,
            graph_name=graph_name,
            top_k=3,
            classify_list=["knowledge", "document", "quiz"],
        )
        ctx.deps.state["rag_context"] = result
        return {"tool": "rag_search", "success": result.get("success"), "result_count": result.get("result_count", 0)}

    @agent.tool(sequential=True)
    def get_tree_context(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("get_student_learning_tree_context")
        payload = ctx.deps.payload
        question = str(payload.get("question") or payload.get("learning_goal") or "").strip()
        result = get_student_learning_tree_context(
            payload.get("user_id"),
            payload.get("syllabus_id"),
            question,
        )
        ctx.deps.state["tree_context"] = result
        return {"tool": "get_student_learning_tree_context", "ranked_candidate_count": len(result.get("ranked_candidates") or [])}

    @agent.tool(sequential=True)
    def derive_payload(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("derive_payload")
        payload = ctx.deps.payload
        ctx.deps.state["derived_payload"] = {
            "user_id": payload.get("user_id"),
            "syllabus_id": payload.get("syllabus_id"),
            "source_kind": payload.get("source_kind") or (payload.get("source") or {}).get("kind") or "total_agent",
            "question": payload.get("question"),
            "learning_goal": payload.get("learning_goal"),
            "personal_syllabus_context": payload.get("personal_syllabus_context") or {},
            "rag_context": payload.get("rag_context") or [],
            "detected_topics": payload.get("detected_topics") or [],
            "events": payload.get("events") or [],
            "parent_candidates": payload.get("parent_candidates") or [],
            "source": payload.get("source") or {"kind": payload.get("source_kind") or "total_agent"},
            "timestamp": payload.get("timestamp"),
        }
        return {"tool": "derive_payload", "has_personal_syllabus": bool(ctx.deps.state["derived_payload"].get("personal_syllabus_context"))}

    @agent.tool(sequential=True)
    def build_changes(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("build_changes")
        payload = ctx.deps.state.get("derived_payload") or dict(ctx.deps.payload)
        enriched_payload = dict(payload)
        rag_context = ctx.deps.state.get("rag_context") or {}
        tree_context = ctx.deps.state.get("tree_context") or {}
        enriched_payload["rag_context"] = _normalize_rag_context_items(payload, rag_context)
        enriched_payload["parent_candidates"] = _merge_parent_candidates(payload, tree_context)
        changes = build_study_graph_changes_from_student_payload(enriched_payload)
        ctx.deps.state["changes"] = changes
        return {"tool": "build_study_graph_changes", "change_count": len(changes)}

    @agent.tool(sequential=True)
    def submit_changes(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("submit_learning_tree_changes")
        payload = ctx.deps.payload
        changes = ctx.deps.state.get("changes") or []
        result = submit_learning_tree_changes(
            payload.get("user_id"),
            payload.get("syllabus_id"),
            changes,
            source=payload.get("source") or {"kind": "total_agent"},
            timestamp=payload.get("timestamp"),
            subject_title=payload.get("subject_title"),
        )
        ctx.deps.state["submit_result"] = result
        return {"tool": "submit_learning_tree_changes", "success": result.get("success"), "result_count": len(result.get("results") or [])}

    @agent.tool(sequential=True)
    def read_tree(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("get_student_learning_tree")
        payload = ctx.deps.payload
        result = get_student_learning_tree(payload.get("user_id"), payload.get("syllabus_id"))
        ctx.deps.state["tree"] = result
        return {"tool": "get_student_learning_tree", "success": result.get("success")}

    @agent.tool(sequential=True)
    def read_features(ctx: RunContext[StudentAgentDeps]) -> dict:
        ctx.deps.state.setdefault("tool_trace", []).append("get_learning_tree_features")
        payload = ctx.deps.payload
        result = get_learning_tree_features(payload.get("user_id"), payload.get("syllabus_id"))
        ctx.deps.state["features"] = result
        return {"tool": "get_learning_tree_features", "success": result.get("success")}

    return agent


def _build_student_agent_user_prompt(payload: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "dispatch_id": payload.get("dispatch_id"),
            "source_kind": payload.get("source_kind"),
            "user_id": payload.get("user_id"),
            "syllabus_id": payload.get("syllabus_id"),
            "subject_title": payload.get("subject_title"),
            "question": payload.get("question"),
            "learning_goal": payload.get("learning_goal"),
            "personal_syllabus_context": payload.get("personal_syllabus_context"),
            "rag_context": payload.get("rag_context") or [],
            "detected_topics": payload.get("detected_topics") or [],
            "events": payload.get("events") or [],
            "parent_candidates": payload.get("parent_candidates") or [],
            "timestamp": payload.get("timestamp"),
            "execution_rules": [
                "先调用 rag_search",
                "再调用 get_tree_context",
                "再调用 derive_payload",
                "再调用 build_changes",
                "再调用 submit_changes",
                "最后调用 read_tree 和 read_features",
            ],
        },
        ensure_ascii=False,
    )


def run_student_agent(payload: Dict[str, Any]) -> StudentAgentResult:
    deps = StudentAgentDeps(payload=dict(payload or {}), state={})
    agent = get_student_agent()
    result = agent.run_sync(_build_student_agent_user_prompt(payload), deps=deps)
    result.output.tree_id = (deps.state.get("submit_result") or {}).get("tree_id") or result.output.tree_id
    result.output.tree = deps.state.get("tree") or result.output.tree
    result.output.features = deps.state.get("features") or result.output.features
    result.output.changes = deps.state.get("changes") or result.output.changes
    result.output.tool_trace = deps.state.get("tool_trace") or result.output.tool_trace
    return result.output
