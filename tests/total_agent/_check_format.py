"""Check reasoning_paths format from search_tool."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tasks.common.search_tool import search_tool

r = search_tool("HBase RowKey", graph_name="RAG", top_k=3)
print("=== reasoning_paths ===")
print(json.dumps(r.get("reasoning_paths", []), ensure_ascii=False, indent=2)[:2000])
print()
print("=== paragraphs (first 2) ===")
for p in r.get("paragraphs", [])[:2]:
    print(p[:200])
    print("---")
print()
print("=== path_scores ===")
print(json.dumps(r.get("path_scores", {}), ensure_ascii=False, indent=2)[:500])
