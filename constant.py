from enum import Enum

class JobStage(Enum):
        PDF_TO_MD = "pdf_to_md"
        MD_TO_TRIPLES = "md_to_triples"
        TRIPLE_TO_KNOWLEDGE = "triple_to_knowledge"
        KNOWLEDGE_TO_SAVE = "knowledge_to_save"

class JobStatus(Enum):
        PENDING = "pending"
        PAUSED = "paused"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"

class BasePath(Enum):
        FILE_CACHE = "file_cache"

        PDF_ROOT = "pdfs"
        MARKDOWN_ROOT = "markdowns"
        TRIPLES_ROOT = "triples"
        KNOWLEDGE_ROOT = "knowledge"
        
        CALENDAR_ROOT = "/schedule/calendar"
        SYLLABUS_DRAFT_ROOT = "/schedule/syllabus_draft"
        SYLLABUS_ROOT = "/schedule/syllabus"
        PERSONAL_SYLLABUS_ROOT = "/schedule/student_alt" # /user_{user_id}

        MATERIAL_DRAFT_ROOT = "/material/draft_material_json" 
        MATERIAL_JSON_ROOT = "/material/material_json"
        MATERIAL_MD_CACHE_ROOT = "/material/material_md_cache"
        MATERIAL_PDF_ROOT = "/material/pdfs"