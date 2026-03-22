#!/usr/bin/env python3
"""Interactive test for update_syllabus_draft.

Usage:
1. Start the app (e.g. `python run.py`) so DB and context are available.
2. Run this script: `python test_update_syllabus_draft.py`

The script will prompt for: syllabus_id, week_index, new_content, new_importance
and then call tasks.syllabus_task.update_syllabus_draft(...).
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
    print("Interactive update_syllabus_draft test")
    print("(Start the app first in another terminal if required)")

    syllabus_id = prompt_input("syllabus_id (int): ", required=True, cast=int)
    week_index = prompt_input("week_index (str): ", required=True, cast=str)
    print("Enter new_content (leave empty to skip):")
    try:
        new_content = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted by user.")
        return
    if new_content == "":
        new_content = None

    new_importance = prompt_input("new_importance (low/medium/high) (leave empty to skip): ", required=False, cast=str, default=None)
    if new_importance is not None:
        new_importance = new_importance.strip()
        if new_importance == "":
            new_importance = None

    new_title = prompt_input("new_title (optional, write into draft JSON only, leave empty to skip): ", required=False, cast=str, default=None)
    if new_title is not None:
        new_title = new_title.strip()
        if new_title == "":
            new_title = None

    day_one = prompt_input("day_one (optional, formats: YYYY-MM-DD or M-D, leave empty to skip): ", required=False, cast=str, default=None)
    if day_one is not None:
        day_one = day_one.strip()
        if day_one == "":
            day_one = None

    # perform call inside Flask application context
    print("\nCalling update_syllabus_draft(...) inside app context...")
    try:
        from app import create_app
        app = create_app()
    except Exception as e:
        print(f"Failed to create Flask app: {e}")
        print("If your environment requires external services (DB), ensure they're available or set env vars.")
        return

    try:
        with app.app_context():
            try:
                from tasks.syllabus_task import update_syllabus_draft
            except Exception as e:
                print(f"Failed to import update_syllabus_draft within app context: {e}")
                return

            try:
                res = update_syllabus_draft(syllabus_id=syllabus_id, week_index=week_index, day_one=day_one, new_content=new_content, new_importance=new_importance, new_title=new_title)
                if res is None:
                    print("update_syllabus_draft returned None (failure or no-op). Check logs/messages above.")
                else:
                    print("update_syllabus_draft completed. Check syllabus draft JSON file for title/day_one/content changes; DB day_one may also be updated if applicable.")
            except Exception as e:
                print(f"Exception during update_syllabus_draft: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
