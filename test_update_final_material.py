#!/usr/bin/env python3
"""Interactive test for tasks.material_gen_task.update_final_material.

Usage:
1. Start the app (e.g. `python run.py`) so DB and other services are available.
2. Run this script: `python test_update_final_material.py` and follow prompts.

This test uses real services (no mocking). It calls the final-material update flow
and will depend on external DB configuration being available.
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
    print("Interactive update_final_material test")
    print("(Start the app first in another terminal if required)")

    material_id = prompt_input("material_id (int): ", required=True, cast=int)
    new_title = prompt_input("new_title (optional, leave empty to skip): ", required=False, cast=str, default=None)

    # collect question_content updates
    question_updates = []
    n_qc = prompt_input("number of question_content updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_qc or 0)):
        qi = prompt_input(f"  update #{i+1} question_index (int): ", required=True, cast=int)
        val = prompt_input(f"  update #{i+1} question_content (text): ", required=True, cast=str)
        question_updates.append({"question_index": qi, "question_content": val})

    # collect answer updates
    answer_updates = []
    n_ans = prompt_input("number of answer updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_ans or 0)):
        qi = prompt_input(f"  update #{i+1} question_index (int): ", required=True, cast=int)
        val = prompt_input(f"  update #{i+1} answer (text): ", required=True, cast=str)
        answer_updates.append({"question_index": qi, "answer": val})

    # collect reason updates
    reason_updates = []
    n_r = prompt_input("number of reason updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_r or 0)):
        qi = prompt_input(f"  update #{i+1} question_index (int): ", required=True, cast=int)
        val = prompt_input(f"  update #{i+1} reason (text): ", required=True, cast=str)
        reason_updates.append({"question_index": qi, "reason": val})

    # collect options updates: enter three fields per update (question_index, options_index, option)
    options_updates = []
    n_opt = prompt_input("number of option updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_opt or 0)):
        qi = prompt_input(f"  update #{i+1} question_index (int): ", required=True, cast=int)
        opt_idx = prompt_input(f"  update #{i+1} options_index (A/B/...): ", required=True, cast=str)
        opt_text = prompt_input(f"  update #{i+1} option text: ", required=True, cast=str)
        options_updates.append({"question_index": qi, "options_index": opt_idx, "option": opt_text})

    iw_raw = prompt_input("involved_weeks (comma separated, optional, leave empty to skip): ", required=False, cast=str, default=None)
    involved_weeks = None
    if iw_raw:
        parts = [p.strip() for p in iw_raw.split(',') if p.strip()]
        involved_weeks = []
        for p in parts:
            try:
                involved_weeks.append(int(p))
            except Exception:
                pass

    print("\nCalling update_final_material(...) inside Flask app context...")
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
                from tasks.material_gen_task import update_final_material
                from repositories.material_repo import get_material_by_id
            except Exception as e:
                print(f"Failed to import update_final_material: {e}")
                return

            try:
                res = update_final_material(
                    material_id=material_id,
                    material_title=new_title,
                    question_content=question_updates or None,
                    answer=answer_updates or None,
                    reason=reason_updates or None,
                    options=options_updates or None,
                    involved_weeks=involved_weeks,
                )
                if res is None:
                    print("update_final_material returned None (failure). Check logs above.")
                    return

                m = get_material_by_id(material_id)
                final_path = getattr(m, 'material_path', None)
                print(f"update_final_material succeeded for material_id={material_id}")
                print(f"Final material path: {final_path}")
                if final_path and Path(final_path).exists():
                    print("Final JSON preview (first 2000 chars):\n")
                    print(Path(final_path).read_text(encoding='utf-8')[:2000])
                else:
                    print("Final file not found on disk. Check logs or DB record.")

                # extra verification: list materials brief and show parsed final JSON
                try:
                    from tasks.material_gen_task import get_material_detail_info, list_materials_brief_info
                    syl_id = getattr(m, 'syllabus_id', None)
                    print("\nMaterials (brief) for syllabus_id=", syl_id)
                    rows = list_materials_brief_info(syl_id) if syl_id is not None else []
                    if rows:
                        hdr = ["material_id", "title", "final_path", "pdf_path", "create_time"]
                        widths = [12, 30, 40, 30, 20]
                        def fmt(cell, w):
                            s = str(cell) if cell is not None else ""
                            return (s[:w-1] + '…') if len(s) > w else s.ljust(w)
                        print(' | '.join(h.ljust(w) for h, w in zip(hdr, widths)))
                        print('-' * (sum(widths) + 3 * (len(widths)-1)))
                        for r in rows:
                            print(' | '.join(fmt(r.get(k), w) for k, w in zip(['material_id','title','final_path','pdf_path','create_time'], widths)))
                    else:
                        print('  (no materials found)')

                    print('\nMaterial final (parsed JSON) preview:')
                    det = get_material_detail_info(material_id)
                    if det:
                        import json as _json
                        print(_json.dumps(det, ensure_ascii=False, indent=2)[:4000])
                    else:
                        print('  (no final JSON available)')
                except Exception as e:
                    print(f"  ⚠️ 额外验证失败: {e}")
            except Exception as e:
                print(f"Exception during update_final_material: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
