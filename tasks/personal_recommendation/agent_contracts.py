from dataclasses import dataclass, field
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator


@dataclass
class PersonalRecommendationDeps:
    state: Dict[str, Any] = field(default_factory=dict)


class PersonalRecommendationResult(BaseModel):
    success: bool = True
    recommendation: Optional[dict] = None
    error_message: str = ""
    error_code: str = ""

    @field_validator("recommendation", mode="before")
    @classmethod
    def _parse_recommendation_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return None
            return parsed if isinstance(parsed, dict) else None
        return value
