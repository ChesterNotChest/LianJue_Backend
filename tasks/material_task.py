import os

from repositories.material_repo import get_material_by_id


def _is_missing_path(path_value) -> bool:
    if not path_value or not isinstance(path_value, str):
        return True
    return not os.path.exists(path_value)


def get_material_status(material_id: int) -> dict:
    """Return material status flags for draft/final readiness."""
    material = get_material_by_id(material_id)
    if not material:
        return None

    draft_path = getattr(material, 'draft_material_path', None)
    final_path = getattr(material, 'material_path', None)

    return {
        'is_material_draft_path_null': _is_missing_path(draft_path),
        'is_material_path_null': _is_missing_path(final_path),
    }
