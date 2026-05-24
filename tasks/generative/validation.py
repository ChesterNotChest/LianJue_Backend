import re
from ast import parse as ast_parse
from pathlib import PurePosixPath

from tasks.generative.contracts import (
    GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
    GENERATIVE_DOCUMENT_SCHEMA_VERSION,
    GENERATIVE_PPT_SCHEMA_VERSION,
    GENERATIVE_QUIZ_SCHEMA_VERSION,
    MINDMAP_ALLOWED_DIAGRAM_PREFIXES,
)


def strip_mermaid_fence(text: str) -> str:
    stripped = str(text or "").strip()
    fenced_match = re.match(r"^```(?:mermaid)?\s*(.*?)\s*```$", stripped, flags=re.S)
    if fenced_match:
        return fenced_match.group(1).strip()
    return stripped


def validate_mermaid_text(text: str) -> dict:
    cleaned_text = strip_mermaid_fence(text)
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

    if diagram_type == "mindmap":
        node_count = sum(1 for line in content_lines if not line.lstrip().startswith("::"))
    else:
        node_count = sum(
            1 for line in content_lines if any(token in line for token in ("--", "==", "((", "[", "{"))
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
        if not str(section.get("heading") or "").strip():
            errors.append(f"section #{index} missing heading")
        if not str(section.get("body") or "").strip():
            errors.append(f"section #{index} missing body")
        for field_name in ("key_points", "examples", "pitfalls", "checklist", "evidence"):
            if field_name in section and not isinstance(section.get(field_name), list):
                warnings.append(f"section #{index} {field_name} should be a list when provided")

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


def _is_safe_relative_resource_path(path_value: str) -> bool:
    normalized = str(path_value or "").strip().replace("\\", "/")
    if not normalized:
        return False
    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute():
        return False
    if any(part in {"", ".", ".."} for part in pure_path.parts):
        return False
    return True


def validate_coding_practice_payload(practice: dict) -> dict:
    errors = []
    warnings = []

    if not isinstance(practice, dict):
        return {
            "valid": False,
            "errors": ["coding practice payload must be a dict"],
            "warnings": warnings,
            "method": "schema+python_syntax",
            "schema_version": None,
            "language": None,
            "step_count": 0,
            "file_count": 0,
        }

    schema_version = str(practice.get("schema_version") or "").strip()
    if schema_version != GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION}")

    title = str(practice.get("title") or "").strip()
    topic = str(practice.get("topic") or "").strip()
    language = str(practice.get("language") or "").strip()
    summary = str(practice.get("summary") or "").strip()
    if not title:
        errors.append("title is required")
    if not topic:
        errors.append("topic is required")
    if not language:
        errors.append("language is required")
    if not summary:
        errors.append("summary is required")

    steps = practice.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        steps = []

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step #{index} must be a dict")
            continue
        if not str(step.get("title") or "").strip():
            errors.append(f"step #{index} missing title")
        if not str(step.get("instruction") or "").strip():
            errors.append(f"step #{index} missing instruction")

    code_files = practice.get("code_files")
    if not isinstance(code_files, list) or not code_files:
        errors.append("code_files must be a non-empty list")
        code_files = []

    python_file_count = 0
    for index, item in enumerate(code_files, start=1):
        if not isinstance(item, dict):
            errors.append(f"code_file #{index} must be a dict")
            continue
        file_path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if not file_path:
            errors.append(f"code_file #{index} missing path")
            continue
        if not _is_safe_relative_resource_path(file_path):
            errors.append(f"code_file #{index} path must be a safe relative path")
        if not content.strip():
            errors.append(f"code_file #{index} missing content")
        if file_path.replace("\\", "/").endswith(".py"):
            python_file_count += 1
            try:
                ast_parse(content)
            except SyntaxError as exc:
                errors.append(f"code_file #{index} python syntax error: {exc.msg}")

    run_guide = practice.get("run_guide")
    if not isinstance(run_guide, dict):
        errors.append("run_guide must be a dict")
        run_guide = {}

    entry_file = str(run_guide.get("entry_file") or "").strip()
    command = str(run_guide.get("command") or "").strip()
    if not entry_file:
        errors.append("run_guide missing entry_file")
    elif not _is_safe_relative_resource_path(entry_file):
        errors.append("run_guide entry_file must be a safe relative path")
    if not command:
        errors.append("run_guide missing command")

    if language == "python" and python_file_count == 0:
        errors.append("python coding practice must contain at least one .py code file")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "method": "schema+python_syntax",
        "schema_version": schema_version or None,
        "language": language or None,
        "step_count": len(steps),
        "file_count": len(code_files),
    }


def validate_ppt_payload(ppt: dict) -> dict:
    errors = []
    warnings = []

    if not isinstance(ppt, dict):
        return {
            "valid": False,
            "errors": ["ppt payload must be a dict"],
            "warnings": warnings,
            "method": "schema",
            "schema_version": None,
            "slide_count": 0,
        }

    schema_version = str(ppt.get("schema_version") or "").strip()
    if schema_version != GENERATIVE_PPT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GENERATIVE_PPT_SCHEMA_VERSION}")

    title = str(ppt.get("title") or "").strip()
    topic = str(ppt.get("topic") or "").strip()
    summary = str(ppt.get("summary") or "").strip()
    if not title:
        errors.append("title is required")
    if not topic:
        errors.append("topic is required")
    if not summary:
        errors.append("summary is required")

    slides = ppt.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides must be a non-empty list")
        slides = []

    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slide #{index} must be a dict")
            continue
        if not str(slide.get("title") or "").strip():
            errors.append(f"slide #{index} missing title")
        if not str(slide.get("body") or "").strip():
            errors.append(f"slide #{index} missing body")
        bullets = slide.get("bullets")
        if not isinstance(bullets, list) or not bullets:
            errors.append(f"slide #{index} bullets must be a non-empty list")
            bullets = []
        for bullet_index, bullet in enumerate(bullets, start=1):
            if not str(bullet or "").strip():
                errors.append(f"slide #{index} bullet #{bullet_index} is empty")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "method": "schema",
        "schema_version": schema_version or None,
        "slide_count": len(slides),
    }
