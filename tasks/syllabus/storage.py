import json
import re
from datetime import datetime
from pathlib import Path


def validate_syllabus_period(period: list) -> bool:
    if not isinstance(period, list):
        print("   [UPDATE] `period` must be a list.")
        return False
    if not all(isinstance(entry, dict) for entry in period):
        print("   [UPDATE] each `period` entry must be a dict.")
        return False
    if any(entry.get('week_index') is None for entry in period):
        print("   [UPDATE] every `period` entry must contain `week_index`.")
        return False
    return True


def resolve_repo_path(path_value, backend_root: Path):
    if not path_value or not isinstance(path_value, str):
        return None

    raw_path = path_value.strip()
    if not raw_path:
        return None

    normalized = raw_path.replace('\\', '/')
    candidates = []

    if re.match(r'^[A-Za-z]:/', normalized):
        drive = normalized[0].lower()
        candidates.append(Path(normalized))
        candidates.append(Path('/mnt') / drive / normalized[3:])
    else:
        normalized_path = Path(normalized)
        raw_obj = Path(raw_path)
        if normalized_path.is_absolute():
            candidates.append(normalized_path)
        else:
            candidates.append(backend_root / normalized_path)
            candidates.append(normalized_path)
        if raw_obj not in candidates:
            candidates.append(raw_obj)

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if candidate.exists():
            return candidate

    return unique_candidates[0] if unique_candidates else None


def read_json_from_path(path_value: str, backend_root: Path):
    try:
        resolved_path = resolve_repo_path(path_value, backend_root)
        if resolved_path is None:
            return None
        return json.loads(resolved_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"   [UPDATE] failed to read/parse json file: {e}")
        return None


def write_json_to_path(path_value: str, payload: dict, backend_root: Path) -> bool:
    try:
        resolved_path = resolve_repo_path(path_value, backend_root)
        if resolved_path is None:
            return False
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception as e:
        print(f"   [UPDATE] failed to save json file: {e}")
        return False


def parse_day_one_string(day_one: str):
    if not day_one:
        return None
    try:
        if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', day_one):
            return datetime.strptime(day_one, '%Y-%m-%d')
        if re.match(r'^\d{1,2}-\d{1,2}$', day_one):
            month, day = day_one.split('-')
            return datetime(datetime.utcnow().year, int(month), int(day))
        return datetime.fromisoformat(day_one)
    except Exception:
        return None


def is_missing_path(path_value) -> bool:
    return not isinstance(path_value, str) or not path_value.strip()
