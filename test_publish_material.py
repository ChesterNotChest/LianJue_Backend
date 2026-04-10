#!/usr/bin/env python3
"""Interactive test for tasks.material_gen_task.publish_material.

Usage:
1. Start the app (e.g. `python run.py`) so DB and other services are available.
2. Run this script: `python test_publish_material.py` and follow prompts.

This test uses real services (no mocking). It will call `publish_material` and
may generate a PDF (requires `reportlab`).
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
    print("Interactive publish_material test")
    print("(Start the app first in another terminal if required)")

    material_id = prompt_input("material_id (int): ", required=True, cast=int)
    new_pdf_raw = prompt_input("regenerate PDF? (y/N): ", required=False, default="N")
    new_pdf = str(new_pdf_raw).strip().lower() in ("y", "yes")
    do_publish_raw = prompt_input("mark as published? (y/N): ", required=False, default="N")
    do_publish = str(do_publish_raw).strip().lower() in ("y", "yes")

    print("\nCalling publish_material(...) inside Flask app context...")
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
                from tasks.material_gen_task import publish_material
                from repositories.material_repo import get_material_by_id
            except Exception as e:
                print(f"Failed to import publish_material: {e}")
                return

            try:
                res = publish_material(material_id=material_id, new_pdf=new_pdf, do_publish=do_publish)
                if res is None:
                    print("publish_material returned None (failure). Check logs above.")
                    return

                m = get_material_by_id(material_id)
                pdf_path = getattr(m, 'pdf_path', None)
                print(f"publish_material completed for material_id={material_id}")
                print(f"PDF path in DB: {pdf_path}")
                if pdf_path and Path(pdf_path).exists():
                    print(f"PDF file exists on disk: {pdf_path}")
                else:
                    print("PDF file not found on disk. If new_pdf was False, no PDF may be generated.")
            except Exception as e:
                print(f"Exception during publish_material: {e}")
    except Exception as e:
        print(f"Error entering Flask app context: {e}")


if __name__ == '__main__':
    main()
