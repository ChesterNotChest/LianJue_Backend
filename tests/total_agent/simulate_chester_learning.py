"""Chester 模拟学习脚本 — 驱动 total_agent 进行 100+ 轮真实对话。

不需要启动 Flask——脚本内建 app context，直接调 run_total_agent。

运行方式:
  # 完整模拟
  RUN_LLM_TESTS=1 RUN_DB_TESTS=1 python tests/total_agent/simulate_chester_learning.py

  # 干跑测试（只发一条消息验证链路）
  RUN_LLM_TESTS=1 RUN_DB_TESTS=1 python tests/total_agent/simulate_chester_learning.py --dry-run

前提: Chester (user_id=1) 存在，绑定了学科 8/18/104。
效果: 每个学科走完 推荐→确认→逐步学习 流程，study_graph + buddy_tree + profile 自然生长。

所有原始响应写入 logs/chester_sim_{timestamp}.jsonl，方便出问题后排查。
"""

import json
import os
import sys
import time
import uuid
import traceback
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIM] %(message)s")
logger = logging.getLogger("chester_sim")

os.environ["FLASK_APP"] = "app.py"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app import create_app

USER_ID = 1
SUBJECTS = [
    (8, "大数据概论"),
    (18, "算法设计与分析"),
    (104, "软件系统设计与分析"),
]

MAX_STEPS_PER_SUBJECT = 8
WEAK_POINT_EVERY_N = 2
CASUAL_CHAT_EVERY_N = 4
MAX_TOTAL_TURNS = 150
TURN_DELAY_SECONDS = 3
RETRY_MAX = 2

# ── 日志文件 ──
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
RESPONSE_LOG = LOG_DIR / f"chester_sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

