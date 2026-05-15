import re

from tasks.generative.contracts import (
    GENERATIVE_DOCUMENT_SCHEMA_VERSION,
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
