from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel


@dataclass
class LearningProfileDeps:
	state: Dict[str, Any] = field(default_factory=dict)


class LearningProfileResult(BaseModel):
	success: bool = True
	profile: Optional[dict] = None
	error_message: str = ''
	error_code: str = ''
