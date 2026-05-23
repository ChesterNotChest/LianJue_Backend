import json
import os
from pathlib import Path

from app import create_app
from repositories.syllabus_repo import create_syllabus, set_syllabus_path


def test_personal_reco_with_syllabus(tmp_path):
    app = create_app()
    app.testing = True
    client = app.test_client()

    # prepare a simple syllabus JSON file
    sample = [
        {"id": "s1", "title": "Start", "outcomes": ["skill_a"]},
        {"id": "s2", "title": "Next", "prerequisites": ["s1"], "outcomes": ["skill_b"]},
    ]
    out_file = tmp_path / 'sample_syllabus.json'
    out_file.write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')

    with app.app_context():
        syllabus = create_syllabus(title='test-integ')
        assert getattr(syllabus, 'syllabus_id', None) is not None
        set_syllabus_path(int(syllabus.syllabus_id), str(out_file))
        syllabus_id = int(syllabus.syllabus_id)

    # call endpoint
    payload = {'user_id': 12345, 'syllabus_id': syllabus_id}
    resp = client.post('/api/personal_recommendation', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert 'candidates' in data and 'selected' in data

    # save response for inspection
    tests_dir = Path('tests')
    tests_dir.mkdir(exist_ok=True)
    out_path = tests_dir / 'personal_reco_response.json'
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