# ── 反馈模板 ──
COMPLETE_TEMPLATES = [
    "我完成了「{title}」的学习，掌握得不错，大概{score}分",
    "刚把「{title}」学完了，感觉理解得比较扎实，打个{score}分吧",
    "「{title}」这部分啃下来了，做练习正确率还行，给{score}分",
    "花了点时间把「{title}」过了一遍，大致掌握了，{score}分",
]
WEAK_TEMPLATES = [
    "不过「{weak}」这块感觉还不太熟，可能只有{score}分，概念有点模糊",
    "但「{weak}」这部分有点卡，边界条件经常弄混，大概{score}分水平",
    "「{weak}」这个点反复看了几遍还是不太确定，{score}分吧",
]
CASUAL_TEMPLATES = [
    "今天状态还行，学得进去",
    "刚才回头翻了翻前几节的笔记，感觉串起来了",
    "说实话我有点累了，但还能再整一段",
    "对了，我感觉比起做题，看文档理解得更快",
    "你有没有觉得这个学科蛮有意思的",
]


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _log_response(turn: int, subject: str, phase: str, message: str, result: dict) -> None:
    try:
        entry = {
            "turn": turn,
            "subject": subject,
            "phase": phase,
            "message": message[:300],
            "success": result.get("success"),
            "intent": result.get("intent", ""),
            "suggested_next_action": result.get("suggested_next_action", ""),
            "error_code": result.get("error_code", ""),
            "error_message": result.get("error_message", ""),
            "buddy_message": result.get("buddy_message", "")[:200],
            "tool_trace": result.get("tool_trace", []),
            "result_keys": list(_safe_dict(result.get("result")).keys()) if result.get("result") else [],
            "timestamp": int(time.time()),
        }
        with open(RESPONSE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def send_message(
    app,
    user_id: int,
    syllabus_id: int,
    message: str,
    session_id: str,
    intent_hint: str = "",
) -> dict:
    """向 total_agent 发一条消息，带重试。返回 final result dict。"""
    from tasks.total_agent.agent_runtime import run_total_agent

    payload = {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "session_id": session_id,
        "message": message,
    }
    if intent_hint:
        payload["intent"] = intent_hint

    last_error = ""
    for attempt in range(1, RETRY_MAX + 1):
        try:
            with app.app_context():
                result = run_total_agent(payload, use_llm=True)
            if isinstance(result, dict):
                return result
            last_error = f"unexpected type: {type(result).__name__}"
        except Exception as e:
            last_error = str(e)
            if attempt < RETRY_MAX:
                logger.warning("  重试 %s/%s: %s", attempt, RETRY_MAX, last_error[:100])
                time.sleep(5)

    logger.error("  发送失败: %s", last_error[:200])
    return {"success": False, "error_message": last_error}


def parse_next_task(result: dict) -> Optional[dict]:
    """从 Agent 响应中提取下一步任务。"""
    inner = _safe_dict(result.get("result"))
    for key in ("accept_learning_plan", "record_learning_feedback",
                "skip_current_step", "resource_generation", "next_task"):
        sub = _safe_dict(inner.get(key))
        nt = _safe_dict(sub.get("next_task"))
        if nt.get("title"):
            return nt
    nt = _safe_dict(inner.get("next_task"))
    return nt if nt.get("title") else None


def _random_session_id() -> str:
    return f"chester_sim_{uuid.uuid4().hex[:12]}"


def has_best_path(result: dict) -> bool:
    inner = _safe_dict(result.get("result"))
    rec = _safe_dict(inner.get("recommendation"))
    return bool(rec.get("has_best_path") or rec.get("best_path"))


def get_buddy_message(result: dict) -> str:
    return _safe_text(result.get("buddy_message"))


def _agent_reply(result: dict) -> str:
    """从 result 中提取 Agent 回复文本。"""
    inner = _safe_dict(result.get("result"))
    # 直接 reply 字段
    r = _safe_text(inner.get("reply"))
    if r: return r[:200]
    # learning_guidance
    g = _safe_dict(inner.get("learning_guidance"))
    r = _safe_text(g.get("reply"))
    if r: return r[:200]
    # answer
    a = _safe_dict(inner.get("answer_learning_question"))
    ans = _safe_dict(a.get("answer"))
    r = _safe_text(ans.get("text") or a.get("text"))
    if r: return r[:200]
    # resource_generation
    rg = _safe_dict(inner.get("resource_generation"))
    r = _safe_text(rg.get("reply"))
    if r: return r[:200]
    return ""


def _record_turn(turn_no: int, subject: str, phase: str, message: str, result: dict) -> None:
    """将本轮对话写入 JSONL 日志。"""
    try:
        inner = _safe_dict(result.get("result"))
        nt = parse_next_task(result)
        entry = {
            "turn": turn_no,
            "subject": subject,
            "phase": phase,
            "message": message[:300],
            "success": result.get("success"),
            "intent": result.get("intent", ""),
            "suggested_next_action": result.get("suggested_next_action", ""),
            "next_task": nt.get("title") if nt else "",
            "buddy": get_buddy_message(result)[:200],
            "tool_trace": result.get("tool_trace", []),
            "result_keys": list(inner.keys()) if inner else [],
            "error": result.get("error_code") or result.get("error_message") or "",
            "ts": int(time.time()),
        }
        with open(RESPONSE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def simulate_subject(
    app,
    user_id: int,
    syllabus_id: int,
    subject_title: str,
    session_id: str,
) -> int:
    """推着往前走——有活跃计划就接着学，没计划就求推荐，计划完了接新计划。"""
    turns = 0
    seq = [0]
    step_idx = 0
    seen_titles = set()

    def _say(msg: str, phase: str, intent: str = "") -> dict:
        nonlocal turns
        result = send_message(app, user_id, syllabus_id, msg, session_id, intent)
        turns += 1
        seq[0] += 1
        _record_turn(seq[0], subject_title, phase, msg, result)
        reply = _agent_reply(result)
        if reply:
            logger.info("[%s] 💬 Agent: %s", subject_title, reply[:120])
        buddy = get_buddy_message(result)
        if buddy:
            logger.info("[%s] 🦊 小觉: %s", subject_title, buddy[:120])
        time.sleep(TURN_DELAY_SECONDS)
        return result

    import random

    # ── 第一步：问进度，不预设状态 ──────────────────────────
    logger.info("[%s] 启动: 询问当前学习状态", subject_title)
    result = _say(f"我想学{subject_title}，帮我看看现在是什么进度", "start")

    # 如果有活跃计划，直接取 next_task
    next_task = parse_next_task(result)
    suggested = _safe_text(result.get("suggested_next_action", ""))

    # 如果 Agent 推荐了路径，就接受
    if not next_task and suggested == "wait_user_acceptance":
        logger.info("[%s] Agent 推了推荐，接受", subject_title)
        result = _say("好的，确认采用第一个推荐路径，帮我开始学习", "accept", "accept_recommendation")
        next_task = parse_next_task(result)

    # 如果还是没有下一步，明确要求推荐
    if not next_task:
        logger.info("[%s] 没有活跃任务，请求推荐", subject_title)
        result = _say(
            f"我想系统学习{subject_title}，帮我从头规划一条学习路径",
            "recommend",
        )
        if has_best_path(result):
            result = _say("就选第一个，开始学", "accept", "accept_recommendation")
            next_task = parse_next_task(result)

    # ── 主循环：一直学，直到达到上限 ──────────────────────────
    while turns < MAX_TOTAL_TURNS and step_idx < MAX_STEPS_PER_SUBJECT * 3:
        if not next_task:
            suggested = _safe_text(result.get("suggested_next_action", ""))
            # 计划完成了——Agent 推了新推荐
            if suggested == "wait_user_acceptance":
                logger.info("[%s] 计划完成，接受新推荐继续", subject_title)
                result = _say("确认采纳推荐路径，帮我开始学习计划", "accept_next", "accept_recommendation")
                next_task = parse_next_task(result)
                if next_task:
                    seen_titles.clear()
                    continue
            # 试试问下一步
            logger.info("[%s] 问下一步", subject_title)
            result = _say("下一步学什么？帮我继续推进", "get_next")
            next_task = parse_next_task(result)
            if not next_task:
                # 可能真的学完了所有推荐路径
                result = _say(f"还有没有{subject_title}相关的其他路径？帮我再推荐一条", "request_more")
                if has_best_path(result):
                    result = _say("就这个，继续", "accept_more", "accept_recommendation")
                    next_task = parse_next_task(result)
                if not next_task:
                    logger.info("[%s] 没有更多路径了，结束", subject_title)
                    break

        step_title = _safe_text(next_task.get("title"))
        if not step_title or step_title in seen_titles:
            next_task = None  # 强制下一轮重新找路
            continue
        seen_titles.add(step_title)
        step_idx += 1

        score = random.randint(78, 92)
        template = random.choice(COMPLETE_TEMPLATES)
        msg = template.format(title=step_title, score=score)

        if step_idx % WEAK_POINT_EVERY_N == 0:
            weak = random.choice(WEAK_TEMPLATES)
            weak_score = random.randint(30, 48)
            msg += "。" + weak.format(weak=step_title, score=weak_score)

        logger.info("[%s] Step %s: %s", subject_title, step_idx, msg[:80].replace('\n', ' '))
        result = _say(msg, f"step_{step_idx}", "record_learning_feedback")
        next_task = parse_next_task(result)

        if step_idx % CASUAL_CHAT_EVERY_N == 0 and turns < MAX_TOTAL_TURNS:
            _say(random.choice(CASUAL_TEMPLATES), "casual")

    logger.info("[%s] 完成: %s步, %s轮", subject_title, step_idx, turns)
    return turns


def main():
    dry_run = "--dry-run" in sys.argv
    app = create_app()

    logger.info("响应日志: %s", RESPONSE_LOG)
    logger.info("模式: %s", "干跑测试" if dry_run else "完整模拟")

    with app.app_context():
        from schemas.user import User
        chester = User.query.get(USER_ID)
        if not chester:
            logger.error("Chester (user_id=%s) 不存在", USER_ID)
            return
        logger.info("Chester 就绪: %s", chester.user_name)


    if dry_run:
        logger.info("═══ 干跑: 发一条测试消息 ═══")
        sid = _random_session_id()
        result = send_message(app, USER_ID, SUBJECTS[0][0],
                              "你好，我想了解一下我目前的学习进度", sid)
        logger.info("success=%s intent=%s suggested=%s error=%s",
                     result.get("success"), result.get("intent", ""),
                     result.get("suggested_next_action", ""),
                     result.get("error_code") or result.get("error_message") or "无")
        logger.info("result_keys=%s", list(_safe_dict(result.get("result")).keys()))
        _record_turn(1, SUBJECTS[0][1], "dry_run", "你好，我想了解一下我目前的学习进度", result)
        logger.info("干跑完成，检查上面的输出是否正常。日志: %s", RESPONSE_LOG)
        return

    total_turns = 0
    sessions = {}

    for sid, title in SUBJECTS:
        if total_turns >= MAX_TOTAL_TURNS:
            logger.info("已达总轮数上限 %s", MAX_TOTAL_TURNS)
            break

        session_id = _random_session_id()
        sessions[sid] = session_id
        logger.info("══════════ 开始 %s (syllabus %s) ══════════", title, sid)

        try:
            turns = simulate_subject(app, USER_ID, sid, title, session_id)
            total_turns += turns
            logger.info("[%s] 完成，%s 轮对话", title, turns)
        except Exception:
            logger.exception("[%s] 模拟失败", title)

    # ── 汇总 ────────────────────────────────────────────────
    logger.info("══════════ 全部完成 ══════════")
    logger.info("总对话轮数: %s", total_turns)
    logger.info("学科会话: %s", json.dumps(sessions, ensure_ascii=False))

    # 打印最终状态
    with app.app_context():
        from tasks.study_graph.service import get_student_learning_tree
        from tasks.study_buddy.tree_store import load_buddy_tree
        for sid, title in SUBJECTS:
            tree = get_student_learning_tree(USER_ID, sid)
            nodes = len(tree.get("tree", {}).get("nodes", [])) if tree.get("success") else 0
            bt = load_buddy_tree(USER_ID, sid)
            bn = len(bt.get("nodes", {})) if bt else 0
            bnotes = sum(len(n.get("buddy_notes", [])) for n in (bt.get("nodes", {}).values() if bt else []))
            logger.info("[%s] study_graph_nodes=%s  buddy_nodes=%s  buddy_notes=%s",
                         title, nodes, bn, bnotes)


if __name__ == "__main__":
    main()
