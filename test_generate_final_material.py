#!/usr/bin/env python3
"""Interactive test for tasks.material_gen_task.generate_final_material.

Usage:
1. Start the app (e.g. `python run.py`) so DB and other services are available.
2. Run this script: `python test_generate_final_material.py` and follow prompts.

This test uses real services (no mocking). It calls the final-material generation flow
and will depend on external LLM/RAG configuration being available.
"""
from pathlib import Path
import sys


def prompt_input(prompt, required=False, cast=None, default=None):
    while True:
        try:
            v = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted by user.")
            sys.exit(1)
        if v == "":
            if required and default is None:
                print("This field is required.")
                continue
            return default
        if cast:
            try:
                return cast(v)
            except Exception as e:
                print(f"Invalid value: {e}")
                continue
        return v


def main():
    print("Interactive generate_final_material test")
    print("(Start the app first in another terminal if required)")

    material_id = prompt_input("material_id (int): ", required=True, cast=int)

    print("\nCalling generate_final_material(...) inside Flask app context...")
    try:
        from app import create_app
        app = create_app()
    except Exception as e:
        print(f"Failed to create Flask app: {e}")
        print("If your environment requires DB or other services, ensure they're available.")
        return

    try:
        with app.app_context():
            try:
                from tasks.material_gen_task import generate_final_material
                from repositories.material_repo import get_material_by_id
            except Exception as e:
                print(f"Failed to import generate_final_material: {e}")
                return

            try:
                res = generate_final_material(material_id=material_id)
                if res is None:
                    print("generate_final_material returned None (failure). Check logs above.")
                    return

                m = get_material_by_id(material_id)
                final_path = getattr(m, 'material_path', None)
                print(f"generate_final_material succeeded for material_id={material_id}")
                print(f"Final material path: {final_path}")
                if final_path and Path(final_path).exists():
                    print("Final JSON preview (first 2000 chars):\n")
                    print(Path(final_path).read_text(encoding='utf-8')[:2000])
                else:
                    print("Final file not found on disk. Check logs or DB record.")
            except Exception as e:
                print(f"Exception during generate_final_material: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
