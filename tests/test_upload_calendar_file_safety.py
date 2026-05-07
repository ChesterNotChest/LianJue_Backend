from types import SimpleNamespace

from tasks import syllabus_task as st


class EmptyQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


def test_calendar_upload_uses_unique_path_when_original_exists(monkeypatch, tmp_path):
    original_path = tmp_path / "calendar.pdf"
    original_path.write_bytes(b"old calendar")
    created = {}

    monkeypatch.setattr(st, "File", SimpleNamespace(query=EmptyQuery()))
    monkeypatch.setattr(st, "Syllabus", SimpleNamespace(query=EmptyQuery()))

    def fake_create_file(path, upload_time):
        created["path"] = path
        return SimpleNamespace(file_id=11, path=path)

    monkeypatch.setattr(st, "create_file", fake_create_file)

    uploaded = st._add_calendar_file(
        file_path=str(original_path),
        file_name="calendar.pdf",
        file_bytes=b"new calendar",
        upload_time="2026-05-07T00:00:00",
    )

    assert uploaded["file_id"] == 11
    assert uploaded["created"] is True
    assert uploaded["path"] != str(original_path)
    assert original_path.read_bytes() == b"old calendar"
    assert created["path"] == uploaded["path"]


def test_calendar_upload_without_bytes_copies_existing_source_to_unique_path(monkeypatch, tmp_path):
    original_path = tmp_path / "calendar.pdf"
    original_path.write_bytes(b"old calendar")
    created = {}

    monkeypatch.setattr(st, "File", SimpleNamespace(query=EmptyQuery()))
    monkeypatch.setattr(st, "Syllabus", SimpleNamespace(query=EmptyQuery()))

    def fake_create_file(path, upload_time):
        created["path"] = path
        return SimpleNamespace(file_id=14, path=path)

    monkeypatch.setattr(st, "create_file", fake_create_file)

    uploaded = st._add_calendar_file(
        file_path=str(original_path),
        file_name="calendar.pdf",
        file_bytes=None,
        upload_time="2026-05-07T00:00:00",
    )

    assert uploaded["path"] != str(original_path)
    assert original_path.read_bytes() == b"old calendar"
    assert created["path"] == uploaded["path"]
    assert st.Path(uploaded["path"]).read_bytes() == b"old calendar"


def test_calendar_cleanup_only_deletes_created_unreferenced_file(monkeypatch, tmp_path):
    uploaded_path = tmp_path / "calendar_unique.pdf"
    uploaded_path.write_bytes(b"new calendar")
    deleted = []

    monkeypatch.setattr(
        st,
        "get_file_by_id",
        lambda file_id: SimpleNamespace(file_id=file_id, path=str(uploaded_path)),
    )
    monkeypatch.setattr(st, "_has_file_references", lambda file_id: False)
    monkeypatch.setattr(st, "delete_file", lambda file_id: deleted.append(file_id) or True)

    st._delete_calendar_file_if_created({
        "file_id": 12,
        "path": str(uploaded_path),
        "created": True,
    })

    assert deleted == [12]
    assert not uploaded_path.exists()


def test_calendar_cleanup_skips_reused_file(monkeypatch, tmp_path):
    existing_path = tmp_path / "calendar.pdf"
    existing_path.write_bytes(b"old calendar")

    monkeypatch.setattr(st, "delete_file", lambda file_id: (_ for _ in ()).throw(AssertionError("should not delete")))

    st._delete_calendar_file_if_created({
        "file_id": 13,
        "path": str(existing_path),
        "created": False,
    })

    assert existing_path.read_bytes() == b"old calendar"
