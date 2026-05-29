"""学习画像模块门户。

跨模块调用和 API 层调用都应从这里进入；画像构建服务、个人大纲维护、
Agent 工具和 Agent 运行时下沉在 ``tasks.learning_profile`` 包内。
"""

################
# Agent 入口：构造或运行学习画像 Agent，并提供兜底工具选择策略。
from tasks.learning_profile.agent_runtime import (
    fallback_next_learning_profile_tool,
    get_learning_profile_agent,
    run_learning_profile_agent,
)

################
# 个人大纲入口：读取、初始化、归一化并应用画像产生的大纲建议。
from tasks.learning_profile.personal_syllabus import (
    append_profile_personal_syllabus_suggestion,
    init_profile_personal_syllabus,
    maybe_apply_profile_personal_syllabus_progress,
    normalize_profile_personal_syllabus_suggestion,
    read_profile_personal_syllabus,
)

################
# 画像服务入口：读取缓存画像、构建画像、加载历史记录和个人大纲上下文。
from tasks.learning_profile.service import (
    build_learning_profile,
    collect_history_entries,
    get_or_build_learning_profile,
    get_persisted_learning_profile,
    load_personal_syllabus_rows,
)

__all__ = [
    "append_profile_personal_syllabus_suggestion",
    "build_learning_profile",
    "collect_history_entries",
    "fallback_next_learning_profile_tool",
    "get_learning_profile_agent",
    "get_or_build_learning_profile",
    "get_persisted_learning_profile",
    "init_profile_personal_syllabus",
    "load_personal_syllabus_rows",
    "maybe_apply_profile_personal_syllabus_progress",
    "normalize_profile_personal_syllabus_suggestion",
    "read_profile_personal_syllabus",
    "run_learning_profile_agent",
]
