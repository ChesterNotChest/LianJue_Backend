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