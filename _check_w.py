import os; os.environ["FLASK_APP"]="app.py"
from app import create_app
app = create_app()
with app.app_context():
    from tasks.learning_profile.personal_syllabus import read_profile_personal_syllabus
    for sid, title in [(18,"算法"),(104,"软件")]:
        ps = read_profile_personal_syllabus(1, sid)
        if not ps:
            print(f"[{title}] no personal_syllabus")
            continue
        any_hit = False
        for w in ps.get("period", []):
            c = w.get("competance","none")
            r = w.get("suggestion_review_count",0)
            sug = w.get("suggested_competance_list",[])
            if c != "none" or r > 0:
                any_hit = True
                print(f"[{title}] wk{w.get('week_index')}: competance={c} reviews={r} suggestions={sug}")
        if not any_hit:
            print(f"[{title}] all weeks empty")
