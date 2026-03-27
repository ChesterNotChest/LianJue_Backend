#!/usr/bin/env python3
"""Interactive test for tasks.material_gen_task.generate_material.

Usage:
1. Start the app (e.g. `python run.py`) so DB and other services are available.
2. Run this script: `python test_generate_material.py` and follow prompts.

This test uses real services (no mocking). It calls the RAG/LLM flows and will
depend on external configuration being available.
"""
from pathlib import Path
import sys


def prompt_input(prompt, required=False, cast=None, default=None):
    while True:
        try:
            v = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print('\nAborted by user.')
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


def parse_weeks(s: str):
    parts = [p.strip() for p in s.split(',') if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            pass
    return out


def main():
    print("Interactive generate_material test (no mocks)")
    print("(Start the app first in another terminal if required)")

    syllabus_id = prompt_input("syllabus_id (int): ", required=True, cast=int)
    weeks_raw = prompt_input("involved_weeks (comma separated, e.g. 1,2,3): ", required=True)
    involved_weeks = parse_weeks(weeks_raw)
    if not involved_weeks:
        print("No valid weeks parsed. Exiting.")
        return

    print("Enter desired counts for each question type (leave empty for 0):")
    single = prompt_input("  single (int): ", required=False, cast=int, default=0)
    judge = prompt_input("  judge (int): ", required=False, cast=int, default=0)
    short = prompt_input("  short (int): ", required=False, cast=int, default=0)

    distribution = {"single": int(single or 0), "judge": int(judge or 0), "short": int(short or 0)}

    print("\nCalling generate_material(...) inside Flask app context...")
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
                from tasks.material_gen_task import generate_material
            except Exception as e:
                print(f"Failed to import generate_material: {e}")
                return

            try:
                material = generate_material(syllabus_id=syllabus_id, involved_weeks=involved_weeks, question_type_distribution=distribution)
                if material is None:
                    print("generate_material returned None (failure). Check logs above.")
                    return

                mid = getattr(material, 'material_id', None)
                draft_path = getattr(material, 'draft_material_path', None)
                print(f"Material created: id={mid}")
                print(f"Draft path: {draft_path}")
                if draft_path and Path(draft_path).exists():
                    print("Draft file exists. Preview (first 2000 chars):\n")
                    print(Path(draft_path).read_text(encoding='utf-8')[:2000])
                else:
                    print("Draft file not found on disk. Check logs.")
            except Exception as e:
                print(f"Exception during generate_material: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
