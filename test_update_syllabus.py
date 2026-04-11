#!/usr/bin/env python3
"""Interactive test for updating a syllabus draft using JSON payloads.

This script demonstrates the new JSON-based update flow for syllabus drafts.
It reads a JSON file (or uses an inline example) and calls
`tasks.syllabus_task.update_syllabus_draft(...)` inside a Flask app
context. Designed for manual runs; may require DB and background workers.
"""
import json
import sys
from pathlib import Path
from app import create_app


def prompt(prompt, required=False, cast=None, default=None):
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
        try:
            return cast(v) if cast else v
        except Exception as e:
            print(f"Invalid value: {e}")


def main():
    print("Interactive update_syllabus_draft test (JSON payload)")

    syllabus_id = prompt("syllabus_id (int): ", required=True, cast=int)
    json_path = prompt("period JSON file path (optional, leave empty to use example): ", required=False, default=None)

    if json_path:
        p = Path(json_path)
        if not p.exists():
            print(f"File not found: {p}")
            return
        try:
            payload = json.loads(p.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"Failed to read JSON: {e}")
            return
        if isinstance(payload, dict) and 'period' in payload:
            period = payload['period']
        else:
            period = payload
    else:
        # Example minimal period structure — adapt to your schema
        period = [
            {"week": 1, "topics": ["Introduction"], "notes": "示例周次 1"},
            {"week": 2, "topics": ["基础概念"], "notes": "示例周次 2"},
        ]

    print("\nCreating Flask app and calling update_syllabus_draft inside app context...")
    try:
        app = create_app()
    except Exception as e:
        print(f"Failed to create Flask app: {e}")
        return

    try:
        with app.app_context():
            try:
                from tasks.syllabus_task import update_syllabus_draft, get_syllabus_draft_detail_info
            except Exception as e:
                print(f"Failed to import syllabus_task: {e}")
                return

            try:
                res = update_syllabus_draft(syllabus_id=syllabus_id, period=period)
                if res is None:
                    print("update_syllabus_draft returned None (failure or no-op). Check logs.)")
                else:
                    print("update_syllabus_draft completed. Check syllabus draft JSON file or DB record.")
                    try:
                        detail = get_syllabus_draft_detail_info(syllabus_id)
                        print('Syllabus draft detail (preview):')
                        import json as _json
                        print(_json.dumps(detail, ensure_ascii=False, indent=2)[:4000])
                    except Exception:
                        pass
            except Exception as e:
                print(f"Exception during update_syllabus_draft: {e}")
    except Exception as e:
        print(f"Error entering app context: {e}")


if __name__ == '__main__':
    main()
