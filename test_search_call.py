#!/usr/bin/env python3
"""
Quick runner to test `KnowLion.search_call` locally without external services.
Usage:
    python scripts/test_search_call.py --text "你的问题"

This script injects a mock `model` and a mock `search` result to avoid network/LLM dependencies.
"""
import argparse

from knowlion.abution_knowlion_driver import KnowLion
from config import MODEL_CONFIGS


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True, help="Query text to send to search_call")
    p.add_argument("--top_k", type=int, default=10)
    args = p.parse_args()

    # Create KnowLion instance using application MODEL_CONFIGS
    kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name="RAG")

    search_result = kl.search(args.text, top_k=args.top_k)
    print("--- SEARCH RESULT ---")
    print(search_result)

    print("Calling KnowLion.search_call...")
    result = kl.search_call(args.text, top_k=args.top_k, prompt=None, stream=False)
    print("--- RESULT ---")
    print(result)


if __name__ == "__main__":
    main()
