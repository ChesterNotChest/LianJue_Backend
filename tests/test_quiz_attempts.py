from tasks.quiz_attempts import list_quiz_attempts, submit_quiz_attempt


def test_quiz_attempt_submit_and_duplicate(monkeypatch, tmp_path):
    monkeypatch.setenv("QUIZ_ATTEMPT_ROOT", str(tmp_path))

    first = submit_quiz_attempt(
        user_id=212,
        syllabus_id=29,
        resource_id="quiz-abc",
        attempt_id="attempt-fixed",
        answers={"1": "A"},
        score=1.0,
        correct_count=1,
        total_count=1,
        wrong_knowledge_items=[],
        answer_records=[{"question": "q1", "correct": True}],
    )
    duplicate = submit_quiz_attempt(
        user_id=212,
        syllabus_id=29,
        resource_id="quiz-abc",
        attempt_id="attempt-fixed",
        answers={"1": "B"},
        score=0.0,
    )

    attempts = list_quiz_attempts(212, "quiz-abc")
    assert first["success"] is True
    assert first["duplicate"] is False
    assert duplicate["success"] is True
    assert duplicate["duplicate"] is True
    assert len(attempts) == 1
    assert attempts[0]["attempt_id"] == "attempt-fixed"
    assert attempts[0]["answers"] == {"1": "A"}
