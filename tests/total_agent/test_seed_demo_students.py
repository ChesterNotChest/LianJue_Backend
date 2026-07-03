"""演示学生播种 — opt-in，不可 monkeypatch，持久化到真实路径。

生成 5 个学生（低/偏低/中/偏高/高进度），每个学生都在配置的全部学科上
使用同一套真实链路播种数据：画像 + [学习计划 + 学习树 + 生成资源]。

运行：
  RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v
  RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v -k demo_medium
"""

import json
import os
import time
import uuid
from pathlib import Path

import pytest

from werkzeug.security import generate_password_hash

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks.generative_task import generate_resources_from_request

DEMO_SYLLABUS_IDS = [8, 18, 104]
DEMO_PASSWORD = "demo123"
DEMO_SUMMARY_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "demo_students"
LEVEL_LOW = "low"
LEVEL_LOW_MEDIUM = "low_medium"
LEVEL_MEDIUM = "medium"
LEVEL_MEDIUM_HIGH = "medium_high"
LEVEL_HIGH = "high"

# ── Time constants (seconds) for readable offset expressions ──
_DAY = 86400
_HALF_DAY = _DAY // 2
_WEEK = 7 * _DAY


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def demo_seed_use_db_backends(monkeypatch, default_runtime_file_backends):
    """Override conftest FILE_BACKEND — demo students use production DB paths."""
    monkeypatch.setenv("LEARNING_PLAN_FILE_BACKEND", "0")
    monkeypatch.setenv("GENERATIVE_FILE_BACKEND", "0")
    monkeypatch.setenv("STUDY_GRAPH_FILE_BACKEND", "0")
    yield


@pytest.fixture(autouse=True)
def cleanup_new_json_artifacts():
    """Override conftest autouse — preserve demo profiles on disk."""
    yield


def _require_seed_demo_env():
    missing = [
        name for name in ("RUN_LLM_TESTS", "RUN_REAL_RAG_TESTS", "RUN_DB_TESTS")
        if os.getenv(name) != "1"
    ]
    if missing:
        pytest.skip(
            "Set RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1"
        )
    if not DEMO_SYLLABUS_IDS:
        pytest.skip("DEMO_SYLLABUS_IDS is empty")


def _normalize_model_for_dashscope():
    from tasks.personal_recommendation import agent_runtime as recommendation_runtime
    text_config = recommendation_runtime.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        recommendation_runtime.get_personal_recommendation_agent.cache_clear()


def _graph_name() -> str:
    return (
        os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME")
        or os.getenv("SEARCH_TOOL_GRAPH_NAME")
        or "RAG"
    )


def _get_demo_syllabuses() -> list[Syllabus]:
    syllabuses: list[Syllabus] = []
    missing: list[int] = []
    for syllabus_id in DEMO_SYLLABUS_IDS:
        syllabus = Syllabus.query.filter_by(syllabus_id=syllabus_id).first()
        if syllabus is None:
            missing.append(syllabus_id)
        else:
            syllabuses.append(syllabus)
    if missing:
        pytest.skip(f"Missing configured demo syllabuses: {missing}; expected all of {DEMO_SYLLABUS_IDS}")
    return syllabuses


@pytest.fixture
def demo_db_env():
    _require_seed_demo_env()
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"demo_{suffix}",
            password_hash=generate_password_hash(DEMO_PASSWORD),
            email=f"demo_{suffix}@lianjue.example.com",
        )
        syllabuses = _get_demo_syllabuses()
        db.session.add(user)
        db.session.commit()
        relations = []
        for syllabus in syllabuses:
            relation = UserSyllabus(
                user_id=user.user_id,
                syllabus_id=syllabus.syllabus_id,
                syllabus_permission="user",
            )
            db.session.add(relation)
            relations.append(relation)
        db.session.commit()
        # NOTE: no teardown — demo users persist. Tests may rename user
        # (with explicit .user_name assignment + db.session.commit()).
        yield user, syllabuses, relations


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Profile input records
# ═══════════════════════════════════════════════════════════════════════════════

