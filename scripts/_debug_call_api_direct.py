import json
from app import create_app
from repositories.syllabus_repo import create_syllabus, set_syllabus_path
from blueprint.learning_api import personal_recommendation_api
from tasks.learning_profile.storage import save_personal_profile

app = create_app()

sample = [{"id":"s1","title":"Start","outcomes":["skill_a"]},{"id":"s2","title":"Next","prerequisites":["s1"],"outcomes":["skill_b"]}]
import tempfile
fd = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
fd.write(json.dumps(sample, ensure_ascii=False))
fd.close()

with app.app_context():
    syllabus = create_syllabus(title='debug-integ')
    set_syllabus_path(int(syllabus.syllabus_id), fd.name)
    syllabus_id = int(syllabus.syllabus_id)

    # create and save a minimal persisted profile so the API can load it
    profile = {
        'user_id': 12345,
        'syllabus_id': syllabus_id,
        'knowledge_levels': {},
        'learning_goals': []
    }
    # write profile file directly to candidate path to avoid DB foreign-key constraints
    import os
    profile_dir = os.path.abspath(os.path.join(os.getcwd(), 'profiles'))
    os.makedirs(profile_dir, exist_ok=True)
    profile_path = os.path.join(profile_dir, f"{syllabus_id}-12345.json")
    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print('wrote profile to', profile_path)

    # build a test request context and call the view function directly
    with app.test_request_context('/api/personal_recommendation', json={'user_id': 12345, 'syllabus_id': syllabus_id}):
        try:
            resp = personal_recommendation_api()
            print('raw return repr:', repr(resp))
            if isinstance(resp, tuple):
                resp_obj, status = resp
                print('status from tuple:', status)
                try:
                    print('resp json:', resp_obj.get_json())
                except Exception:
                    print('resp text:', resp_obj.get_data(as_text=True))
            else:
                try:
                    print('resp json:', resp.get_json())
                except Exception:
                    print('resp text:', resp.get_data(as_text=True))
        except Exception as e:
            import traceback
            traceback.print_exc()
