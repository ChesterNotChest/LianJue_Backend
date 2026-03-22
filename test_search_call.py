#!/usr/bin/env python3
"""
Quick runner to test `KnowLion.search_call` locally without external services.
Usage:
    python scripts/test_search_call.py --text "你的问题"

This script injects a mock `model` and a mock `search` result to avoid network/LLM dependencies.
"""
import argparse

import json

from knowlion.abution_knowlion_driver import KnowLion
from config import MODEL_CONFIGS
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", help="Optional single query to send to search_call")
    p.add_argument("--top_k", type=int, default=10)
    p.add_argument("--graph", help="Optional graph name to use (default: RAG)")
    args = p.parse_args()

    def run_query_loop(graph_name):
        kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name)
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

            print('--- SEARCH RESULT ---')
            try:
                search_result = kl.search(q, top_k=args.top_k)
                para = json.dumps(search_result.get('paragraphs', []), ensure_ascii=False, indent=2)
                print(para)
                print('--- reasoning_path ---')
                print(json.dumps(search_result.get('reasoning_paths', []), ensure_ascii=False, indent=2))
            except Exception as e:
                print('Search failed:', e)

            # DEBUG EARLY CONTINUE
            continue

            print('Calling KnowLion.search_call...')
            try:
                result = kl.search_call(q, top_k=args.top_k, prompt=None, stream=False)
                print('--- RESULT ---')
                print(result)
            except Exception as e:
                print('search_call failed:', e)

    # If a single text was provided on the command line, run it once (graph from --graph or default)
    if args.text:
        graph_name = args.graph or 'RAG'
        kl = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name)
        print('--- SEARCH RESULT ---')
        try:
            search_result = kl.search(args.text, top_k=args.top_k)
            para = json.dumps(search_result.get('paragraphs', []), ensure_ascii=False, indent=2)
            print(para)
            print('--- reasoning_path ---')
            print(json.dumps(search_result.get('reasoning_paths', []), ensure_ascii=False, indent=2))
        except Exception as e:
            print('Search failed:', e)
        
        # DEBUG EARLY EXIT
        return

        print('Calling KnowLion.search_call...')
        try:
            result = kl.search_call(args.text, top_k=args.top_k, prompt=None, stream=False)
            print('--- RESULT ---')
            print(result)
        except Exception as e:
            print('search_call failed:', e)
        return

    # Interactive mode: allow selecting graph name and repeatedly asking queries
    while True:
        try:
            graph_name = args.graph or input('Enter graph name (or type "/quit" to exit) [RAG]: ').strip() or 'RAG'
        except (KeyboardInterrupt, EOFError):
            print('\nExiting.')
            sys.exit(0)
        if graph_name == '/quit':
            print('Quit requested.')
            break

        run_query_loop(graph_name)


if __name__ == "__main__":
    main()
