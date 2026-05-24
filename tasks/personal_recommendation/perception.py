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


def generate_state(user_profile, learning_tree):
    knowledge = _normalize_knowledge_levels(user_profile)
    start_nodes = []
    for nid,node in learning_tree.items():
        # a node is candidate start if it has at least one outcome not fully known
        outcomes = node.get('outcomes',[])
        if not all(knowledge.get(s,0) > 0 for s in outcomes):
            # but only include node if prerequisites are not impossible (simple check)
            start_nodes.append(nid)
    S = {'knowledge': knowledge, 'preferences': user_profile.get('preferences',{}), 'constraints': user_profile.get('constraints',{})}
    return S, start_nodes
