"""Generative resource agent package.

The public task module still exposes the callable resource-generation helpers.
This package holds stable contracts shared by those helpers and their tests.
"""

from .contracts import (
	GENERATIVE_DOCUMENT_SCHEMA_VERSION,
	GENERATIVE_MANIFEST_VERSION,
	GENERATIVE_QUIZ_SCHEMA_VERSION,
	GENERATIVE_RESOURCE_TYPES,
	MINDMAP_ALLOWED_DIAGRAM_PREFIXES,
)

__all__ = [
	"GENERATIVE_DOCUMENT_SCHEMA_VERSION",
	"GENERATIVE_MANIFEST_VERSION",
	"GENERATIVE_QUIZ_SCHEMA_VERSION",
	"GENERATIVE_RESOURCE_TYPES",
	"MINDMAP_ALLOWED_DIAGRAM_PREFIXES",
]
