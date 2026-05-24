#!/usr/bin/env python3
"""
Moved runner for manual KnowLion tests to avoid pytest module name conflict.
Usage: python scripts/test_search_call_runner.py --text "..."
"""
import argparse
import json
import sys

from knowlion.abution_knowlion_driver import KnowLion
from config import LITELLM_MODEL_CONFIGS


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", help="Optional single query to send to search_call")
    p.add_argument("--top_k", type=int, default=10)
    p.add_argument("--graph", help="Optional graph name to use (default: RAG)")
    args = p.parse_args()

    if args.text:
        graph_name = args.graph or 'RAG'
        kl = KnowLion(model_configs=LITELLM_MODEL_CONFIGS or {}, graph_name=graph_name)
        print('--- SEARCH RESULT ---')
        try:
            search_result = kl.search(args.text, top_k=args.top_k)
            para = json.dumps(search_result.get('paragraphs', []), ensure_ascii=False, indent=2)
            print(para)
            print('--- reasoning_path ---')
            print(json.dumps(search_result.get('reasoning_paths', []), ensure_ascii=False, indent=2))
        except Exception as e:
            print('Search failed:', e)
        return

    while True:
        try:
            graph_name = args.graph or input('Enter graph name (or type "/quit" to exit) [RAG]: ').strip() or 'RAG'
        except (KeyboardInterrupt, EOFError):
            print('\nExiting.')
            sys.exit(0)
        if graph_name == '/quit':
            print('Quit requested.')
            break
        kl = KnowLion(model_configs=LITELLM_MODEL_CONFIGS or {}, graph_name=graph_name)
        while True:
            try:
                q = input('Query (type "/exit" to change graph, "/quit" to exit): ').strip()
            except (KeyboardInterrupt, EOFError):
                print('\nExiting.')
                sys.exit(0)
            if not q:
                continue
            if q == '/quit':
                print('Quit requested.')
                sys.exit(0)
            if q == '/exit':
                print('Returning to graph selection...')
                break
            try:
                search_result = kl.search(q, top_k=args.top_k)
                print(json.dumps(search_result.get('paragraphs', []), ensure_ascii=False, indent=2))
                print('--- reasoning_path ---')
                print(json.dumps(search_result.get('reasoning_paths', []), ensure_ascii=False, indent=2))
            except Exception as e:
                print('Search failed:', e)


if __name__ == '__main__':
    main()
