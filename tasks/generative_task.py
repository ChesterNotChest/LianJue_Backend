import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from constant import BasePath


GENERATIVE_RESOURCE_TYPES = ("documents", "mindmap", "quiz", "coding_practice")
MINDMAP_ALLOWED_DIAGRAM_PREFIXES = ("mindmap", "flowchart", "graph")
GENERATIVE_MANIFEST_VERSION = "v1"
GENERATIVE_QUIZ_SCHEMA_VERSION = "v1"
GENERATIVE_DOCUMENT_SCHEMA_VERSION = "v1"


def _get_backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _get_generative_root() -> Path:
    return _get_backend_root() / BasePath.GENERATIVE_ROOT.value.lstrip("/")


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _normalize_resource_type(resource_type: str) -> str:
    normalized = str(resource_type or "").strip()
    if normalized not in GENERATIVE_RESOURCE_TYPES:
        raise ValueError(
            "resource_type must be one of "
            + "/".join(GENERATIVE_RESOURCE_TYPES)
        )
    return normalized


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _new_resource_id(resource_type: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{resource_type}-{timestamp}-{uuid4().hex[:6]}"


def _repo_relative_path(path_value: Path) -> str:
    return path_value.resolve().relative_to(_get_backend_root().resolve()).as_posix()


def _read_json(path_value: Path, default: Any = None) -> Any:
    if not path_value.exists():
        return default
    try:
        return json.loads(path_value.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json file: {path_value}") from exc


def _write_json(path_value: Path, payload: Dict[str, Any]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_text(path_value: Path, content: str) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(content, encoding="utf-8")


def get_generative_user_root(user_id: int) -> Path:
    """Return the absolute generative workspace root for a user."""
    normalized_user_id = _normalize_positive_int(user_id, "user_id")
    return _get_generative_root() / f"user_{normalized_user_id}"


def ensure_generative_workspace(user_id: int) -> dict:
    """Create the per-user generative workspace and manifest if absent."""
    user_root = get_generative_user_root(user_id)
    user_root.mkdir(parents=True, exist_ok=True)

    directories = {
        "documents_dir": user_root / "documents",
        "mindmap_dir": user_root / "mindmap",
        "quiz_dir": user_root / "quiz",
        "coding_practice_dir": user_root / "coding_practice",
    }
    for path_value in directories.values():
        path_value.mkdir(parents=True, exist_ok=True)

    manifest_path = user_root / "manifest.json"
    if not manifest_path.exists():
        now_ts = _utc_timestamp()
        _write_json(
            manifest_path,
            {
                "version": GENERATIVE_MANIFEST_VERSION,
                "user_id": _normalize_positive_int(user_id, "user_id"),
                "resource_count": 0,
                "updated_at": now_ts,
                "resources": [],
            },
        )

    return {
        "user_root": _repo_relative_path(user_root),
        "documents_dir": _repo_relative_path(directories["documents_dir"]),
        "mindmap_dir": _repo_relative_path(directories["mindmap_dir"]),
        "quiz_dir": _repo_relative_path(directories["quiz_dir"]),
        "coding_practice_dir": _repo_relative_path(directories["coding_practice_dir"]),
        "manifest_path": _repo_relative_path(manifest_path),
    }


def load_manifest(user_id: int) -> dict:
    """Load the user-level manifest from disk."""
    ensure_generative_workspace(user_id)
    manifest_path = get_generative_user_root(user_id) / "manifest.json"
    manifest = _read_json(manifest_path, default=None)
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain a JSON object")
    manifest.setdefault("user_id", _normalize_positive_int(user_id, "user_id"))
    manifest.setdefault("resources", [])
    if not isinstance(manifest["resources"], list):
        raise ValueError("manifest.json resources must be a list")
    manifest.setdefault("version", GENERATIVE_MANIFEST_VERSION)
    manifest["resource_count"] = len(manifest["resources"])
    manifest.setdefault("updated_at", _utc_timestamp())
    return manifest


def save_manifest(user_id: int, manifest: dict) -> None:
    """Persist the user-level manifest."""
    manifest["version"] = GENERATIVE_MANIFEST_VERSION
    manifest["user_id"] = _normalize_positive_int(user_id, "user_id")
    manifest["resource_count"] = len(manifest.get("resources") or [])
    manifest["updated_at"] = _utc_timestamp()
    manifest_path = get_generative_user_root(user_id) / "manifest.json"
    _write_json(manifest_path, manifest)


def append_manifest_entry(user_id: int, entry: dict) -> dict:
    """Append a single resource entry to the user manifest."""
    manifest = load_manifest(user_id)
    manifest["resources"].append(entry)
    save_manifest(user_id, manifest)
    return entry


def _strip_mermaid_fence(text: str) -> str:
    stripped = str(text or "").strip()
    fenced_match = re.match(r"^```(?:mermaid)?\s*(.*?)\s*```$", stripped, flags=re.S)
    if fenced_match:
        return fenced_match.group(1).strip()
    return stripped


def validate_mermaid_text(text: str) -> dict:
    """Perform lightweight validation for Mermaid source text."""
    cleaned_text = _strip_mermaid_fence(text)
    lines = [line.rstrip() for line in cleaned_text.splitlines() if line.strip()]
    errors = []
    warnings = []

    if not lines:
        errors.append("mermaid content is empty")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "method": "syntax",
            "diagram_type": None,
            "node_count": 0,
            "cleaned_text": cleaned_text,
        }

    first_line = lines[0].strip()
    if not first_line.startswith(MINDMAP_ALLOWED_DIAGRAM_PREFIXES):
        errors.append("first line must start with mindmap, flowchart, or graph")

    diagram_type = first_line.split()[0]
    content_lines = [line for line in lines[1:] if line.strip()]
    if not content_lines:
        errors.append("mermaid diagram must contain at least one node line")

    node_count = 0
    if diagram_type == "mindmap":
        node_count = sum(1 for line in content_lines if not line.lstrip().startswith("::"))
    else:
        node_count = sum(
            1
            for line in content_lines
            if any(token in line for token in ("--", "==", "((", "[", "{"))
        )

    if node_count <= 0:
        errors.append("mermaid diagram must contain parseable nodes or edges")

    if "```" in cleaned_text:
        warnings.append("embedded code fence markers were removed before validation")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "method": "syntax",
        "diagram_type": diagram_type,
        "node_count": node_count,
        "cleaned_text": cleaned_text,
    }


def validate_quiz_payload(quiz: dict) -> dict:
    """Perform lightweight schema validation for generated quiz payloads."""
    errors = []
    warnings = []

    if not isinstance(quiz, dict):
        return {
            "valid": False,
            "errors": ["quiz payload must be a dict"],
            "warnings": warnings,
            "method": "schema",
            "schema_version": None,
            "question_count": 0,
        }

    schema_version = str(quiz.get("schema_version") or "").strip()
    if schema_version != GENERATIVE_QUIZ_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GENERATIVE_QUIZ_SCHEMA_VERSION}")

    title = str(quiz.get("title") or "").strip()
    if not title:
        errors.append("title is required")

    questions = quiz.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("questions must be a non-empty list")
        questions = []

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            errors.append(f"question #{index} must be a dict")
            continue

        q_type = str(question.get("type") or "").strip()
        stem = str(question.get("stem") or "").strip()
        answer = question.get("answer")
        explanation = str(question.get("explanation") or "").strip()

        if not q_type:
            errors.append(f"question #{index} missing type")
        if not stem:
            errors.append(f"question #{index} missing stem")
        if answer in (None, ""):
            errors.append(f"question #{index} missing answer")
        if not explanation:
            errors.append(f"question #{index} missing explanation")

        if q_type == "single_choice":
            options = question.get("options")
            if not isinstance(options, list) or len(options) < 2:
                errors.append(f"question #{index} single_choice requires options")
        elif q_type == "judge":
            if not isinstance(answer, bool):
                errors.append(f"question #{index} judge answer must be boolean")
        elif q_type and q_type not in {"short_answer", "single_choice", "judge"}:
            warnings.append(f"question #{index} uses unrecognized type {q_type}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "method": "schema",
        "schema_version": schema_version or None,
        "question_count": len(questions),
    }


