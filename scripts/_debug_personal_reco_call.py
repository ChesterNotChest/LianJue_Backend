import json
from app import create_app
from repositories.syllabus_repo import create_syllabus, set_syllabus_path
import tempfile

app = create_app()
app.testing = True
client = app.test_client()

sample = [{"id":"s1","title":"Start","outcomes":["skill_a"]},{"id":"s2","title":"Next","prerequisites":["s1"],"outcomes":["skill_b"]}]
fd = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
fd.write(json.dumps(sample, ensure_ascii=False))
fd.close()
with app.app_context():
    syllabus = create_syllabus(title='test-integ')
    set_syllabus_path(int(syllabus.syllabus_id), fd.name)
    syllabus_id = int(syllabus.syllabus_id)
resp = client.post('/api/personal_recommendation', json={'user_id':12345, 'syllabus_id': syllabus_id})
print('status', resp.status_code)
print(resp.get_data(as_text=True))
