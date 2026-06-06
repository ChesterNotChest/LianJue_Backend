import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator


@dataclass
class LearningProfileDeps:
	state: Dict[str, Any] = field(default_factory=dict)


class LearningProfileResult(BaseModel):
	success: bool = True
	profile: Optional[dict] = None
	error_message: str = ''
	error_code: str = ''

	@field_validator('profile', mode='before')
	@classmethod
	def parse_profile_json_string(cls, value: Any) -> Any:
		if not isinstance(value, str):
			return value
		text = value.strip()
		if not text:
			return None
		try:
			parsed = json.loads(text)
		except Exception:
			return value
		return parsed if isinstance(parsed, dict) else value
