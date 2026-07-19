"""Quick matching test: study graph titles → RAG galaxy nodes.

Run: python tests/total_agent/test_galaxy_match.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # up from tests/total_agent/ → project root

def match(sg_title: str, gn_title: str, min_len: int = 2) -> bool:
    t = sg_title.lower()
    gt = gn_title.lower()
    if len(t) < min_len or len(gt) < min_len:
        return False
    return gt in t or t in gt

# Load RAG galaxy
with open(ROOT / 'data' / 'knowledge_graph' / 'rag_probe_full_result.json', encoding='utf-8') as f:
    rag = json.load(f)
galaxy_snap = rag.get('graphSnapshot', rag)
galaxy_nodes = galaxy_snap.get('nodes', [])
print(f'Galaxy (RAG): {len(galaxy_nodes)} nodes')
groups = Counter(n.get('group', '?') for n in galaxy_nodes)
print(f'  Groups: {dict(groups)}')

# Load study graph (use the richest one from e2e_amend)
sg_path = ROOT / 'tests' / 'artifacts' / 'total_agent' / 'e2e_amend' / 'feedback_updates_plan_and_graph' / 'study_graph' / 'user_808' / 'syllabus_2020' / 'manifest.json'
with open(sg_path, encoding='utf-8') as f:
    sg_data = json.load(f)
sg_nodes = (sg_data.get('tree') or sg_data).get('nodes', [])
print(f'\nStudy graph: {len(sg_nodes)} nodes')
for n in sg_nodes:
    label = (n.get('mastery') or {}).get('label', '?')
    print(f'  [{label}] {n["title"]}')

# Match
matched_ids = set()
match_map = {}
for sg in sg_nodes:
    st = sg['title']
    hits = []
    for gn in galaxy_nodes:
        gt = gn.get('title', '')
        if match(st, gt):
            hits.append(gt)
            matched_ids.add(gn.get('id'))
    match_map[st] = hits

print(f'\n=== MATCH RESULTS ===')
print(f'Study graph nodes: {len(sg_nodes)}')
hit_count = sum(1 for v in match_map.values() if v)
print(f'Study nodes with >=1 galaxy match: {hit_count}/{len(sg_nodes)} ({hit_count/len(sg_nodes)*100:.0f}%)')
print(f'Galaxy nodes matched: {len(matched_ids)}/{len(galaxy_nodes)} ({len(matched_ids)/len(galaxy_nodes)*100:.2f}%)')

print(f'\n--- Per-node details ---')
for st, hits in match_map.items():
    if hits:
        print(f'  MATCHED "{st}" -> {len(hits)}: {hits[:5]}{"..." if len(hits) > 5 else ""}')
    else:
        print(f'  NO MATCH "{st}"')

# Matched node groups
matched_groups = Counter()
for nid in matched_ids:
    gn = next((n for n in galaxy_nodes if n.get('id') == nid), None)
    if gn:
        matched_groups[gn.get('group', '?')] += 1
print(f'\nMatched galaxy node groups: {dict(matched_groups)}')
