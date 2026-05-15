def render_document_markdown(document: dict) -> str:
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
