STUDY_GRAPH_STATE_COMPLETED = "completed"
STUDY_GRAPH_STATE_BLOCKED = "blocked"
STUDY_GRAPH_STATE_WEAK = "weak"
STUDY_GRAPH_STATE_CURRENT = "current"


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


def _as_set(value):
    if value is None:
        return set()
    if isinstance(value, str):
        text = value.strip()
        return {text} if text else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item not in (None, "")}
    return {str(value)}


def generate_state(user_profile, learning_tree, study_graph_state=None):
    knowledge = _normalize_knowledge_levels(user_profile)
    study_graph_state = study_graph_state if isinstance(study_graph_state, dict) else {}
    completed_nodes = _as_set(study_graph_state.get("completed_node_ids"))
    blocked_nodes = _as_set(study_graph_state.get("blocked_node_ids"))
    weak_nodes = _as_set(study_graph_state.get("weak_node_ids"))
    current_node = str(study_graph_state.get("current_node_id") or "")
    start_nodes = []
    for nid,node in learning_tree.items():
        if str(nid) in blocked_nodes:
            continue
        if str(nid) in completed_nodes:
            continue
        # a node is candidate start if it has at least one outcome not fully known
        outcomes = node.get('outcomes',[])
        if str(nid) == current_node or str(nid) in weak_nodes or not all(knowledge.get(s,0) > 0 for s in outcomes):
            # but only include node if prerequisites are not impossible (simple check)
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