def validate_document_payload(document: dict) -> dict:
    """Perform lightweight schema validation for generated document payloads."""
    errors = []
    warnings = []

    if not isinstance(document, dict):
        return {
            "valid": False,
            "errors": ["document payload must be a dict"],
            "warnings": warnings,
            "method": "schema",
            "schema_version": None,
            "section_count": 0,
        }

    schema_version = str(document.get("schema_version") or "").strip()
    if schema_version != GENERATIVE_DOCUMENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GENERATIVE_DOCUMENT_SCHEMA_VERSION}")

    title = str(document.get("title") or "").strip()
    summary = str(document.get("summary") or "").strip()
    if not title:
        errors.append("title is required")
    if not summary:
        errors.append("summary is required")

    sections = document.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty list")
        sections = []

    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            errors.append(f"section #{index} must be a dict")
            continue
        heading = str(section.get("heading") or "").strip()
        body = str(section.get("body") or "").strip()
        if not heading:
            errors.append(f"section #{index} missing heading")
        if not body:
            errors.append(f"section #{index} missing body")

    extension_reading = document.get("extension_reading")
    if extension_reading is not None and not isinstance(extension_reading, list):
        errors.append("extension_reading must be a list when provided")
        extension_reading = []
    elif extension_reading is None:
        extension_reading = []

    for index, item in enumerate(extension_reading, start=1):
        if not isinstance(item, dict):
            warnings.append(f"extension_reading #{index} is not a dict")
            continue
        if not str(item.get("title") or "").strip():
            warnings.append(f"extension_reading #{index} missing title")
        if not str(item.get("reason") or "").strip():
            warnings.append(f"extension_reading #{index} missing reason")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "method": "schema",
        "schema_version": schema_version or None,
        "section_count": len(sections),
    }


