"""Public generative resource task facade.

The package under ``tasks.generative`` owns lower-level storage, validation,
rendering, and constants. This task module keeps the public generation
orchestration functions.
"""

from pathlib import Path
from typing import Any, Optional

from tasks.generative.contracts import (
    GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
    GENERATIVE_DOCUMENT_SCHEMA_VERSION,
    GENERATIVE_MANIFEST_VERSION,
    GENERATIVE_PPT_SCHEMA_VERSION,
    GENERATIVE_QUIZ_SCHEMA_VERSION,
    GENERATIVE_RESOURCE_TYPES,
    MINDMAP_ALLOWED_DIAGRAM_PREFIXES,
)
from tasks.generative.renderers import (
    render_coding_practice_markdown,
    render_document_markdown,
    render_ppt_markdown,
    render_quiz_markdown,
)
from tasks.generative.storage import (
    _get_backend_root,
    _get_generative_root,
    append_manifest_entry,
    ensure_generative_workspace,
    get_generative_user_root,
    load_manifest,
    new_resource_id as _new_resource_id,
    normalize_positive_int as _normalize_positive_int,
    normalize_resource_type as _normalize_resource_type,
    read_json as _read_json,
    repo_relative_path as _repo_relative_path,
    save_manifest,
    utc_timestamp as _utc_timestamp,
    write_json as _write_json,
    write_text as _write_text,
)
from tasks.generative.validation import (
    strip_mermaid_fence as _strip_mermaid_fence,
    validate_coding_practice_payload,
    validate_document_payload,
    validate_mermaid_text,
    validate_ppt_payload,
    validate_quiz_payload,
)


def _build_resource_entry(
    *,
    user_id: int,
    resource_id: str,
    resource_type: str,
    title: str,
    topic: str,
    syllabus_id: Optional[int],
    resource_dir: Path,
    main_files: dict,
    status: str,
    validation: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    now_ts = _utc_timestamp()
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "title": title,
        "topic": topic,
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "status": status,
        "resource_dir": _repo_relative_path(resource_dir),
        "main_files": main_files,
        "validation": validation or {},
        "metadata": metadata or {},
        "created_at": now_ts,
        "updated_at": now_ts,
    }


def _payload_ids_and_topic(payload: dict) -> tuple[int, Optional[int], str]:
    user_id = _normalize_positive_int(payload.get("user_id"), "user_id")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic is required")

    syllabus_id_raw = payload.get("syllabus_id")
    syllabus_id = None
    if syllabus_id_raw not in (None, ""):
        syllabus_id = _normalize_positive_int(syllabus_id_raw, "syllabus_id")
    return user_id, syllabus_id, topic


def _build_main_files(*, json_path: str, **extra: Optional[str]) -> dict:
    main_files = {"json_path": json_path}
    for key, value in extra.items():
        if value:
            main_files[key] = value
    return main_files


def _build_result_payload(*, entry: dict) -> dict:
    result = {
        "success": True,
        "resource_id": entry["resource_id"],
        "resource_type": entry["resource_type"],
        "title": entry["title"],
        "topic": entry["topic"],
        "status": entry["status"],
        "resource_dir": entry["resource_dir"],
        "validation": entry["validation"],
    }
    for key, value in entry["main_files"].items():
        if key not in result:
            result[key] = value
    return result


