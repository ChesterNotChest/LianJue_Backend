import re
from typing import Optional


def clean_llm_response(response: str) -> str:
    """Remove markdown fences like ```json and trailing ``` from model output."""
    if not response:
        return ""
    # strip leading ```json or ``` and whitespace
    response = re.sub(r'^```\s*json\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^```\s*', '', response, flags=re.IGNORECASE)
    # strip trailing ```
    response = re.sub(r'\s*```\s*$', '', response)
    return response.strip()


def preprocess_markdown_content(md: str) -> str:
    """Lightweight markdown cleaning: remove isolated page numbers and compress blank lines."""
    if not md:
        return ""
    # remove lines that are only numbers (likely page numbers)
    md = re.sub(r'^\s*\d+\s*$\n?', '', md, flags=re.MULTILINE)
    # compress multiple blank lines to two
    md = re.sub(r'\n{3,}', '\n\n', md)
    # remove trailing/leading whitespace
    md = md.strip()
    return md