def render_document_markdown(document: dict) -> str:
    """Render generated structured document JSON into Markdown."""
    title = str(document.get("title") or "Document").strip() or "Document"
    topic = str(document.get("topic") or "").strip()
    summary = str(document.get("summary") or "").strip()
    sections = document.get("sections") if isinstance(document.get("sections"), list) else []
    extension_reading = document.get("extension_reading") if isinstance(document.get("extension_reading"), list) else []

    lines = [f"# {title}", ""]
    if topic:
        lines.extend([f"Topic: {topic}", ""])
    if summary:
        lines.extend([summary, ""])

    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        body = str(section.get("body") or "").strip()
        if heading:
            lines.extend([f"## {heading}", ""])
        lines.extend([body or "N/A", ""])

    if extension_reading:
        lines.extend(["## Extension Reading", ""])
        for item in extension_reading:
            if not isinstance(item, dict):
                continue
            item_title = str(item.get("title") or "").strip() or "Untitled"
            item_reason = str(item.get("reason") or "").strip()
            lines.append(f"- {item_title}")
            if item_reason:
                lines.append(f"  - Reason: {item_reason}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_quiz_markdown(quiz: dict) -> str:
    """Render generated quiz JSON into a readable Markdown document."""
    title = str(quiz.get("title") or "Quiz").strip() or "Quiz"
    topic = str(quiz.get("topic") or "").strip()
    questions = quiz.get("questions") if isinstance(quiz.get("questions"), list) else []

    lines = [f"# {title}", ""]
    if topic:
        lines.extend([f"Topic: {topic}", ""])

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            continue
        q_type = str(question.get("type") or "unknown").strip() or "unknown"
        difficulty = str(question.get("difficulty") or "").strip()
        stem = str(question.get("stem") or "").strip()
        answer = question.get("answer")
        explanation = str(question.get("explanation") or "").strip()
        knowledge_points = question.get("knowledge_points") if isinstance(question.get("knowledge_points"), list) else []

        heading = f"## Q{index}. {q_type}"
        if difficulty:
            heading += f" ({difficulty})"
        lines.extend([heading, "", stem or "No stem provided.", ""])

        if q_type == "single_choice" and isinstance(question.get("options"), list):
            for opt_index, option in enumerate(question["options"]):
                label = chr(ord("A") + opt_index)
                lines.append(f"- {label}. {option}")
            lines.append("")

        answer_text = "True" if answer is True else "False" if answer is False else str(answer)
        lines.extend([f"Answer: {answer_text}", ""])
        lines.extend([f"Explanation: {explanation or 'N/A'}", ""])

        if knowledge_points:
            lines.extend([f"Knowledge Points: {', '.join(map(str, knowledge_points))}", ""])

    return "\n".join(lines).strip() + "\n"


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


def generate_mindmap(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single mindmap resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_mindmap"):
        raise ValueError("agent_adapter must expose generate_mindmap(payload)")

    user_id = _normalize_positive_int(payload.get("user_id"), "user_id")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic is required")

    syllabus_id_raw = payload.get("syllabus_id")
    syllabus_id = None
    if syllabus_id_raw not in (None, ""):
        syllabus_id = _normalize_positive_int(syllabus_id_raw, "syllabus_id")

    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("mindmap")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    generated = agent_adapter.generate_mindmap(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_mindmap must return a dict")

    title = str(generated.get("title") or topic).strip() or topic
    mermaid_text = str(generated.get("mermaid") or "").strip()
    if not mermaid_text:
        raise ValueError("agent output must include non-empty mermaid text")

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
    main_files = {
        "json_path": _repo_relative_path(mindmap_json_path),
        "mermaid_path": _repo_relative_path(mermaid_path),
    }
    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=topic,
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files=main_files,
        status=status,
        validation={
            "valid": validation["valid"],
            "method": validation["method"],
            "diagram_type": validation["diagram_type"],
            "node_count": validation["node_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        metadata={
            "knowledge_item_count": len(mindmap_json["knowledge_items"]),
        },
    )

    append_manifest_entry(user_id, entry)

    return {
        "success": True,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "title": title,
        "topic": topic,
        "status": status,
        "resource_dir": _repo_relative_path(resource_dir),
        "json_path": entry["main_files"]["json_path"],
        "mermaid_path": entry["main_files"]["mermaid_path"],
        "validation": entry["validation"],
    }


def generate_structured_document(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single structured document resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_document"):
        raise ValueError("agent_adapter must expose generate_document(payload)")

    user_id = _normalize_positive_int(payload.get("user_id"), "user_id")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic is required")

    syllabus_id_raw = payload.get("syllabus_id")
    syllabus_id = None
    if syllabus_id_raw not in (None, ""):
        syllabus_id = _normalize_positive_int(syllabus_id_raw, "syllabus_id")

    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("documents")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    generated = agent_adapter.generate_document(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_document must return a dict")

    title = str(generated.get("title") or f"{topic} 讲解文档").strip() or f"{topic} 讲解文档"
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
        main_files={
            "json_path": _repo_relative_path(document_json_path),
            "md_path": _repo_relative_path(document_md_path),
        },
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

    return {
        "success": True,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "title": title,
        "topic": document_json["topic"],
        "status": status,
        "resource_dir": _repo_relative_path(resource_dir),
        "json_path": entry["main_files"]["json_path"],
        "md_path": entry["main_files"]["md_path"],
        "validation": entry["validation"],
    }


def generate_quiz(payload: dict, agent_adapter: Any) -> dict:
    """Generate a single quiz resource bundle from an agent adapter."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    if agent_adapter is None or not hasattr(agent_adapter, "generate_quiz"):
        raise ValueError("agent_adapter must expose generate_quiz(payload)")

    user_id = _normalize_positive_int(payload.get("user_id"), "user_id")
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic is required")

    syllabus_id_raw = payload.get("syllabus_id")
    syllabus_id = None
    if syllabus_id_raw not in (None, ""):
        syllabus_id = _normalize_positive_int(syllabus_id_raw, "syllabus_id")

    ensure_generative_workspace(user_id)
    resource_type = _normalize_resource_type("quiz")
    resource_id = _new_resource_id(resource_type)
    resource_dir = get_generative_user_root(user_id) / resource_type / resource_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    generated = agent_adapter.generate_quiz(payload)
    if not isinstance(generated, dict):
        raise ValueError("generate_quiz must return a dict")

    title = str(generated.get("title") or f"{topic} 练习题").strip() or f"{topic} 练习题"
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
    question_types = []
    for question in quiz_json["questions"]:
        if isinstance(question, dict) and question.get("type"):
            question_types.append(str(question["type"]))

    entry = _build_resource_entry(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        topic=quiz_json["topic"],
        syllabus_id=syllabus_id,
        resource_dir=resource_dir,
        main_files={
            "json_path": _repo_relative_path(quiz_json_path),
            "md_path": _repo_relative_path(quiz_md_path),
        },
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

    return {
        "success": True,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "title": title,
        "topic": quiz_json["topic"],
        "status": status,
        "resource_dir": _repo_relative_path(resource_dir),
        "json_path": entry["main_files"]["json_path"],
        "md_path": entry["main_files"]["md_path"],
        "validation": entry["validation"],
    }


def generate_resource(payload: dict, agent_adapter: Any) -> dict:
    """Unified generative resource dispatcher.

    Current phase only exposes the `mindmap` resource type. The dispatcher is
    added now so future resource types can share the same contract-level entry.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    resource_type = _normalize_resource_type(payload.get("resource_type"))
    if resource_type == "documents":
        return generate_structured_document(payload, agent_adapter)
    if resource_type == "mindmap":
        return generate_mindmap(payload, agent_adapter)
    if resource_type == "quiz":
        return generate_quiz(payload, agent_adapter)

    raise ValueError(f"resource_type {resource_type} is not implemented yet")
