"""Demo script: call `/api/personal_recommendation` via Flask test client,
pick the first syllabus in DB if not provided, and save response to
tests/personal_reco_response.json for quick inspection.
"""
import json
import os
from pathlib import Path

from app import create_app
from repositories.syllabus_repo import list_all_syllabuses


def main():
    app = create_app()
    client = app.test_client()

    # try pick first syllabus
    syllabuses = list_all_syllabuses()
    if not syllabuses:
        print('No syllabus found in DB; aborting demo.')
        return
    syllabus = syllabuses[0]
    payload = {'user_id': 1, 'syllabus_id': int(getattr(syllabus, 'syllabus_id', 0))}

    resp = client.post('/api/personal_recommendation', json=payload)
    out_dir = Path('tests')
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / 'personal_reco_response.json'
    try:
        data = resp.get_json()
    except Exception:
        data = {'status_code': resp.status_code, 'text': resp.get_data(as_text=True)}
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote response to {out_file}')


if __name__ == '__main__':
    main()
