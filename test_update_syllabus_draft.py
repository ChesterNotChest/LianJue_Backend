#!/usr/bin/env python3
"""Interactive test for update_syllabus_draft.

Usage:
1. Start the app (e.g. `python run.py`) so DB and context are available.
2. Run this script: `python test_update_syllabus_draft.py`

The script will prompt for: syllabus_id, period_json_path
and then call tasks.syllabus_task.update_syllabus_draft(...).
"""
from pathlib import Path
import json
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
    period_json_path = prompt_input("period_json_path (JSON file containing a period array or an object with `period`): ", required=True, cast=str)
    period_path = Path(period_json_path)
    if not period_path.exists():
        print(f"File does not exist: {period_path}")
        return

    try:
        payload = json.loads(period_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Failed to read JSON file: {e}")
        return

    if isinstance(payload, dict):
        period = payload.get('period')
    else:
        period = payload

    if not isinstance(period, list):
        print("JSON must be a period array, or an object containing a `period` array.")
        return

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
                res = update_syllabus_draft(syllabus_id=syllabus_id, period=period)
                if res is None:
                    print("update_syllabus_draft returned None (failure or no-op). Check logs/messages above.")
                else:
                    print("update_syllabus_draft completed. Check syllabus draft JSON file for full period replacement.")
                    # extra verification: show draft JSON and list syllabuses brief
                    try:
                        from tasks.syllabus_task import get_syllabus_draft_detail_info, list_all_syllabuses_brief_info
                        detail = get_syllabus_draft_detail_info(syllabus_id)
                        print('\nSyllabus draft detail (preview):')
                        if detail:
                            import json as _json
                            print(_json.dumps(detail, ensure_ascii=False, indent=2)[:4000])
                        else:
                            print('  (no draft detail available)')

                        print('\nAll syllabuses (brief):')
                        rows = list_all_syllabuses_brief_info()
                        if rows:
                            hdr = ['syllabus_id','title','draft_path']
                            widths = [12,40,60]
                            def fmt(cell,w):
                                s = str(cell) if cell is not None else ''
                                return (s[:w-1] + '…') if len(s) > w else s.ljust(w)
                            print(' | '.join(h.ljust(w) for h,w in zip(hdr,widths)))
                            print('-' * (sum(widths) + 3*(len(widths)-1)))
                            for r in rows:
                                print(' | '.join(fmt(r.get(k), w) for k,w in zip(['syllabus_id','title','draft_path'], widths)))
                        else:
                            print('  (no syllabuses found)')
                    except Exception as e:
                        print(f'  ⚠️ 额外验证失败: {e}')
            except Exception as e:
                print(f"Exception during update_syllabus_draft: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
