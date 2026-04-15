#!/usr/bin/env python3
"""Interactive test for tasks.material_gen_task.update_material_draft.

Usage:
1. Start the app (e.g. `python run.py`) so DB and other services are available.
2. Run this script: `python test_update_material_draft.py` and follow prompts.

This is an interactive test (no mocks) modeled after existing test scripts.
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
    print("Interactive update_material_draft test")
    print("(Start the app first in another terminal if required)")

    material_id = prompt_input("material_id (int): ", required=True, cast=int)
    new_title = prompt_input("new_title (optional, leave empty to skip): ", required=False, cast=str, default=None)

    # collect related_knowledge updates
    related_updates = []
    n_rel = prompt_input("number of related_knowledge updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_rel or 0)):
        qi = prompt_input(f"  update #{i+1} question_index (int): ", required=True, cast=int)
        val = prompt_input(f"  update #{i+1} related_knowledge (text): ", required=True, cast=str)
        related_updates.append({"question_index": qi, "related_knowledge": val})

    # collect query_key updates
    query_updates = []
    n_q = prompt_input("number of query_key updates (0 to skip): ", required=False, cast=int, default=0)
    for i in range(int(n_q or 0)):
        qi = prompt_input(f"  qupdate #{i+1} question_index (int): ", required=True, cast=int)
        val = prompt_input(f"  qupdate #{i+1} query_key (text): ", required=True, cast=str)
        query_updates.append({"question_index": qi, "query_key": val})

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

    print("\nCalling update_material_draft(...) inside Flask app context...")
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
                from tasks.material_gen_task import update_material_draft
                from repositories.material_repo import get_material_by_id
            except Exception as e:
                print(f"Failed to import update_material_draft: {e}")
                return

            try:
                res = update_material_draft(
                    material_id=material_id,
                    material_title=new_title,
                    new_related_knowledge=related_updates or None,
                    new_query_keys=query_updates or None,
                    involved_weeks=involved_weeks,
                )
                if res is None:
                    print("update_material_draft returned None (failure). Check logs above.")
                    return

                print(f"update_material_draft succeeded for material_id={material_id}")
                m = get_material_by_id(material_id)
                draft_path = getattr(m, 'draft_material_path', None)
                print(f"Draft path: {draft_path}")
                if draft_path and Path(draft_path).exists():
                    print("Draft preview (first 2000 chars):\n")
                    print(Path(draft_path).read_text(encoding='utf-8')[:2000])
                else:
                    print("Draft file not found on disk. Check logs.")
                # additional validation: list materials for the syllabus and show a simple table
                try:
                    from tasks.material_gen_task import get_material_draft_detail_info, list_materials_draft_brief_info
                    syl_id = getattr(m, 'syllabus_id', None)
                    print("\nMaterials (brief) for syllabus_id=", syl_id)
                    rows = list_materials_draft_brief_info(syl_id) if syl_id is not None else []
                    if rows:
                        # print pseudo-table
                        hdr = ["material_id", "title", "draft_path", "final_path", "pdf_path", "create_time"]
                        widths = [12, 30, 40, 40, 30, 20]
                        def fmt(cell, w):
                            s = str(cell) if cell is not None else ""
                            return (s[:w-1] + '…') if len(s) > w else s.ljust(w)
                        print(' | '.join(h.ljust(w) for h, w in zip(hdr, widths)))
                        print('-' * (sum(widths) + 3 * (len(widths)-1)))
                        for r in rows:
                            print(' | '.join(fmt(r.get(k), w) for k, w in zip(['material_id','title','draft_path','final_path','pdf_path','create_time'], widths)))
                    else:
                        print('  (no materials found)')

                    print('\nMaterial draft (parsed JSON) preview:')
                    det = get_material_draft_detail_info(material_id)
                    if det:
                        import json as _json
                        print(_json.dumps(det, ensure_ascii=False, indent=2)[:4000])
                    else:
                        print('  (no draft JSON available)')
                except Exception as e:
                    print(f"  ⚠️ 额外验证失败: {e}")
            except Exception as e:
                print(f"Exception during update_material_draft: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