def _build_profile_input_records(level: str, now_ts: int, subject_title: str) -> dict:
    """Build profile input records for a given level.

    subject_title is always taken from Syllabus.title at the call site —
    no hardcoded fallback so every subject gets its real name.

    All *_offset_seconds are negative offsets from now_ts.
    """
    if level == LEVEL_LOW:
        return {
            "dialogue_text": [
                f"我刚接触{subject_title}，正在学课程导论部分。",
                f"对{subject_title}的基本概念有一些了解，想继续学下去。",
            ],
            "learning_goal": f"了解{subject_title}基本概念和核心框架",
            "learning_records": [
                {
                    "event_type": "study_session", "topic": f"{subject_title}课程导论",
                    "duration_minutes": 30, "status": "completed", "score": 0.72,
                    "started_at": now_ts - 2 * _DAY,
                    "meta": {"knowledge_points": [f"{subject_title}基础"]},
                },
                {
                    "event_type": "study_session", "topic": f"{subject_title}定义与特征",
                    "duration_minutes": 25, "status": "completed", "score": 0.68,
                    "started_at": now_ts - _DAY,
                    "meta": {"knowledge_points": [f"{subject_title}基础"]},
                },
            ],
            "answer_records": [
                {
                    "question": f"{subject_title}的核心概念有哪些？", "correct": True,
                    "time_spent_seconds": 60, "answered_at": now_ts - _DAY,
                    "meta": {"knowledge_points": [f"{subject_title}基础"]},
                },
            ],
            "resource_usage": [
                {
                    "resource_id": "doc-intro-001", "resource_type": "documents",
                    "action": "complete", "duration_seconds": 600,
                    "timestamp": now_ts - 2 * _DAY,
                    "meta": {"knowledge_points": [f"{subject_title}基础"]},
                },
            ],
        }
    elif level == LEVEL_LOW_MEDIUM:
        return {
            "dialogue_text": [
                f"我已经把{subject_title}前几讲过了一遍，但做题时经常把概念边界混在一起。",
                "我希望先把基础概念和典型例题串起来，再进入后面的模块。",
                "如果能给我一些短资料和针对性练习会更好。",
            ],
            "learning_goal": f"补齐{subject_title}基础概念并建立入门学习路径",
            "learning_records": [
                {"event_type": "study_session", "topic": f"{subject_title}导论复习", "duration_minutes": 35, "status": "completed", "score": 0.76, "started_at": now_ts - 2 * _WEEK, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"event_type": "practice", "topic": f"{subject_title}基础概念辨析", "duration_minutes": 28, "status": "completed", "score": 0.58, "started_at": now_ts - 11 * _DAY, "meta": {"knowledge_points": ["概念辨析"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心框架", "duration_minutes": 32, "status": "partial", "score": 0.52, "started_at": now_ts - _WEEK, "meta": {"knowledge_points": ["核心框架"]}},
                {"event_type": "practice", "topic": f"{subject_title}章节小测", "duration_minutes": 22, "status": "partial", "score": 0.46, "started_at": now_ts - 2 * _DAY, "meta": {"knowledge_points": ["章节小测"]}},
            ],
            "answer_records": [
                {"question": f"{subject_title}中最基础的三个概念分别是什么？", "correct": True, "time_spent_seconds": 95, "answered_at": now_ts - 11 * _DAY, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"question": "如何区分概念定义和应用场景？", "correct": False, "time_spent_seconds": 130, "answered_at": now_ts - 2 * _DAY, "meta": {"knowledge_points": ["概念辨析"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-foundation-001", "resource_type": "documents", "action": "complete", "duration_seconds": 720, "timestamp": now_ts - 13 * _DAY, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"resource_id": "quiz-foundation-001", "resource_type": "quiz", "action": "submit", "score": 0.55, "duration_seconds": 260, "timestamp": now_ts - 2 * _DAY, "meta": {"knowledge_points": ["概念辨析"]}},
            ],
        }
    elif level == LEVEL_MEDIUM:
        return {
            "dialogue_text": [
                f"我已经学完了{subject_title}的导论、基础概念和前几个核心模块。",
                "现在开始进入中段内容，能听懂讲解，但独立做题时还需要提示。",
                "希望能围绕当前薄弱模块生成学习计划和配套资料。",
            ],
            "learning_goal": f"系统掌握{subject_title}中段核心模块并补齐薄弱概念",
            "learning_records": [
                {"event_type": "study_session", "topic": f"{subject_title}课程导论", "duration_minutes": 40, "status": "completed", "score": 0.88, "started_at": now_ts - 6 * _WEEK, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"event_type": "study_session", "topic": f"{subject_title}基础概念", "duration_minutes": 35, "status": "completed", "score": 0.85, "started_at": now_ts - 5 * _WEEK, "meta": {"knowledge_points": ["基础概念"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心模块一", "duration_minutes": 35, "status": "completed", "score": 0.82, "started_at": now_ts - 4 * _WEEK, "meta": {"knowledge_points": ["核心模块一"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心模块二", "duration_minutes": 45, "status": "completed", "score": 0.86, "started_at": now_ts - 3 * _WEEK, "meta": {"knowledge_points": ["核心模块二"]}},
                {"event_type": "practice", "topic": f"{subject_title}模块二练习", "duration_minutes": 25, "status": "completed", "score": 0.80, "started_at": now_ts - 20 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
                {"event_type": "study_session", "topic": f"{subject_title}当前模块", "duration_minutes": 30, "status": "completed", "score": 0.72, "started_at": now_ts - 2 * _WEEK, "meta": {"knowledge_points": ["当前模块"]}},
                {"event_type": "study_session", "topic": f"{subject_title}拓展概念", "duration_minutes": 30, "status": "partial", "score": 0.48, "started_at": now_ts - 4 * _DAY, "meta": {"knowledge_points": ["拓展概念"]}},
            ],
            "answer_records": [
                {"question": f"{subject_title}核心模块二的关键步骤是什么？", "correct": True, "time_spent_seconds": 75, "answered_at": now_ts - 20 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
                {"question": "如何把基础概念迁移到标准例题中？", "correct": True, "time_spent_seconds": 90, "answered_at": now_ts - 26 * _DAY, "meta": {"knowledge_points": ["核心模块一"]}},
                {"question": "当前模块和前置模块的主要区别是什么？", "correct": True, "time_spent_seconds": 120, "answered_at": now_ts - 10 * _DAY, "meta": {"knowledge_points": ["当前模块"]}},
                {"question": "拓展概念适用于哪些复杂场景？", "correct": False, "time_spent_seconds": 110, "answered_at": now_ts - 2 * _DAY, "meta": {"knowledge_points": ["拓展概念"]}},
                {"question": f"{subject_title}基础概念之间有哪些依赖关系？", "correct": True, "time_spent_seconds": 65, "answered_at": now_ts - 32 * _DAY, "meta": {"knowledge_points": ["基础概念"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-subject-intro", "resource_type": "documents", "action": "complete", "duration_seconds": 800, "timestamp": now_ts - 40 * _DAY, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"resource_id": "doc-module-002", "resource_type": "documents", "action": "complete", "duration_seconds": 700, "timestamp": now_ts - 20 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
                {"resource_id": "quiz-module-002", "resource_type": "quiz", "action": "submit", "score": 0.82, "duration_seconds": 300, "timestamp": now_ts - 19 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
            ],
        }
    elif level == LEVEL_MEDIUM_HIGH:
        return {
            "dialogue_text": [
                f"我已经完成了{subject_title}的大部分基础模块，现在开始做综合题。",
                "单个知识点基本能理解，但遇到跨章节任务时需要更清晰的拆解路径。",
                "希望系统帮我定位薄弱点，并生成能复盘的资料。",
            ],
            "learning_goal": f"提升{subject_title}综合应用能力并补齐跨章节薄弱点",
            "learning_records": [
                {"event_type": "study_session", "topic": f"{subject_title}课程导论", "duration_minutes": 42, "status": "completed", "score": 0.9, "started_at": now_ts - 8 * _WEEK, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心框架", "duration_minutes": 38, "status": "completed", "score": 0.86, "started_at": now_ts - 7 * _WEEK, "meta": {"knowledge_points": ["核心框架"]}},
                {"event_type": "practice", "topic": f"{subject_title}案例分析", "duration_minutes": 45, "status": "completed", "score": 0.78, "started_at": now_ts - 5 * _WEEK, "meta": {"knowledge_points": ["案例分析"]}},
                {"event_type": "study_session", "topic": f"{subject_title}方法工具", "duration_minutes": 40, "status": "completed", "score": 0.74, "started_at": now_ts - 4 * _WEEK, "meta": {"knowledge_points": ["方法工具"]}},
                {"event_type": "practice", "topic": f"{subject_title}综合应用题", "duration_minutes": 50, "status": "partial", "score": 0.56, "started_at": now_ts - _WEEK, "meta": {"knowledge_points": ["综合应用"]}},
                {"event_type": "study_session", "topic": f"{subject_title}复习整理", "duration_minutes": 30, "status": "partial", "score": 0.6, "started_at": now_ts - 3 * _DAY, "meta": {"knowledge_points": ["复习策略"]}},
            ],
            "answer_records": [
                {"question": f"如何概括{subject_title}的核心学习框架？", "correct": True, "time_spent_seconds": 80, "answered_at": now_ts - 7 * _WEEK, "meta": {"knowledge_points": ["核心框架"]}},
                {"question": "案例题中如何从条件抽取关键概念？", "correct": True, "time_spent_seconds": 120, "answered_at": now_ts - 5 * _WEEK, "meta": {"knowledge_points": ["案例分析"]}},
                {"question": "跨章节综合题应该如何拆解？", "correct": False, "time_spent_seconds": 160, "answered_at": now_ts - _WEEK, "meta": {"knowledge_points": ["综合应用"]}},
                {"question": "如何安排阶段性复盘？", "correct": True, "time_spent_seconds": 90, "answered_at": now_ts - 3 * _DAY, "meta": {"knowledge_points": ["复习策略"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-framework-001", "resource_type": "documents", "action": "complete", "duration_seconds": 900, "timestamp": now_ts - 7 * _WEEK, "meta": {"knowledge_points": ["核心框架"]}},
                {"resource_id": "case-analysis-001", "resource_type": "practice", "action": "complete", "score": 0.78, "duration_seconds": 1200, "timestamp": now_ts - 5 * _WEEK, "meta": {"knowledge_points": ["案例分析"]}},
                {"resource_id": "quiz-integrated-001", "resource_type": "quiz", "action": "submit", "score": 0.56, "duration_seconds": 500, "timestamp": now_ts - _WEEK, "meta": {"knowledge_points": ["综合应用"]}},
            ],
        }
    else:  # HIGH
        return {
            "dialogue_text": [
                f"我已经完成了{subject_title}的大部分内容，包括基础、方法、案例和综合应用。",
                "对高阶综合问题和易错点还有疑惑，需要加强复习。",
                "希望针对弱项进行有重点的巩固练习。",
            ],
            "learning_goal": f"巩固{subject_title}核心知识，强化高阶综合应用与易错点",
            "learning_records": [
                {"event_type": "study_session", "topic": f"{subject_title}课程导论", "duration_minutes": 40, "status": "completed", "score": 0.91, "started_at": now_ts - 12 * _WEEK, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"event_type": "study_session", "topic": f"{subject_title}基础概念", "duration_minutes": 35, "status": "completed", "score": 0.87, "started_at": now_ts - 11 * _WEEK, "meta": {"knowledge_points": ["基础概念"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心模块一", "duration_minutes": 35, "status": "completed", "score": 0.84, "started_at": now_ts - 10 * _WEEK, "meta": {"knowledge_points": ["核心模块一"]}},
                {"event_type": "study_session", "topic": f"{subject_title}核心模块二", "duration_minutes": 45, "status": "completed", "score": 0.89, "started_at": now_ts - 9 * _WEEK, "meta": {"knowledge_points": ["核心模块二"]}},
                {"event_type": "practice", "topic": f"{subject_title}模块二练习", "duration_minutes": 30, "status": "completed", "score": 0.83, "started_at": now_ts - 8 * _WEEK, "meta": {"knowledge_points": ["核心模块二"]}},
                {"event_type": "study_session", "topic": f"{subject_title}当前模块", "duration_minutes": 45, "status": "completed", "score": 0.82, "started_at": now_ts - 7 * _WEEK, "meta": {"knowledge_points": ["当前模块"]}},
                {"event_type": "study_session", "topic": f"{subject_title}拓展概念", "duration_minutes": 35, "status": "completed", "score": 0.78, "started_at": now_ts - 6 * _WEEK + _HALF_DAY, "meta": {"knowledge_points": ["拓展概念"]}},
                {"event_type": "study_session", "topic": f"{subject_title}案例分析", "duration_minutes": 40, "status": "completed", "score": 0.75, "started_at": now_ts - 6 * _WEEK, "meta": {"knowledge_points": ["案例分析"]}},
                {"event_type": "study_session", "topic": f"{subject_title}可视化表达", "duration_minutes": 35, "status": "completed", "score": 0.80, "started_at": now_ts - 5 * _WEEK, "meta": {"knowledge_points": ["可视化表达"]}},
                {"event_type": "study_session", "topic": f"{subject_title}综合应用", "duration_minutes": 40, "status": "completed", "score": 0.76, "started_at": now_ts - 4 * _WEEK, "meta": {"knowledge_points": ["综合应用"]}},
                {"event_type": "study_session", "topic": f"{subject_title}高阶方法", "duration_minutes": 35, "status": "partial", "score": 0.48, "started_at": now_ts - 2 * _WEEK, "meta": {"knowledge_points": ["高阶方法"]}},
                {"event_type": "study_session", "topic": f"{subject_title}易错点归纳", "duration_minutes": 30, "status": "partial", "score": 0.42, "started_at": now_ts - 10 * _DAY, "meta": {"knowledge_points": ["易错点"]}},
                {"event_type": "study_session", "topic": f"{subject_title}综合复盘", "duration_minutes": 25, "status": "partial", "score": 0.38, "started_at": now_ts - _WEEK, "meta": {"knowledge_points": ["综合复盘"]}},
            ],
            "answer_records": [
                {"question": f"{subject_title}核心模块二和当前模块各自解决什么问题？", "correct": True, "time_spent_seconds": 70, "answered_at": now_ts - 8 * _WEEK, "meta": {"knowledge_points": ["核心模块二"]}},
                {"question": "如何把基础概念迁移到复杂案例中？", "correct": True, "time_spent_seconds": 85, "answered_at": now_ts - 9 * _WEEK, "meta": {"knowledge_points": ["核心模块一"]}},
                {"question": "拓展概念相比基础概念的适用边界是什么？", "correct": True, "time_spent_seconds": 80, "answered_at": now_ts - 6 * _WEEK, "meta": {"knowledge_points": ["拓展概念"]}},
                {"question": "案例分析中如何判断证据是否充分？", "correct": True, "time_spent_seconds": 95, "answered_at": now_ts - 38 * _DAY + _HALF_DAY, "meta": {"knowledge_points": ["案例分析"]}},
                {"question": "综合应用题的拆解流程是什么？", "correct": True, "time_spent_seconds": 90, "answered_at": now_ts - 24 * _DAY + _HALF_DAY, "meta": {"knowledge_points": ["综合应用"]}},
                {"question": "高阶方法应该如何选择？", "correct": False, "time_spent_seconds": 130, "answered_at": now_ts - 10 * _DAY, "meta": {"knowledge_points": ["高阶方法"]}},
                {"question": "如何识别综合题中的易错点？", "correct": False, "time_spent_seconds": 140, "answered_at": now_ts - _WEEK, "meta": {"knowledge_points": ["易错点"]}},
                {"question": "综合复盘时应该保留哪些证据？", "correct": False, "time_spent_seconds": 120, "answered_at": now_ts - 6 * _DAY, "meta": {"knowledge_points": ["综合复盘"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-intro-001", "resource_type": "documents", "action": "complete", "duration_seconds": 800, "timestamp": now_ts - 80 * _DAY, "meta": {"knowledge_points": [f"{subject_title}导论"]}},
                {"resource_id": "doc-module-002", "resource_type": "documents", "action": "complete", "duration_seconds": 700, "timestamp": now_ts - 59 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
                {"resource_id": "quiz-module-002", "resource_type": "quiz", "action": "submit", "score": 0.82, "duration_seconds": 300, "timestamp": now_ts - 58 * _DAY, "meta": {"knowledge_points": ["核心模块二"]}},
                {"resource_id": "doc-current-module", "resource_type": "documents", "action": "complete", "duration_seconds": 750, "timestamp": now_ts - 46 * _DAY, "meta": {"knowledge_points": ["当前模块"]}},
                {"resource_id": "mindmap-review-001", "resource_type": "mindmap", "action": "complete", "duration_seconds": 400, "timestamp": now_ts - 45 * _DAY, "meta": {"knowledge_points": ["综合复盘"]}},
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Recommendation + Plan seeding
# ═══════════════════════════════════════════════════════════════════════════════

def _tokenize_goal_text(*values: object) -> set[str]:
    """Copy from e2e_cases_large.py — tokenize for goal alignment."""
    raw = " ".join(str(value or "") for value in values)
    normalized = raw.lower()
    for char in "，。；;、/\\|:：()（）[]【】{}<>《》!?！？+-_":
        normalized = normalized.replace(char, " ")
    tokens = {part.strip() for part in normalized.split() if len(part.strip()) >= 2}
    for keyword in [
        "基础概念", "课程导论", "核心框架", "核心模块", "当前模块", "拓展概念",
        "案例分析", "综合应用", "高阶方法", "易错点", "复习策略", "证据检查",
    ]:
        if keyword.lower() in raw.lower():
            tokens.add(keyword.lower())
    return tokens


def _derive_graph_aligned_goals(recommendation: dict | None, user_goal_tokens: set[str], min_score: float = 1.5) -> dict:
    """Copy from e2e_cases_large.py — map tokenized goals to graph node outcomes."""
    recommendation = recommendation if isinstance(recommendation, dict) else {}
    graph = recommendation.get("graph") if isinstance(recommendation.get("graph"), dict) else {}
    rag_overlay = recommendation.get("rag_overlay") if isinstance(recommendation.get("rag_overlay"), dict) else {}
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    matched_nodes = {
        str(item.get("node_id")): item
        for item in (rag_overlay.get("matched_nodes") or [])
        if isinstance(item, dict) and item.get("node_id")
    }
    ranked = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        title = str(node.get("title") or "")
        outcomes = [str(item) for item in node.get("outcomes") or [] if str(item or "").strip()]
        evidence = matched_nodes.get(node_id) or node.get("rag_evidence") or {}
        evidence_entities = evidence.get("evidence_entities") if isinstance(evidence, dict) else []
        matched_by = evidence.get("matched_by") if isinstance(evidence, dict) else []
        node_tokens = _tokenize_goal_text(node_id, title, " ".join(outcomes), " ".join(evidence_entities or []), " ".join(matched_by or []))
        overlap = user_goal_tokens & node_tokens
        relevance = float(node.get("rag_relevance") or (evidence.get("relevance") if isinstance(evidence, dict) else 0) or 0)
        score = len(overlap) + relevance
        if overlap:
            score += 0.5
        ranked.append({
            "node_id": node_id, "title": title, "outcomes": outcomes,
            "score": round(score, 4), "overlap": sorted(overlap),
            "rag_relevance": relevance,
        })
    ranked.sort(key=lambda item: (item["score"], len(item["overlap"]), item["rag_relevance"]), reverse=True)
    best = ranked[0] if ranked else {}
    if not best or best.get("score", 0) < min_score or not best.get("overlap"):
        return {"goals": [], "selected_node": None, "ranked_nodes": ranked[:8], "reason": "no_semantically_aligned_syllabus_node", "min_score": min_score}
    return {"goals": (best.get("outcomes") or [best.get("title") or best.get("node_id")])[:2], "selected_node": best, "ranked_nodes": ranked[:8], "reason": "semantic_overlap_with_user_goal_or_rag_evidence", "min_score": min_score}


def _has_best_path(recommendation: dict | None) -> bool:
    if not isinstance(recommendation, dict):
        return False
    best_path = recommendation.get("best_path")
    return isinstance(best_path, dict) and bool(best_path.get("path"))


def _run_recommendation_for_demo(user_id: int, syllabus_id: int, graph_name: str, goals: list[str], learning_goal: str, question: str) -> dict:
    """Run real LLM recommendation with deterministic fallback, then save snapshot and accept plan."""
    _normalize_model_for_dashscope()
    payload = {
        "user_id": user_id, "syllabus_id": syllabus_id,
        "goals": goals, "question": question, "learning_goal": learning_goal,
        "graph_name": graph_name, "rag_top_k": 5,
        "decomposer_mode": "agent", "K": 10, "beam_width": 8,
    }
    # Step 1: LLM agent
    agent_result = prt.run_personal_recommendation_agent(payload)
    recommendation = agent_result.recommendation if isinstance(agent_result.recommendation, dict) else None
    flow = "agent"

    # Step 2: fallback via goal alignment
    if not _has_best_path(recommendation):
        user_goal_tokens = _tokenize_goal_text(question, learning_goal, " ".join(goals))
        goal_alignment = _derive_graph_aligned_goals(recommendation, user_goal_tokens)
        aligned_goals = goal_alignment.get("goals") or []
        if aligned_goals:
            aligned_payload = dict(payload)
            aligned_payload["goals"] = aligned_goals
            aligned_payload["goal_normalization_source"] = "syllabus_learning_tree"
            aligned_payload.pop("graph_name", None)
            aligned_payload.pop("rag_top_k", None)
            recommendation = prt.run_recommendation_route_from_payload(aligned_payload)
            flow = "deterministic_retry"
        else:
            return {"recommendation": None, "snapshot": None, "plan": None, "flow": "failed", "error": goal_alignment.get("reason")}

    if not _has_best_path(recommendation):
        return {"recommendation": recommendation, "snapshot": None, "plan": None, "flow": flow, "error": "no_best_path"}

    # Step 3: snapshot (proposed only — do NOT auto-accept; demo users should
    # see the candidate-selection UI before a plan is confirmed)
    snapshot = prt.save_recommendation_snapshot(user_id, syllabus_id, recommendation, request_payload=payload)
    return {"recommendation": recommendation, "snapshot": snapshot, "plan": None, "flow": flow}


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Study graph seeding
# ═══════════════════════════════════════════════════════════════════════════════

def _study_change(uid: int, sid: int, key: str, title: str, *, signal: str, summary: str, confidence: float = 0.9, parent_title: str = "", delta: float | None = None) -> dict:
    """Copy from e2e_cases_amend.py — build a single knowledge node change."""
    mastery: dict = {"signal": signal}
    if delta is not None:
        mastery["delta"] = delta
    change = {
        "op": "upsert_knowledge_node",
        "client_change_id": f"demo-seed:{uid}:{sid}:{key}",
        "knowledge": {"title": title, "summary": summary, "aliases": [title]},
        "mastery": mastery,
        "confidence": confidence,
    }
    if parent_title:
        change["parent_candidate"] = {"title": parent_title}
    return change


def _submit_study_batch(uid: int, sid: int, subject_title: str, changes: list[dict], *, timestamp: int, phase: str) -> dict:
    result = sgt.submit_learning_tree_changes(
        uid, sid, changes,
        source={"kind": "demo_student_seed", "phase": phase},
        timestamp=timestamp, subject_title=subject_title,
    )
    assert result["success"] is True
    return result


def _submit_study_batches_for_demo(uid: int, sid: int, subject_title: str, batches: list[dict], now_ts: int) -> dict:
    submit_results = []
    for batch in batches:
        ts = now_ts + int(batch.get("timestamp_offset_seconds") or 0)
        changes = [
            _study_change(
                uid, sid,
                str(c["key"]), str(c["title"]),
                signal=str(c["signal"]), summary=str(c["summary"]),
                confidence=float(c.get("confidence") or 0.9),
                parent_title=str(c.get("parent_title") or ""),
                delta=c.get("delta"),
            )
            for c in batch.get("changes") or []
        ]
        submit_results.append(
            _submit_study_batch(uid, sid, subject_title, changes, timestamp=ts, phase=str(batch["phase"]))
        )
    tree = sgt.get_student_learning_tree(uid, sid)
    features = sgt.get_learning_tree_features(uid, sid, stale_days=14)
    return {"tree": tree, "features": features, "submit_batches": submit_results, "node_count": len((tree.get("tree") or {}).get("nodes") or [])}


# ═══════════════════════════════════════════════════════════════════════════════
# Study graph batch data
# ═══════════════════════════════════════════════════════════════════════════════

LOW_STUDY_BATCHES = [
    {
        "phase": "first_contact",
        "timestamp_offset_seconds": -2 * _DAY,
        "changes": [
            {"key": "course_intro", "title": "课程导论", "signal": "learned", "summary": "刚开始建立课程整体印象"},
        ],
    },
    {
        "phase": "basic_terms",
        "timestamp_offset_seconds": - _DAY,
        "changes": [
            {"key": "basic_terms", "title": "基础术语", "signal": "struggled", "summary": "能记住部分术语，但概念边界还不稳定"},
        ],
    },
]

LOW_MEDIUM_STUDY_BATCHES = [
    {
        "phase": "intro_review",
        "timestamp_offset_seconds": -2 * _WEEK,
        "changes": [
            {"key": "course_intro", "title": "课程导论", "signal": "mastered", "summary": "完成导论复习，能说出课程主要模块"},
            {"key": "basic_terms", "title": "基础术语", "signal": "practiced", "summary": "通过短测练习过基础术语"},
        ],
    },
    {
        "phase": "concept_boundary",
        "timestamp_offset_seconds": - _WEEK,
        "changes": [
            {"key": "concept_boundary", "title": "概念边界", "signal": "struggled", "summary": "做题时容易混淆相近概念的定义和适用场景"},
        ],
    },
    {
        "phase": "framework_start",
        "timestamp_offset_seconds": -2 * _DAY,
        "changes": [
            {"key": "core_framework", "title": "核心框架", "signal": "learned", "summary": "开始把章节知识串成框架", "parent_title": "课程导论"},
        ],
    },
]

MEDIUM_STUDY_BATCHES = [
    {
        "phase": "mastered_foundations",
        "timestamp_offset_seconds": -3 * _WEEK,
        "changes": [
            {"key": "course_foundation", "title": "课程基础", "signal": "mastered", "summary": "对课程基础概念有稳定理解"},
            {"key": "core_module_1", "title": "核心模块一", "signal": "mastered", "summary": "掌握第一个核心模块的基本结构和常见题型"},
        ],
    },
    {
        "phase": "core_module_practice",
        "timestamp_offset_seconds": -2 * _WEEK,
        "changes": [
            {"key": "core_module_2", "title": "核心模块二", "signal": "mastered", "summary": "理解第二个核心模块的关键概念和流程"},
            {"key": "standard_practice", "title": "标准练习", "signal": "practiced", "summary": "能完成标准例题，但迁移到新场景时仍需提示"},
        ],
    },
    {
        "phase": "current_module_start",
        "timestamp_offset_seconds": -4 * _DAY,
        "changes": [
            {"key": "current_module", "title": "当前模块", "signal": "struggled", "summary": "对当前模块与前置模块的关系感到困惑"},
        ],
    },
    {
        "phase": "current_module_detail",
        "timestamp_offset_seconds": -3 * _DAY,
        "changes": [
            {"key": "current_module_detail", "title": "当前模块细节", "signal": "learned", "summary": "开始理解当前模块的内部结构和关键步骤", "parent_title": "当前模块"},
        ],
    },
    {
        "phase": "practice_detail",
        "timestamp_offset_seconds": -20 * _DAY,
        "changes": [
            {"key": "practice_detail", "title": "练习拆解", "signal": "practiced", "summary": "熟悉标准题目的拆解步骤和检查方法"},
        ],
    },
]

MEDIUM_HIGH_STUDY_BATCHES = [
    {
        "phase": "foundation_mastered",
        "timestamp_offset_seconds": -6 * _WEEK,
        "changes": [
            {"key": "course_intro", "title": "课程导论", "signal": "mastered", "summary": "课程整体结构已经稳定掌握"},
            {"key": "core_framework", "title": "核心框架", "signal": "mastered", "summary": "能把核心模块和应用场景建立对应关系"},
        ],
    },
    {
        "phase": "applied_practice",
        "timestamp_offset_seconds": -4 * _WEEK,
        "changes": [
            {"key": "case_analysis", "title": "案例分析", "signal": "practiced", "summary": "已经通过案例练习过知识迁移"},
            {"key": "tool_method", "title": "方法工具", "signal": "learned", "summary": "能使用部分方法解决标准题目"},
        ],
    },
    {
        "phase": "advanced_weakness",
        "timestamp_offset_seconds": - _WEEK,
        "changes": [
            {"key": "advanced_integration", "title": "综合应用", "signal": "struggled", "summary": "跨章节综合题仍需要拆解提示"},
            {"key": "review_strategy", "title": "复习策略", "signal": "learned", "summary": "开始按薄弱主题安排复习", "parent_title": "综合应用"},
        ],
    },
]

HIGH_STUDY_BATCHES = [
    {
        "phase": "stale_history",
        "timestamp_offset_seconds": -60 * _DAY,
        "changes": [
            {"key": "early_core_module", "title": "早期核心模块", "signal": "mastered", "summary": "较早完成过早期核心模块学习"},
        ],
    },
    {
        "phase": "mastered_foundations_0",
        "timestamp_offset_seconds": -8 * _WEEK,
        "changes": [
            {"key": "course_foundation", "title": "课程基础", "signal": "mastered", "summary": "多次学习与测验后已较稳定"},
            {"key": "concept_system", "title": "概念体系", "signal": "mastered", "summary": "对基础概念之间的依赖关系有清晰理解"},
        ],
    },
    {
        "phase": "mastered_foundations_1",
        "timestamp_offset_seconds": -7 * _WEEK,
        "changes": [
            {"key": "core_module_1", "title": "核心模块一", "signal": "mastered", "summary": "掌握核心模块一的完整流程"},
            {"key": "core_module_2", "title": "核心模块二", "signal": "mastered", "summary": "已通过多次练习巩固核心模块二"},
        ],
    },
    {
        "phase": "mastered_foundations_2",
        "timestamp_offset_seconds": -6 * _WEEK,
        "changes": [
            {"key": "current_module", "title": "当前模块", "signal": "mastered", "summary": "对当前模块的基础概念和结构有较好掌握"},
            {"key": "extension_concepts", "title": "拓展概念", "signal": "mastered", "summary": "理解拓展概念与基础概念的对比和适用场景"},
        ],
    },
    {
        "phase": "active_step_foundation",
        "timestamp_offset_seconds": -20 * _DAY,
        "stale_timestamp_offset_seconds": -30 * _DAY,
        "changes": [
            {"key": "current_module_detail", "title": "当前模块细节", "signal": "mastered", "summary": "理解当前模块的细节结构、关键步骤和常见变体", "parent_title": "当前模块"},
        ],
    },
    {
        "phase": "application_branch",
        "timestamp_offset_seconds": -2 * _WEEK,
        "changes": [
            {"key": "case_analysis", "title": "案例分析", "signal": "learned", "summary": "能理解部分案例条件，但对复杂场景的关键线索识别不足", "parent_title": "当前模块细节"},
            {"key": "solution_design", "title": "方案设计", "signal": "learned", "summary": "了解方案设计需要平衡目标、约束和证据", "parent_title": "当前模块细节"},
        ],
    },
    {
        "phase": "weakness_branch",
        "timestamp_offset_seconds": -10 * _DAY,
        "changes": [
            {"key": "advanced_integration", "title": "高阶综合应用", "signal": "struggled", "summary": "对跨章节条件整合和策略选择理解不足", "parent_title": "案例分析"},
        ],
    },
    {
        "phase": "review_branch",
        "timestamp_offset_seconds": - _WEEK,
        "changes": [
            {"key": "review_strategy", "title": "复习策略", "signal": "struggled", "summary": "复习范围和优先级判断仍不稳定", "parent_title": "方案设计"},
            {"key": "mistake_summary", "title": "易错点归纳", "signal": "learned", "summary": "开始整理常见错因和触发条件", "parent_title": "高阶综合应用"},
            {"key": "evidence_check", "title": "证据检查", "signal": "learned", "summary": "了解用证据检查结论是否可靠的方法", "parent_title": "高阶综合应用"},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: Resource generation
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_demo_resource(user_id: int, syllabus_id: int, step: dict, graph_name: str, resource_type: str) -> dict:
    topic = step.get("title") or step.get("node_id") or "current learning step"
    outcomes = step.get("outcomes") if isinstance(step.get("outcomes"), list) else []
    result = generate_resources_from_request({
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "question": f"请为 {topic} 生成学习资料，帮助学生深入理解并完成练习。",
        "topic": topic,
        "learning_objectives": outcomes,
        "resource_types": [resource_type],
        "graph_name": graph_name,
        "generation_requirements": {},
    })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5: Summary output
# ═══════════════════════════════════════════════════════════════════════════════

def _write_demo_summary_entry(entry: dict) -> None:
    DEMO_SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path = DEMO_SUMMARY_ROOT / "summary.json"
    existing: list[dict] = []
    if summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            existing = []
    # dedupe by level — keep latest
    existing = [e for e in existing if e.get("level") != entry["level"]]
    existing.append(entry)
    existing.sort(key=lambda e: e.get("created_at", 0))
    summary_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _active_step_from_recommendation(recommendation: dict) -> dict:
    best_path = recommendation.get("best_path") if isinstance(recommendation, dict) else {}
    path_node_ids = best_path.get("path") if isinstance(best_path, dict) else []
    graph_nodes = recommendation.get("graph", {}).get("nodes") if isinstance(recommendation, dict) else []
    node_by_id = {n.get("id"): n for n in (graph_nodes or []) if isinstance(n, dict)}
    first_node = node_by_id.get(path_node_ids[0]) if path_node_ids else None
    active_step = {
        "step_id": "seed-step-0",
        "node_id": path_node_ids[0] if path_node_ids else "",
        "title": (first_node.get("title") if isinstance(first_node, dict) else "") or (path_node_ids[0] if path_node_ids else ""),
        "outcomes": (first_node.get("outcomes") if isinstance(first_node, dict) else []) or [],
        "order_index": 0,
        "status": "active",
    } if path_node_ids else {}
    assert active_step, "No active step derived from best_path"
    return active_step


def _level_config(level: str, subject_title: str) -> dict:
    if level == LEVEL_LOW:
        return {
            "batches": LOW_STUDY_BATCHES,
            "min_nodes": 2,
            "resource_type": "documents",
            "goals": [f"{subject_title}基础概念", f"{subject_title}课程导论"],
            "question": f"我刚开始学习{subject_title}，想从基础概念和课程导论开始建立学习路径。",
        }
    if level == LEVEL_LOW_MEDIUM:
        return {
            "batches": LOW_MEDIUM_STUDY_BATCHES,
            "min_nodes": 4,
            "resource_type": "quiz",
            "goals": [f"{subject_title}概念辨析", f"{subject_title}核心框架"],
            "question": f"我已经学过{subject_title}前几讲，但基础概念容易混淆，希望先补齐概念边界。",
        }
    if level == LEVEL_MEDIUM:
        return {
            "batches": MEDIUM_STUDY_BATCHES,
            "min_nodes": 5,
            "resource_type": "documents",
            "goals": [f"{subject_title}核心模块", f"{subject_title}方法应用"],
            "question": f"我想深入学习{subject_title}的核心模块和典型应用，形成下一阶段学习计划。",
        }
    if level == LEVEL_MEDIUM_HIGH:
        return {
            "batches": MEDIUM_HIGH_STUDY_BATCHES,
            "min_nodes": 6,
            "resource_type": "ppt",
            "goals": [f"{subject_title}综合应用", f"{subject_title}案例分析"],
            "question": f"我已经学完{subject_title}多数基础内容，想针对综合应用和跨章节题目继续提升。",
        }
    return {
        "batches": HIGH_STUDY_BATCHES,
        "min_nodes": 10,
        "resource_type": "mindmap",
        "goals": [f"{subject_title}高阶综合应用", f"{subject_title}易错点复习"],
        "question": f"我已经完成{subject_title}大部分内容，想针对高阶综合应用和易错点进行复习巩固。",
    }


def _seed_demo_level_for_subject(user: User, syllabus: Syllabus, level: str, now_ts: int, graph_name: str) -> dict:
    subject_title = syllabus.title or f"学科 {syllabus.syllabus_id}"
    config = _level_config(level, subject_title)

    records = _build_profile_input_records(level, now_ts, subject_title)
    profile = lpt.get_or_build_learning_profile(
        user.user_id, syllabus.syllabus_id, refresh_profile=True,
        dialogue_text=records["dialogue_text"], learning_goal=records["learning_goal"],
        learning_records=records["learning_records"], answer_records=records["answer_records"],
        resource_usage=records["resource_usage"],
    )
    assert isinstance(profile, dict), f"profile must be dict, got {type(profile)}"
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(persisted, dict) and persisted.get("profile_saved") is True

    rec_result = _run_recommendation_for_demo(
        user.user_id, syllabus.syllabus_id, graph_name,
        goals=config["goals"],
        learning_goal=records["learning_goal"],
        question=config["question"],
    )
    assert rec_result["recommendation"] is not None, f"Recommendation failed: {rec_result.get('error')}"
    active_step = _active_step_from_recommendation(rec_result["recommendation"])

    graph_result = _submit_study_batches_for_demo(
        user.user_id, syllabus.syllabus_id, subject_title,
        config["batches"], now_ts,
    )
    assert graph_result["node_count"] >= config["min_nodes"], (
        f"Expected >={config['min_nodes']} nodes for {level}/{syllabus.syllabus_id}, "
        f"got {graph_result['node_count']}"
    )

    resource_result = _generate_demo_resource(
        user.user_id, syllabus.syllabus_id, active_step, graph_name, config["resource_type"],
    )
    assert resource_result.get("success") is True, f"Resource generation failed: {resource_result.get('error_message')}"
    resource_id = (resource_result.get("resources") or [{}])[0].get("resource_id") if resource_result.get("resources") else None
    snapshot_id = (rec_result.get("snapshot") or {}).get("recommendation_id")

    return {
        "syllabus_id": syllabus.syllabus_id,
        "subject_title": subject_title,
        "profile_path": persisted.get("profile_path"),
        "learning_plan_id": None,
        "recommendation_snapshot_id": snapshot_id,
        "study_graph_node_count": graph_result["node_count"],
        "generated_resource_id": resource_id,
        "generated_resource_type": config["resource_type"],
        "current_step_title": active_step.get("title"),
    }


def _seed_demo_student(level: str, demo_db_env) -> None:
    user, syllabuses, _relations = demo_db_env
    now_ts = int(time.time())
    user.user_name = f"demo_{level}_{uuid.uuid4().hex[:8]}"
    user.email = f"{user.user_name}@lianjue.example.com"
    db.session.commit()
    graph_name = _graph_name()

    subject_entries = [
        _seed_demo_level_for_subject(user, syllabus, level, now_ts, graph_name)
        for syllabus in syllabuses
    ]

    _write_demo_summary_entry({
        "level": level,
        "user_id": user.user_id,
        "user_name": user.user_name,
        "syllabus_ids": [entry["syllabus_id"] for entry in subject_entries],
        "password": DEMO_PASSWORD,
        "subjects": subject_entries,
        "created_at": now_ts,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Test functions
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_low_student(monkeypatch, demo_db_env):
    """Low-progress student: full real chain for every configured subject."""
    _seed_demo_student(LEVEL_LOW, demo_db_env)


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_low_medium_student(monkeypatch, demo_db_env):
    """Low-medium student: full real chain for every configured subject."""
    _seed_demo_student(LEVEL_LOW_MEDIUM, demo_db_env)


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_medium_student(monkeypatch, demo_db_env):
    """Medium student: full real chain for every configured subject."""
    _seed_demo_student(LEVEL_MEDIUM, demo_db_env)


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_medium_high_student(monkeypatch, demo_db_env):
    """Medium-high student: full real chain for every configured subject."""
    _seed_demo_student(LEVEL_MEDIUM_HIGH, demo_db_env)


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_high_student(monkeypatch, demo_db_env):
    """High student: full real chain for every configured subject."""
    _seed_demo_student(LEVEL_HIGH, demo_db_env)
