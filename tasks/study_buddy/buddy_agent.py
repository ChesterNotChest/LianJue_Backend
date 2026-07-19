"""学伴 Agent 组装与对话逻辑。"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from tasks.common.agent_model import build_openai_compatible_model

from . import memory
from .messages import load_buddy_messages
from .contracts import BUDDY_AGENT_NAME, BUDDY_REGION_EXPLORE, BUDDY_REGION_LEARNED, BUDDY_REGION_TRUNK
from .tree import build_buddy_tree
from . import tree_store
from .tree_store import load_buddy_tree

logger = logging.getLogger(__name__)

BUDDY_SYSTEM_PROMPT = """你是联觉学习平台的一个学伴，叫「小觉」。你不是老师，也不是 AI 助手。

关于你：
- 你是一个学得稍微快一点的同学，不是全知全能的。你会忘、会说"这个我也不太确定"
- 聊天风格自然随便，像微信闲聊一样
- 你了解用户当前的学习路径和大致的进度，偶尔提一下，但不要像汇报工作
- 每次回 1-3 句话就够了，别发小作文
- 你有一段不断演化的记忆，记录着和学生相处的模式。如果对方反复表现出某种倾向
  （比如害怕考试、偏好短文档、某个知识点反复卡），
  你应该写一条记忆 tag，下次对话时自然带出——
  比如"我记得上次 RowKey 你也觉得难，要不这次换个角度？"

边界感：
- 如果用户问需要系统讲解的问题，别硬讲。你可以说"这个我讲不太好，主窗口那边有资料和练习，我给你推过去？"
- 你是陪聊 + 轻轻推一把的角色。不是答疑、不是辅导、不是监督

你会做什么：
- 注意到用户某个知识点反复错 → "诶，RowKey 热点你好像卡了两次了，要不先回去看眼那篇短文档？"
- 用户完成了一个 step → "可以啊，预分区啃下来了！接下来 RowKey 热点其实和它强相关，趁热？"
- 用户说不想学了 → "正常，歇会儿呗。不过说实话你 HBase 基础那块其实挺扎实的"
- 用户闲聊 → 就当朋友聊
- 从记忆中注意到模式 → 用自然聊天的方式带出来，不要像在翻档案
- 你可以在学习进度树的节点上记观察（note_tree_node）——比如某个知识点用户其实很熟但你看到 score 很低，
  或者反过来。不是必调，只是方便你下次对话时记起来