def persist_mindmap_resource(payload: dict, generated: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if not isinstance(generated, dict):
        raise ValueError("generated mindmap content must be a dict")

    user_id, syllabus_id, topic = _payload_ids_and_topic(payload)
    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("mindmap")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    title = str(generated.get("title") or topic).strip() or topic
    mermaid_text = str(generated.get("mermaid") or "").strip()
    if not mermaid_text:
        raise ValueError("generated mindmap content must include non-empty mermaid text")

    validation = validate_mermaid_text(mermaid_text)
    cleaned_mermaid = validation["cleaned_text"]
    mindmap_json = {
        "title": title,
        "topic": topic,
        "root": generated.get("root") or topic,
        "nodes": generated.get("nodes") if isinstance(generated.get("nodes"), list) else [],
        "mermaid": cleaned_mermaid,
        "knowledge_items": payload.get("knowledge_items") if isinstance(payload.get("knowledge_items"), list) else [],
        "hierarchy": generated.get("hierarchy") if isinstance(generated.get("hierarchy"), dict) else payload.get("hierarchy", {}),
    }

    mindmap_json_path = resource_dir / "mindmap.json"
    mermaid_path = resource_dir / "mindmap.mmd"
    _write_json(mindmap_json_path, mindmap_json)
    _write_text(mermaid_path, cleaned_mermaid + "\n")

    status = "ready" if validation["valid"] else "invalid"
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=topic,
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=_build_main_files(
            json_path=_repo_relative_path(mindmap_json_path),
            mermaid_path=_repo_relative_path(mermaid_path),
        ),
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "diagram_type": validation["diagram_type"],
            "node_count": validation["node_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={"knowledge_item_count": len(mindmap_json["knowledge_items"])},
    )
    append_manifest_entry(user_id, entry)
    return _build_result_payload(entry=entry)


def persist_structured_document_resource(payload: dict, generated: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if not isinstance(generated, dict):
        raise ValueError("generated document content must be a dict")

    user_id, syllabus_id, topic = _payload_ids_and_topic(payload)
    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("documents")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    title = str(generated.get("title") or f"{topic} document").strip() or f"{topic} document"
    document_json = {
        "schema_version": str(generated.get("schema_version") or GENERATIVE_DOCUMENT_SCHEMA_VERSION),
        "title": title,
        "topic": str(generated.get("topic") or topic).strip() or topic,
        "summary": str(generated.get("summary") or "").strip(),
        "sections": generated.get("sections") if isinstance(generated.get("sections"), list) else [],
        "extension_reading": generated.get("extension_reading") if isinstance(generated.get("extension_reading"), list) else [],
    }
    validation = validate_document_payload(document_json)
    document_markdown = render_document_markdown(document_json)

    document_json_path = resource_dir / "document.json"
    document_md_path = resource_dir / "document.md"
    _write_json(document_json_path, document_json)
    _write_text(document_md_path, document_markdown)

    status = "ready" if validation["valid"] else "invalid"
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=document_json["topic"],
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=_build_main_files(
            json_path=_repo_relative_path(document_json_path),
            md_path=_repo_relative_path(document_md_path),
        ),
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "schema_version": validation["schema_version"],
            "section_count": validation["section_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={
            "section_count": validation["section_count"],
            "extension_reading_count": len(document_json["extension_reading"]),
        },
    )
    append_manifest_entry(user_id, entry)
    return _build_result_payload(entry=entry)


def persist_quiz_resource(payload: dict, generated: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if not isinstance(generated, dict):
        raise ValueError("generated quiz content must be a dict")

    user_id, syllabus_id, topic = _payload_ids_and_topic(payload)
    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("quiz")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    title = str(generated.get("title") or f"{topic} quiz").strip() or f"{topic} quiz"
    quiz_json = {
        "schema_version": str(generated.get("schema_version") or GENERATIVE_QUIZ_SCHEMA_VERSION),
        "title": title,
        "topic": str(generated.get("topic") or topic).strip() or topic,
        "questions": generated.get("questions") if isinstance(generated.get("questions"), list) else [],
    }
    validation = validate_quiz_payload(quiz_json)
    quiz_markdown = render_quiz_markdown(quiz_json)

    quiz_json_path = resource_dir / "quiz.json"
    quiz_md_path = resource_dir / "quiz.md"
    _write_json(quiz_json_path, quiz_json)
    _write_text(quiz_md_path, quiz_markdown)

    status = "ready" if validation["valid"] else "invalid"
    question_types = [
        str(question["type"])
        for question in quiz_json["questions"]
        if isinstance(question, dict) and question.get("type")
    ]
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=quiz_json["topic"],
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=_build_main_files(
            json_path=_repo_relative_path(quiz_json_path),
            md_path=_repo_relative_path(quiz_md_path),
        ),
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "schema_version": validation["schema_version"],
            "question_count": validation["question_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={
            "question_count": validation["question_count"],
            "question_types": sorted(set(question_types)),
        },
    )
    append_manifest_entry(user_id, entry)
    return _build_result_payload(entry=entry)


def generate_mindmap(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single mindmap resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_mindmap"):
        raise ValueError("agent_adapter must expose generate_mindmap(payload)")

    generated = agent_adapter.generate_mindmap(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_mindmap must return a dict")
    return persist_mindmap_resource(payload, generated)


def generate_structured_document(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single structured document resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_document"):
        raise ValueError("agent_adapter must expose generate_document(payload)")

    generated = agent_adapter.generate_document(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_document must return a dict")
    return persist_structured_document_resource(payload, generated)


def generate_quiz(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single quiz resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_quiz"):
        raise ValueError("agent_adapter must expose generate_quiz(payload)")

    generated = agent_adapter.generate_quiz(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_quiz must return a dict")
    return persist_quiz_resource(payload, generated)


def _safe_relative_code_path(path_value: Any) -> Optional[Path]:
    normalized = str(path_value or "").strip().replace("\\", "/")
    if not normalized:
        return None
    candidate = Path(normalized)
    if candidate.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate


def persist_coding_practice_resource(payload: dict, generated: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if not isinstance(generated, dict):
        raise ValueError("generated coding practice content must be a dict")

    user_id, syllabus_id, topic = _payload_ids_and_topic(payload)
    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("coding_practice")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    title = str(generated.get("title") or f"{topic} 实操案例").strip() or f"{topic} 实操案例"
    language = str(generated.get("language") or payload.get("language") or "").strip() or "python"
    code_files = generated.get("code_files") if isinstance(generated.get("code_files"), list) else []
    practice_json = {
        "schema_version": str(
            generated.get("schema_version") or GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION
        ),
        "title": title,
        "topic": str(generated.get("topic") or topic).strip() or topic,
        "language": language,
        "summary": str(generated.get("summary") or "").strip(),
        "learning_objectives": (
            generated.get("learning_objectives")
            if isinstance(generated.get("learning_objectives"), list)
            else []
        ),
        "steps": generated.get("steps") if isinstance(generated.get("steps"), list) else [],
        "code_files": code_files,
        "run_guide": generated.get("run_guide") if isinstance(generated.get("run_guide"), dict) else {},
    }
    validation = validate_coding_practice_payload(practice_json)
    practice_markdown = render_coding_practice_markdown(practice_json)

    practice_json_path = resource_dir / "practice.json"
    practice_md_path = resource_dir / "practice.md"
    _write_json(practice_json_path, practice_json)
    _write_text(practice_md_path, practice_markdown)

    for item in code_files:
        if not isinstance(item, dict):
            continue
        safe_path = _safe_relative_code_path(item.get("path"))
        if safe_path is None:
            continue
        _write_text(resource_dir / safe_path, str(item.get("content") or ""))

    entry_file = str(practice_json["run_guide"].get("entry_file") or "").strip()
    safe_entry_file = _safe_relative_code_path(entry_file)
    entry_file_path = (
        _repo_relative_path(resource_dir / safe_entry_file) if safe_entry_file is not None else None
    )

    status = "ready" if validation["valid"] else "invalid"
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=practice_json["topic"],
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=_build_main_files(
            json_path=_repo_relative_path(practice_json_path),
            md_path=_repo_relative_path(practice_md_path),
            entry_file_path=entry_file_path,
        ),
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "schema_version": validation["schema_version"],
            "language": validation["language"],
            "step_count": validation["step_count"],
            "file_count": validation["file_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={
            "language": language,
            "file_count": validation["file_count"],
            "step_count": validation["step_count"],
            "entry_file": entry_file or None,
        },
    )
    append_manifest_entry(user_id, entry)
    return _build_result_payload(entry=entry)


def persist_ppt_resource(payload: dict, generated: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if not isinstance(generated, dict):
        raise ValueError("generated ppt content must be a dict")

    user_id, syllabus_id, topic = _payload_ids_and_topic(payload)
    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("ppt")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    title = str(generated.get("title") or f"{topic} PPT").strip() or f"{topic} PPT"
    ppt_json = {
        "schema_version": str(generated.get("schema_version") or GENERATIVE_PPT_SCHEMA_VERSION),
        "title": title,
        "topic": str(generated.get("topic") or topic).strip() or topic,
        "summary": str(generated.get("summary") or "").strip(),
        "theme": str(generated.get("theme") or "").strip(),
        "slide_style": str(generated.get("slide_style") or "").strip(),
        "slides": generated.get("slides") if isinstance(generated.get("slides"), list) else [],
    }
    validation = validate_ppt_payload(ppt_json)
    ppt_markdown = render_ppt_markdown(ppt_json)

    ppt_json_path = resource_dir / "ppt.json"
    ppt_md_path = resource_dir / "ppt.md"
    _write_json(ppt_json_path, ppt_json)
    _write_text(ppt_md_path, ppt_markdown)

    status = "ready" if validation["valid"] else "invalid"
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=ppt_json["topic"],
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=_build_main_files(
            json_path=_repo_relative_path(ppt_json_path),
            md_path=_repo_relative_path(ppt_md_path),
        ),
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "schema_version": validation["schema_version"],
            "slide_count": validation["slide_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={
            "slide_count": validation["slide_count"],
            "theme": ppt_json["theme"] or None,
            "slide_style": ppt_json["slide_style"] or None,
        },
    )
    append_manifest_entry(user_id, entry)
    return _build_result_payload(entry=entry)


def generate_coding_practice(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single coding practice resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_coding_practice"):
        raise ValueError("agent_adapter must expose generate_coding_practice(payload)")

    generated = agent_adapter.generate_coding_practice(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_coding_practice must return a dict")
    return persist_coding_practice_resource(payload, generated)


def generate_ppt(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single ppt resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_ppt"):
        raise ValueError("agent_adapter must expose generate_ppt(payload)")

    generated = agent_adapter.generate_ppt(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_ppt must return a dict")
    return persist_ppt_resource(payload, generated)


def persist_generated_resource(payload: dict, generated_content: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    resource_type = _normalize_resource_type(payload.get("resource_type"))
    if resource_type == "documents":
        return persist_structured_document_resource(payload, generated_content)
    if resource_type == "mindmap":
        return persist_mindmap_resource(payload, generated_content)
    if resource_type == "quiz":
        return persist_quiz_resource(payload, generated_content)
    if resource_type == "coding_practice":
        return persist_coding_practice_resource(payload, generated_content)
    if resource_type == "ppt":
        return persist_ppt_resource(payload, generated_content)
    raise ValueError(f"resource_type {resource_type} is not implemented yet")


def generate_resource(payload: dict, agent_adapter: Any) -> dict:
    """Unified generative resource dispatcher."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    resource_type = _normalize_resource_type(payload.get("resource_type"))
    if resource_type == "documents":
        return generate_structured_document(payload, agent_adapter)
    if resource_type == "mindmap":
        return generate_mindmap(payload, agent_adapter)
    if resource_type == "quiz":
        return generate_quiz(payload, agent_adapter)
    if resource_type == "coding_practice":
        return generate_coding_practice(payload, agent_adapter)
    if resource_type == "ppt":
        return generate_ppt(payload, agent_adapter)

    raise ValueError(f"resource_type {resource_type} is not implemented yet")
