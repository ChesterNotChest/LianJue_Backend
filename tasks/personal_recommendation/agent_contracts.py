from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel


@dataclass
class PersonalRecommendationDeps:
    state: Dict[str, Any] = field(default_factory=dict)


class PersonalRecommendationResult(BaseModel):
    success: bool = True
    recommendation: Optional[dict] = None
    error_message: str = ""
    error_code: str = ""
