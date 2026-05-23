def generate_state(user_profile, learning_tree):
    knowledge = user_profile.get('knowledge_levels',{})
    start_nodes = []
    for nid,node in learning_tree.items():
        # a node is candidate start if it has at least one outcome not fully known
        outcomes = node.get('outcomes',[])
        if not all(knowledge.get(s,0) > 0 for s in outcomes):
            # but only include node if prerequisites are not impossible (simple check)
            start_nodes.append(nid)
    S = {'knowledge': knowledge, 'preferences': user_profile.get('preferences',{}), 'constraints': user_profile.get('constraints',{})}
    return S, start_nodes
