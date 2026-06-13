"""学伴 Agent 组装与对话逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from tasks.common.agent_model import build_openai_compatible_model

from . import memory
from .contracts import BUDDY_AGENT_NAME
from .tree import build_buddy_tree
from .tree_store import load_buddy_tree

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

你不会做什么：
- 列知识清单、给出完整答案或长篇讲解、替用户做学习决策
- 把记忆 tag 原文念给用户听"""


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

    return agent


def build_buddy_context(
    user_id: int,
    syllabus_id: int,
    plan: dict | None,
    study_graph_features: dict | None,
) -> str:
    """构建学伴对话上下文——树 + 记忆 tag，拼接为纯文本。"""
    tree = build_buddy_tree(user_id, syllabus_id, plan, study_graph_features)
    tags = memory.load_memory_tags(user_id, syllabus_id)
    regions = tree.get("regions", {})

    lines: list[str] = []
    lines.append("当前学习状态 ────────")

    # trunk
    trunk = regions.get("trunk", [])
    if trunk:
        trunk_lines = [
            f"  [{s.get('status', '?')}] {s.get('title', '')}"
            for s in trunk[:10]
        ]
        lines.append("主干路径：\n" + "\n".join(trunk_lines))
    else:
        lines.append("主干路径：暂无")

    # learned
    learned = regions.get("learned", [])
    if learned:
        learned_lines = [
            f"  {n.get('signal', '?')} ({n.get('score', 0):.0%}): {n.get('title', '')}"
            for n in learned[:8]
        ]
        lines.append("已掌握：\n" + "\n".join(learned_lines))

    # explore
    explore = regions.get("explore", [])
    if explore:
        explore_lines = [
            f"  {n.get('signal', '?')}: {n.get('title', '')}"
            for n in explore[:8]
        ]
        lines.append("可以探索的：\n" + "\n".join(explore_lines))

    # memory tags
    if tags:
        tag_lines = [f"  - {t['tag']}" for t in tags[:15]]
        lines.append("你的记忆 ────────\n" + "\n".join(tag_lines))
    else:
        lines.append("你的记忆 ────────\n  （暂无记忆）")

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

    return {"reply": reply[:500], "memory_tags_written": memory_tags_written}


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

    # 导入 tree_store 用于保存
    from . import tree_store
    tree_store.save_buddy_tree(user_id, syllabus_id, new_tree)

    # 变化检测
    changes: list[str] = []
    old_trunk = {
        s["step_id"]: s
        for s in (old_tree.get("regions", {}).get("trunk", []) if old_tree else [])
    }
    new_trunk = {s["step_id"]: s for s in new_tree["regions"]["trunk"]}

    for sid, ns in new_trunk.items():
        os = old_trunk.get(sid, {})
        old_status = os.get("status", "")
        new_status = ns.get("status", "")
        title = ns.get("title", "")
        if old_status == "pending" and new_status == "active":
            changes.append(f"「{title}」从待办变为当前学习步骤")
        elif old_status == "active" and new_status == "completed":
            changes.append(f"「{title}」已完成")

    if not changes:
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

    return reply[:500] if reply else None
