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


def render_coding_practice_markdown(practice: dict) -> str:
    title = str(practice.get("title") or "Coding Practice").strip() or "Coding Practice"
    topic = str(practice.get("topic") or "").strip()
    summary = str(practice.get("summary") or "").strip()
    language = str(practice.get("language") or "").strip() or "text"
    learning_objectives = (
        practice.get("learning_objectives")
        if isinstance(practice.get("learning_objectives"), list)
        else []
    )
    steps = practice.get("steps") if isinstance(practice.get("steps"), list) else []
    code_files = practice.get("code_files") if isinstance(practice.get("code_files"), list) else []
    run_guide = practice.get("run_guide") if isinstance(practice.get("run_guide"), dict) else {}

    lines = [f"# {title}", ""]
    if topic:
        lines.extend([f"Topic: {topic}", ""])
    if summary:
        lines.extend([summary, ""])

    if learning_objectives:
        lines.extend(["## Learning Objectives", ""])
        for item in learning_objectives:
            text = str(item or "").strip()
            if text:
                lines.append(f"- {text}")
        lines.append("")

    if steps:
        lines.extend(["## Practice Steps", ""])
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            step_title = str(step.get("title") or f"Step {index}").strip() or f"Step {index}"
            instruction = str(step.get("instruction") or "").strip()
            lines.extend([f"### {index}. {step_title}", ""])
            lines.extend([instruction or "N/A", ""])

    if run_guide:
        lines.extend(["## Run Guide", ""])
        entry_file = str(run_guide.get("entry_file") or "").strip()
        command = str(run_guide.get("command") or "").strip()
        expected_output = str(run_guide.get("expected_output") or "").strip()
        if entry_file:
            lines.extend([f"Entry File: `{entry_file}`", ""])
        if command:
            lines.extend([f"Command: `{command}`", ""])
        if expected_output:
            lines.extend(["Expected Output:", "", f"```text\n{expected_output}\n```", ""])

    if code_files:
        lines.extend(["## Code Files", ""])
        for item in code_files:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("path") or "").strip() or "code/main.py"
            purpose = str(item.get("purpose") or "").strip()
            content = str(item.get("content") or "").rstrip()
            heading = f"### `{file_path}`"
            if purpose:
                heading += f" ({purpose})"
            lines.extend([heading, ""])
            lines.extend([f"```{language}", content or "# empty", "```", ""])

    return "\n".join(lines).strip() + "\n"


def render_ppt_markdown(ppt: dict) -> str:
    title = str(ppt.get("title") or "PPT").strip() or "PPT"
    topic = str(ppt.get("topic") or "").strip()
    summary = str(ppt.get("summary") or "").strip()
    theme = str(ppt.get("theme") or "").strip()
    slide_style = str(ppt.get("slide_style") or "").strip()
    slides = ppt.get("slides") if isinstance(ppt.get("slides"), list) else []

    lines = [f"# {title}", ""]
    if topic:
        lines.extend([f"Topic: {topic}", ""])
    if theme:
        lines.extend([f"Theme: {theme}", ""])
    if slide_style:
        lines.extend([f"Style: {slide_style}", ""])
    if summary:
        lines.extend([summary, ""])

    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        slide_title = str(slide.get("title") or f"Slide {index}").strip() or f"Slide {index}"
        bullets = slide.get("bullets") if isinstance(slide.get("bullets"), list) else []
        speaker_notes = str(slide.get("speaker_notes") or "").strip()
        visual_hint = str(slide.get("visual_hint") or "").strip()

        lines.extend([f"## Slide {index}: {slide_title}", ""])
        for bullet in bullets:
            bullet_text = str(bullet or "").strip()
            if bullet_text:
                lines.append(f"- {bullet_text}")
        if bullets:
            lines.append("")
        if visual_hint:
            lines.extend([f"Visual Hint: {visual_hint}", ""])
        if speaker_notes:
            lines.extend(["Speaker Notes:", "", speaker_notes, ""])

    return "\n".join(lines).strip() + "\n"