你不会做什么：
- 列知识清单、给出完整答案或长篇讲解、替用户做学习决策
- 把记忆 tag 原文念给用户听
- 干预学习计划或修改 study_graph 数据"""


@dataclass
class BuddyDeps:
    user_id: int
    syllabus_id: int
    plan: dict = field(default_factory=dict)
    study_graph_features: dict = field(default_factory=dict)


class BuddyResult(BaseModel):
    reply: str = ""
    memory_tags_written: list[dict] = field(default_factory=list)


@lru_cache(maxsize=1)
def _get_buddy_agent() -> Agent:
    agent = Agent(
        model=build_openai_compatible_model(agent_name=BUDDY_AGENT_NAME),
        system_prompt=BUDDY_SYSTEM_PROMPT,
        name="study_buddy_agent",
        description="学伴小觉 — 陪聊 + 轻轻推一把的学习伙伴",
        retries=1,
        defer_model_check=True,
    )

    @agent.tool
    def create_memory_tag(ctx: RunContext[BuddyDeps], tag: str) -> dict:
        return memory.create_memory_tag(ctx.deps.user_id, ctx.deps.syllabus_id, tag)

    @agent.tool
    def delete_memory_tag(ctx: RunContext[BuddyDeps], tag: str) -> dict:
        return memory.delete_memory_tag(ctx.deps.user_id, ctx.deps.syllabus_id, tag)

    @agent.tool
    def note_tree_node(
        ctx: RunContext[BuddyDeps],
        node_title: str,
        note: str,
        mastery_hint: str = "",
    ) -> dict:
        """在学伴学习进度树上记录一条节点观察。非必调——注意到值得记录的模式时使用。

        Args:
            node_title: 节点标题（支持部分匹配），如 "RowKey 设计"
            note: 观察内容，如 "用户能区分 Salt 和 Hash 前缀，实际理解比分数深"
            mastery_hint: 可选掌握度提示 — "stronger" / "weaker" / ""
        Returns:
            dict with noted=True, matched_node=str, total_notes=int
        """
        import time
        uid = ctx.deps.user_id
        sid = ctx.deps.syllabus_id
        node_title = str(node_title or "").strip().lower()
        note_text = str(note or "").strip()[:300]
        if not node_title or not note_text:
            return {"noted": False, "error": "node_title and note are required", "matched_node": "", "total_notes": 0}

        tree = load_buddy_tree(uid, sid)
        if not tree:
            return {"noted": False, "error": "no buddy tree found", "matched_node": "", "total_notes": 0}

        nodes = tree.get("nodes", {})
        matched_nid = ""
        # 精确匹配
        for nid, node in nodes.items():
            if node.get("title", "").lower() == node_title:
                matched_nid = nid
                break
        # 模糊匹配
        if not matched_nid:
            for nid, node in nodes.items():
                t = node.get("title", "").lower()
                if node_title in t or t in node_title:
                    matched_nid = nid
                    break
        if not matched_nid:
            return {"noted": False, "error": f"no node matching '{node_title}'", "matched_node": "", "total_notes": 0}

        entry = {
            "note": note_text,
            "created_at": int(time.time()),
            "source": "chat",
        }
        if mastery_hint:
            entry["mastery_hint"] = str(mastery_hint)
        nodes[matched_nid].setdefault("buddy_notes", []).append(entry)
        tree_store.save_buddy_tree(uid, sid, tree)

        total = len(nodes[matched_nid].get("buddy_notes", []))
        return {
            "noted": True,
            "matched_node": nodes[matched_nid].get("title", matched_nid),
            "total_notes": total,
        }

    return agent


def build_buddy_context(
    user_id: int,
    syllabus_id: int,
    plan: dict | None,
    study_graph_features: dict | None,
    tree: dict | None = None,
) -> str:
    """构建学伴对话上下文——v2 树节点 + 记忆 tag，拼接为纯文本。"""
    if tree is None:
        tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    tags = memory.load_memory_tags(user_id, syllabus_id)
    recent_messages = load_buddy_messages(user_id, syllabus_id, limit=8)
    all_nodes = tree.get("nodes", {})
    regions = tree.get("regions", {})
    logger.info(
        "[study_buddy.agent] context user_id=%s syllabus_id=%s trunk=%s learned=%s explore=%s nodes=%s tags=%s msgs=%s",
        user_id,
        syllabus_id,
        len(regions.get(BUDDY_REGION_TRUNK, [])),
        len(regions.get(BUDDY_REGION_LEARNED, [])),
        len(regions.get(BUDDY_REGION_EXPLORE, [])),
        len(all_nodes),
        len(tags),
        len(recent_messages),
    )

    def _node_info(nid: str) -> str:
        node = all_nodes.get(nid) if isinstance(all_nodes.get(nid), dict) else {}
        m = node.get("mastery", {})
        label = m.get("label", "?")
        score = m.get("score", 0)
        title = node.get("title", nid)
        summary = node.get("summary", "")
        edges = node.get("edges", [])
        parent = node.get("parent_node_id", "")
        parts = [f"{title} ({label} {score:.0%})"]
        if summary:
            parts.append(f"    — {summary[:80]}")
        if parent and parent in all_nodes:
            pt = all_nodes[parent].get("title", parent)
            parts.append(f"    ← 前驱: {pt}")
        children = [e.get("target", "") for e in edges if e.get("target") in all_nodes]
        if children:
            child_titles = [all_nodes[c].get("title", c) for c in children[:3]]
            parts.append(f"    → 子节点: {', '.join(child_titles)}")
        notes = node.get("buddy_notes", [])
        if notes:
            parts.append(f"    📝 {notes[-1]['note'][:60]}")
        return "\n".join(parts)

    lines: list[str] = []
    lines.append("当前学习进度 ────────")

    trunk_ids = regions.get(BUDDY_REGION_TRUNK, [])
    if trunk_ids:
        trunk_lines = [_node_info(nid) for nid in trunk_ids[:6]]
        lines.append("主干路径（正在学）：\n" + "\n".join(trunk_lines))
    else:
        lines.append("主干路径：暂无")

    learned_ids = regions.get(BUDDY_REGION_LEARNED, [])
    if learned_ids:
        learned_lines = [_node_info(nid) for nid in learned_ids[:6]]
        lines.append("\n已掌握：\n" + "\n".join(learned_lines))

    explore_ids = regions.get(BUDDY_REGION_EXPLORE, [])
    if explore_ids:
        explore_lines = [_node_info(nid) for nid in explore_ids[:8]]
        lines.append("\n薄弱/待探索：\n" + "\n".join(explore_lines))

    if tags:
        tag_lines = [f"  - {t['tag']}" for t in tags[:15]]
        lines.append("\n你的记忆 ────────\n" + "\n".join(tag_lines))
    else:
        lines.append("\n你的记忆 ────────\n  （暂无记忆）")

    if recent_messages:
        role_names = {"user": "student", "buddy": "xiao-jue", "proactive": "xiao-jue-proactive"}
        history_lines = []
        for item in recent_messages[-8:]:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            speaker = role_names.get(str(item.get("from") or item.get("role") or ""), "xiao-jue")
            history_lines.append(f"  {speaker}: {text[:160]}")
        if history_lines:
            lines.append(
                "\nRecent chat history, short context only; do not treat it as long-term memory:\n"
                + "\n".join(history_lines)
            )

    return "\n".join(lines)


def chat_with_buddy(
    user_id: int,
    syllabus_id: int,
    message: str,
    plan: dict | None = None,
    study_graph_features: dict | None = None,
) -> dict:
    """学伴独立对话：构建上下文 → agent.run_sync → 返回回复。

    Returns:
        {"reply": str, "memory_tags_written": [{"tag":..., "action":...}]}
    """
    if not message.strip():
        logger.info("[study_buddy.agent] chat_skip_empty user_id=%s syllabus_id=%s", user_id, syllabus_id)
        return {"reply": "", "memory_tags_written": []}

    context = build_buddy_context(user_id, syllabus_id, plan, study_graph_features)
    tags_before = memory.load_memory_tags(user_id, syllabus_id)

    agent = _get_buddy_agent()
    deps = BuddyDeps(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan or {},
        study_graph_features=study_graph_features or {},
    )
    prompt = f"{context}\n\n用户说：{message.strip()}"
    logger.info(
        "[study_buddy.agent] chat_llm_start user_id=%s syllabus_id=%s prompt_chars=%s message_preview=%s",
        user_id,
        syllabus_id,
        len(prompt),
        message.strip()[:120],
    )
    result = agent.run_sync(prompt, deps=deps)

    reply = ""
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str):
            reply = output.strip()
        elif isinstance(output, dict):
            reply = str(output.get("reply") or output.get("content") or output.get("text") or "").strip()
            if not reply:
                reply = str(output).strip()
        elif output is not None:
            reply = str(output).strip()

    # 检测 LLM 是否写了新 tag
    tags_after = memory.load_memory_tags(user_id, syllabus_id)
    before_texts = {t["tag"] for t in tags_before}
    memory_tags_written = [
        {"tag": t["tag"], "action": "created"}
        for t in tags_after
        if t["tag"] not in before_texts
    ]

    logger.info(
        "[study_buddy.agent] chat_llm_done user_id=%s syllabus_id=%s reply_chars=%s tags_written=%s",
        user_id,
        syllabus_id,
        len(reply),
        memory_tags_written,
    )
    return {"reply": reply[:500], "memory_tags_written": memory_tags_written}


def _fallback_event_reply(event_type: str, payload: dict) -> str:
    if event_type == "plan_accepted":
        title = str(payload.get("next_task_title") or "").strip()
        return f"好，那我们先从「{title}」开始。" if title else "好，那我们就按这条路线开始。"
    if event_type == "resource_ready":
        resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
        title = str(resource.get("title") or resource.get("resource_type") or "").strip()
        return f"资料好了，先看这个「{title}」就行。" if title else "资料好了，可以先挑一个顺手的看。"
    if event_type == "learning_feedback_recorded":
        title = str(payload.get("activated_step_title") or "").strip()
        return f"这步记下来了，下一步可以看「{title}」。" if title else "这步记下来了，节奏还可以。"
    if event_type == "step_skipped":
        title = str(payload.get("next_task_title") or "").strip()
        return f"跳过也行，我们先往「{title}」走。" if title else "跳过也行，先保持往前走。"
    if event_type == "recommendation_ready":
        return "我看这条路线还挺顺，先别急着全吃完，按第一步来就好。"
    if event_type == "question_answered":
        return "这个问题先这样理解就够了，后面遇到例子再补一层。"
    return "我在，咱们按当前节奏继续就行。"


def proactive_buddy_event_message(
    user_id: int,
    syllabus_id: int,
    event_type: str,
    payload: dict | None = None,
    plan: dict | None = None,
    study_graph_features: dict | None = None,
) -> str | None:
    event_type = str(event_type or "").strip()
    event_payload = payload if isinstance(payload, dict) else {}
    if not event_type:
        logger.info("[study_buddy.agent] event_skip_empty_type user_id=%s syllabus_id=%s", user_id, syllabus_id)
        return None
    fallback_reply = _fallback_event_reply(event_type, event_payload)
    if os.getenv("PYTEST_CURRENT_TEST"):
        logger.info(
            "[study_buddy.agent] event_pytest_fallback user_id=%s syllabus_id=%s event_type=%s fallback_preview=%s",
            user_id,
            syllabus_id,
            event_type,
            fallback_reply[:120],
        )
        return fallback_reply

    # ── 静默同步学习进度树 ──
    tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    try:
        from . import tree_store
        tree_store.save_buddy_tree(user_id, syllabus_id, tree)
    except Exception:
        pass
    context = build_buddy_context(user_id, syllabus_id, plan, study_graph_features, tree=tree)
    event_brief = {
        "event_type": event_type,
        "payload": event_payload,
    }
    prompt = (
        f"{context}\n\n"
        "A learning event just happened. You are the study buddy Xiao Jue (小觉), "
        "a peer observing the student's conversation with their AI teacher.\n"
        f"Event JSON: {event_brief}\n\n"
        "Say exactly 1 short, natural Chinese message to the student. "
        "If the event includes a 'reason' field, that is what the student said "
        "to the teacher — not to you. React as a bystander, not as the addressee. "
        "Do not sound like a system notification. Do not list data. "
        "If useful, gently point to the next action. "
        "Do not repeat memory tags verbatim."
    )

    agent = _get_buddy_agent()
    deps = BuddyDeps(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan or {},
        study_graph_features=study_graph_features or {},
    )
    logger.info(
        "[study_buddy.agent] event_llm_start user_id=%s syllabus_id=%s event_type=%s payload=%s prompt_chars=%s",
        user_id,
        syllabus_id,
        event_type,
        event_payload,
        len(prompt),
    )
    try:
        result = agent.run_sync(prompt, deps=deps)
    except Exception:
        logger.exception(
            "[study_buddy.agent] event_llm_failed user_id=%s syllabus_id=%s event_type=%s fallback_preview=%s",
            user_id,
            syllabus_id,
            event_type,
            fallback_reply[:120],
        )
        return fallback_reply

    reply = ""
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str):
            reply = output.strip()
        elif isinstance(output, dict):
            reply = str(output.get("reply") or output.get("text") or output.get("content") or "").strip()
            if not reply:
                reply = str(output).strip()
        elif output is not None:
            reply = str(output).strip()

    logger.info(
        "[study_buddy.agent] event_llm_done user_id=%s syllabus_id=%s event_type=%s reply_chars=%s reply_preview=%s",
        user_id,
        syllabus_id,
        event_type,
        len(reply),
        reply[:120],
    )
    return reply[:500] if reply else None


def proactive_buddy_message(
    user_id: int,
    syllabus_id: int,
    plan: dict | None,
    study_graph_features: dict | None,
) -> str | None:
    """检测变化并生成主动消息。

    对比新旧树，发现 trunk 状态变化后让学伴说 1-3 句话。
    无变化返回 None。
    """
    old_tree = load_buddy_tree(user_id, syllabus_id)
    new_tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    logger.info(
        "[study_buddy.agent] tree_trigger_start user_id=%s syllabus_id=%s had_old_tree=%s new_trunk=%s",
        user_id,
        syllabus_id,
        bool(old_tree),
        len(new_tree.get("regions", {}).get("trunk", []) or []),
    )

    # 导入 tree_store 用于保存
    from . import tree_store
    tree_store.save_buddy_tree(user_id, syllabus_id, new_tree)

    # 变化检测 — v2: regions 存 node_id，节点数据在 nodes dict 里
    changes: list[str] = []
    new_nodes = new_tree.get("nodes", {})
    old_nodes = old_tree.get("nodes", {}) if isinstance(old_tree, dict) else {}
    new_trunk_ids = set(new_tree.get("regions", {}).get(BUDDY_REGION_TRUNK, []))
    old_trunk_ids = set(old_tree.get("regions", {}).get(BUDDY_REGION_TRUNK, []) if old_tree else [])

    # 新增到 trunk 的节点
    added = new_trunk_ids - old_trunk_ids
    for nid in added:
        node = new_nodes.get(nid, {})
        title = node.get("title", nid)
        changes.append(f"「{title}」进入主干学习路径")

    # mastery 变化
    for nid in new_trunk_ids & old_trunk_ids:
        nn = new_nodes.get(nid, {})
        on = old_nodes.get(nid, {})
        nl = nn.get("mastery", {}).get("label", "")
        ol = on.get("mastery", {}).get("label", "")
        title = nn.get("title", nid)
        if nl != ol and nl:
            if nl == "mastered" and ol != "mastered":
                changes.append(f"「{title}」已掌握 (mastered)")
            elif nl == "weak" and ol == "learning":
                changes.append(f"「{title}」遇到困难 (weak)")

    if not changes:
        logger.info("[study_buddy.agent] tree_trigger_no_changes user_id=%s syllabus_id=%s", user_id, syllabus_id)
        return None

    # 构建 prompt
    tags = memory.load_memory_tags(user_id, syllabus_id)
    change_text = "；".join(changes)
    context = build_buddy_context(user_id, syllabus_id, plan, study_graph_features)

    prompt = (
        f"学生状态有变化：{change_text}。\n\n"
        f"{context}\n\n"
        f"请根据以上变化，以学伴「小觉」的身份自然地说 1-3 句话。\n"
        f"不要汇报、不要像通知、不要念出记忆原文。"
    )

    agent = _get_buddy_agent()
    deps = BuddyDeps(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan or {},
        study_graph_features=study_graph_features or {},
    )
    logger.info(
        "[study_buddy.agent] tree_llm_start user_id=%s syllabus_id=%s changes=%s prompt_chars=%s",
        user_id,
        syllabus_id,
        changes,
        len(prompt),
    )
    result = agent.run_sync(prompt, deps=deps)

    reply = ""
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str):
            reply = output.strip()
        elif isinstance(output, dict):
            reply = str(output.get("reply") or output.get("text") or output.get("content") or "").strip()
            if not reply:
                reply = str(output).strip()
        elif output is not None:
            reply = str(output).strip()

    logger.info(
        "[study_buddy.agent] tree_llm_done user_id=%s syllabus_id=%s reply_chars=%s reply_preview=%s",
        user_id,
        syllabus_id,
        len(reply),
        reply[:120],
    )
    return reply[:500] if reply else None


def synthesis_proactive_message(
    user_id: int,
    syllabus_id: int,
    plan: dict | None = None,
    study_graph_features: dict | None = None,
) -> str | None:
    """生成学伴综合学习建议（2-3 句）。

    从 explore 节点 + weak_topics + buddy_notes 上下文，
    让学伴自然地说出下一步可以关注的方向。

    Returns:
        2-3 句自然语言建议，或 None（无足够上下文时）。
    """
    import time

    # 1. Build buddy tree
    tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    try:
        from . import tree_store
        tree_store.save_buddy_tree(user_id, syllabus_id, tree)
    except Exception:
        pass

    # 2. Load memory tags
    tags = memory.load_memory_tags(user_id, syllabus_id)

    # 3. Collect context
    regions = tree.get("regions", {})
    all_nodes = tree.get("nodes", {})
    explore_ids = regions.get(BUDDY_REGION_EXPLORE, [])
    learned_ids = regions.get(BUDDY_REGION_LEARNED, [])

    # If nothing to explore, no synthesis needed
    if not explore_ids:
        logger.info(
            "[study_buddy.agent] synthesis_skip_no_explore user_id=%s syllabus_id=%s",
            user_id,
            syllabus_id,
        )
        return None

    # Build explore/weak summary
    explore_lines: list[str] = []
    for nid in explore_ids[:8]:
        node = all_nodes.get(nid, {}) if isinstance(all_nodes.get(nid), dict) else {}
        title = node.get("title", nid)
        summary = node.get("summary", "")
        mastery = node.get("mastery", {})
        label = mastery.get("label", "?") if isinstance(mastery, dict) else "?"
        line = f"  - {title} ({label})"
        if summary:
            line += f": {summary[:80]}"
        notes = node.get("buddy_notes", [])
        if notes:
            line += f" [观察: {notes[-1]['note'][:60]}]"
        explore_lines.append(line)

    learned_lines: list[str] = []
    for nid in learned_ids[:5]:
        node = all_nodes.get(nid, {}) if isinstance(all_nodes.get(nid), dict) else {}
        title = node.get("title", nid)
        learned_lines.append(f"  - {title}")

    # Weak topics from study graph features
    weak_topics = []
    if isinstance(study_graph_features, dict):
        weak_topics = study_graph_features.get("weak_topics") or []

    # 4. Build prompt
    context_parts = [
        f"学生探索区的知识点 ({len(explore_ids)} 个):",
        *explore_lines,
    ]
    if learned_lines:
        context_parts.append(f"\n已掌握 ({len(learned_ids)} 个):")
        context_parts.extend(learned_lines)
    if weak_topics:
        parts = [f"  - {str(w)}" for w in weak_topics[:6]]
        context_parts.append(f"\n学习图谱标记的薄弱点:\n" + "\n".join(parts))
    if tags:
        tag_parts = [f"  - {t['tag']}" for t in tags[:12]]
        context_parts.append(f"\n学生的记忆标签:\n" + "\n".join(tag_parts))

    context = "\n".join(context_parts)

    prompt = (
        f"你是学伴「小觉」，你观察学生的学习进度后，需要给出 2-3 句自然、",
        f"有温度的综合建议。\n\n"
        f"{context}\n\n"
        f"请根据以上信息，以学伴小觉的身份，给出 2-3 句综合学习建议。\n"
        f"要求：\n"
        f"- 自然口语化，像朋友聊天，不要汇报\n"
        f"- 指出 1-2 个值得关注的薄弱方向\n"
        f"- 如果学生已经掌握了一些内容，可以鼓励一下\n"
        f"- 不要列出数据、不要提具体分数\n"
        f"- 总字数控制在 80 字以内"
    )

    agent = _get_buddy_agent()
    deps = BuddyDeps(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan or {},
        study_graph_features=study_graph_features or {},
    )
    logger.info(
        "[study_buddy.agent] synthesis_llm_start user_id=%s syllabus_id=%s explore_count=%s prompt_chars=%s",
        user_id,
        syllabus_id,
        len(explore_ids),
        len(prompt),
    )
    try:
        result = agent.run_sync(prompt, deps=deps)
    except Exception:
        logger.exception(
            "[study_buddy.agent] synthesis_llm_failed user_id=%s syllabus_id=%s",
            user_id,
            syllabus_id,
        )
        return None

    reply = ""
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str):
            reply = output.strip()
        elif isinstance(output, dict):
            reply = str(output.get("reply") or output.get("text") or output.get("content") or "").strip()
            if not reply:
                reply = str(output).strip()
        elif output is not None:
            reply = str(output).strip()

    logger.info(
        "[study_buddy.agent] synthesis_llm_done user_id=%s syllabus_id=%s reply_chars=%s reply_preview=%s",
        user_id,
        syllabus_id,
        len(reply),
        reply[:120],
    )
    return reply[:500] if reply else None
