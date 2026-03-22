#!/usr/bin/env python3
"""Interactive runner for build_syllabus.

Prompts for:
- syllabus_id (int, required)
- graph_name (optional, pass empty to use draft/default)
- day_one (optional, pass empty to send None; build_syllabus will use draft or fallback)

Usage: Start the app services (DB) if necessary, then run:
    python test_build_syllabus.py
"""
import sys

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
    print("Interactive build_syllabus test")
    print("(Start the app first in another terminal if required)")

    syllabus_id = prompt("syllabus_id (int): ", required=True, cast=int)
    graph_name = prompt("graph_name (optional, leave empty to use draft): ", required=False, default=None)
    day_one = prompt("day_one (optional, leave empty to send None): ", required=False, default=None)

    print("\nCreating Flask app and calling build_syllabus inside app context...")
    try:
        from app import create_app
        app = create_app()
    except Exception as e:
        print(f"Failed to create Flask app: {e}")
        return

    try:
        with app.app_context():
            try:
                from tasks.syllabus_task import build_syllabus
            except Exception as e:
                print(f"Failed to import build_syllabus: {e}")
                return

            try:
                res = build_syllabus(syllabus_id=syllabus_id, graph_name=graph_name, day_one=day_one)
                if res is None:
                    print("build_syllabus returned None (failure). Check logs above.")
                else:
                    print("build_syllabus completed. Check schedule/syllabus_final/ and DB record.")
            except Exception as e:
                print(f"Exception during build_syllabus: {e}")
    except Exception as e:
        print(f"Error entering app context: {e}")


if __name__ == '__main__':
    main()
