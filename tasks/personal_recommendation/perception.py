import json
import os
import re

STUDY_GRAPH_STATE_COMPLETED = "completed"
STUDY_GRAPH_STATE_BLOCKED = "blocked"
STUDY_GRAPH_STATE_WEAK = "weak"
STUDY_GRAPH_STATE_CURRENT = "current"

_ALIGN_CACHE: dict = {}


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _tokenize(text):
    """Lightweight token set for Chinese + English mixed text."""
    tokens = set()
    for m in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", text):
        if len(m) >= 2:
            tokens.add(m.lower())
    chinese = re.findall(r"[一-鿿]+", text)
    for chunk in chinese:
        for i in range(len(chunk) - 1):
            tokens.add(chunk[i:i+2])
        if len(chunk) <= 8:
            tokens.add(chunk)
    return tokens


def _fuzzy_match_score(candidate, knowledge):
    """Return (score, matched_key) for a single candidate against knowledge dict.

    Tries exact → substring → token-overlap, same as graph_builder.py.
    """
    if not candidate or not knowledge:
        return 0.0, ""
    # 1) exact
    if candidate in knowledge:
        return _safe_float(knowledge[candidate]), candidate
    # 2) substring
    cl = candidate.lower()
    best = 0.0
    best_key = ""
    for key, value in knowledge.items():
        kl = key.lower()
        if kl in cl or cl in kl:
            v = _safe_float(value)
            if v > best:
                best = v
                best_key = key
    if best > 0:
        return best, best_key
    # 3) token overlap
    ct = _tokenize(candidate)
    if not ct:
        return 0.0, ""
    for key, value in knowledge.items():
        kt = _tokenize(key)
        if ct & kt:
            v = _safe_float(value)
            if v > best:
                best = v
                best_key = key
    return best, best_key


def _normalize_knowledge_levels(user_profile):
    knowledge = user_profile.get('knowledge_levels', {})
    if isinstance(knowledge, dict) and knowledge:
        return knowledge

    mastery = user_profile.get('knowledge_mastery', {})
    if not isinstance(mastery, dict):
        return {}

    details = mastery.get('knowledge_point_details', {})
    if isinstance(details, dict) and details:
        normalized = {}
        for key, item in details.items():
            if isinstance(item, dict) and item.get('score') is not None:
                normalized[str(key)] = item.get('score')
        if normalized:
            return normalized

    by_point = mastery.get('by_knowledge_point', {})
    if isinstance(by_point, dict):
        return by_point
    return {}


def _llm_align_knowledge(knowledge, learning_tree):
    """Use LLM to semantically align knowledge_point tags with node descriptions.

    Returns an enriched copy of *knowledge* with additional entries keyed by
    node outcome / title strings that the LLM matched to a knowledge_point tag.
    The rule-based ``_fuzzy_match_score`` remains the primary path; this is a
    semantic fallback for pairs that share no lexical overlap.
    """
    if os.getenv("KNOWLEDGE_ALIGN_LLM_ENABLED") == "0":
        return knowledge
    if not knowledge or not learning_tree:
        return knowledge

    # -- cache key -----------------------------------------------------------------
    kp_keys = frozenset(knowledge.keys())
    node_titles = frozenset(
        n.get("title") or ""
        for n in learning_tree.values()
        if isinstance(n, dict)
    )
    cache_key = hash((kp_keys, node_titles))
    cached = _ALIGN_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # -- build prompt --------------------------------------------------------------
    tag_lines = "\n".join(
        f"- {k}" for k, v in knowledge.items() if v > 0
    )
    if not tag_lines:
        _ALIGN_CACHE[cache_key] = knowledge
        return knowledge

    node_lines = []
    for nid, n in learning_tree.items():
        if not isinstance(n, dict):
            continue
        title = str(n.get("title") or "")
        outcomes = [str(o) for o in (n.get("outcomes") or []) if o]
        desc = title
        if outcomes:
            desc += "; " + "; ".join(outcomes[:3])
        if desc.strip():
            node_lines.append(f"- node({nid}): {desc[:120]}")

    if not node_lines:
        _ALIGN_CACHE[cache_key] = knowledge
        return knowledge

    system_prompt = (
        "You are matching knowledge point tags to course node descriptions. "
        "For each node description, find the best matching knowledge tag. "
        "Only match when there is a clear semantic relationship (same topic, "
        "synonym, or direct parent/child concept). "
        "Return ONLY valid JSON. No explanation."
    )
    user_prompt = (
        "Knowledge tags:\n" + tag_lines + "\n\n"
        "Node descriptions:\n" + "\n".join(node_lines) + "\n\n"
        'Return JSON: {"matches": {"node title or outcome": {"tag": "best matching knowledge tag"}}}'
        "\nOnly include entries where you are confident of a match."
    )

    # -- call LLM ------------------------------------------------------------------
    try:
        from config import LITELLM_MODEL_CONFIGS
        import litellm

        text_config = LITELLM_MODEL_CONFIGS.get("text") or {}
        response = litellm.completion(
            model=text_config.get("model_name", ""),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            api_base=text_config.get("api_base") or None,
            api_key=text_config.get("api_key") or os.getenv("OPENAI_API_KEY"),
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        # silent degradation — return unenriched knowledge
        _ALIGN_CACHE[cache_key] = knowledge
        return knowledge

    # -- parse JSON ----------------------------------------------------------------
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # try to extract a JSON block from markdown fences
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                _ALIGN_CACHE[cache_key] = knowledge
                return knowledge
        else:
            _ALIGN_CACHE[cache_key] = knowledge
            return knowledge

    matches = parsed.get("matches") if isinstance(parsed, dict) else {}
    if not isinstance(matches, dict):
        _ALIGN_CACHE[cache_key] = knowledge
        return knowledge

    # -- enrich knowledge ----------------------------------------------------------
    enriched = dict(knowledge)
    for matched_text, info in matches.items():
        tag = info.get("tag") if isinstance(info, dict) else info
        if isinstance(tag, str) and tag in knowledge:
            enriched[str(matched_text)] = knowledge[tag]

    _ALIGN_CACHE[cache_key] = enriched
    return enriched


def _as_set(value):
    if value is None:
        return set()
    if isinstance(value, str):
        text = value.strip()
        return {text} if text else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item not in (None, "")}
    return {str(value)}


def _node_outcomes_known(node, knowledge):
    outcomes = [str(s) for s in (node.get('outcomes') or []) if s not in (None, "")]
    title = str(node.get('title') or "")
    if not outcomes and not title:
        return False
    if not knowledge:
        return False
    # Check each outcome and title via fuzzy matching (exact → substring → token overlap).
    # This bridges the gap between short knowledge-point keys ("HDFS 基础") and long
    # syllabus outcome strings ("分布式文件系统及主流技术HDFS").
    candidates = list(outcomes)
    if title and title not in candidates:
        candidates.append(title)
    for candidate in candidates:
        score, _ = _fuzzy_match_score(candidate, knowledge)
        if score <= 0:
            return False
    return True


def _prerequisites_satisfied(node, learning_tree, knowledge, completed_nodes):
    prerequisites = node.get('prerequisites', []) if isinstance(node, dict) else []
    for prerequisite in prerequisites:
        prerequisite_id = str(prerequisite)
        if prerequisite_id in completed_nodes:
            continue
        prerequisite_node = learning_tree.get(prerequisite_id, {})
        if not _node_outcomes_known(prerequisite_node, knowledge):
            return False
    return True


def generate_state(user_profile, learning_tree, study_graph_state=None):
    knowledge = _normalize_knowledge_levels(user_profile)
    knowledge = _llm_align_knowledge(knowledge, learning_tree)
    study_graph_state = study_graph_state if isinstance(study_graph_state, dict) else {}
    completed_nodes = _as_set(study_graph_state.get("completed_node_ids"))
    blocked_nodes = _as_set(study_graph_state.get("blocked_node_ids"))
    weak_nodes = _as_set(study_graph_state.get("weak_node_ids"))
    current_node = str(study_graph_state.get("current_node_id") or "")
    start_nodes = []
    for nid,node in learning_tree.items():
        normalized_id = str(nid)
        if normalized_id in blocked_nodes:
            continue
        if normalized_id in completed_nodes:
            continue
        # Current/weak nodes may be resumed even if their prerequisites are not fully satisfied.
        if normalized_id == current_node or normalized_id in weak_nodes:
            start_nodes.append(nid)
            continue
        # Otherwise a node is a valid start only if it adds new outcomes and its
        # direct prerequisites are already satisfied by profile knowledge or the
        # study graph. This prevents jumping straight to a target node and losing
        # prerequisite context from the candidate path.
        if not _node_outcomes_known(node, knowledge) and _prerequisites_satisfied(node, learning_tree, knowledge, completed_nodes):
            start_nodes.append(nid)
    constraints = dict(user_profile.get('constraints',{}) or {})
    existing_blocked = _as_set(constraints.get("blocked_nodes"))
    if blocked_nodes or existing_blocked:
        constraints["blocked_nodes"] = sorted(blocked_nodes | existing_blocked)
    S = {
        'knowledge': knowledge,
        'preferences': user_profile.get('preferences',{}),
        'constraints': constraints,
        'study_graph_state': {
            'current_node_id': current_node,
            'completed_node_ids': sorted(completed_nodes),
            'blocked_node_ids': sorted(blocked_nodes),
            'weak_node_ids': sorted(weak_nodes),
        },
    }
    return S, start_nodes
