from datetime import datetime
import os
import time
from typing import Union

from repositories.file_repo import create_file, get_file_by_id
from repositories.filegraph_repo import list_files_by_graph
from repositories.material_repo import list_materials_by_syllabus
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.syllabusmaterial_repo import get_syllabusmaterials_by_material
from schemas.file import File


def add_file(save_path, file_name, file_bytes: Union[bytes, str] = None, upload_time: str = None):
    if not upload_time:
        upload_time = datetime.utcnow().isoformat()

    if save_path:
        abs_path = os.path.abspath(os.path.join(save_path, file_name))
    else:
        abs_path = os.path.abspath(file_name)

    if file_bytes is not None:
        db_exists = File.query.filter_by(path=abs_path).first() is not None
        fs_exists = os.path.exists(abs_path)
        if db_exists or fs_exists:
            base, ext = os.path.splitext(abs_path)
            abs_path = f'{base}_{int(time.time())}{ext}'

        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        content = file_bytes if isinstance(file_bytes, (bytes, bytearray)) else str(file_bytes).encode('utf-8')
        with open(abs_path, 'wb') as wf:
            wf.write(content)

        file = create_file(abs_path, upload_time=upload_time)
        return file.file_id

    file = create_file(abs_path, upload_time=upload_time)
    return file.file_id


def list_all_files_brief_info(graph_id_list: list = None, syllabus_id_list: list = None, material_id_list: list = None):
    def _normalize_id_list(values):
        if not isinstance(values, list):
            return []
        out = []
        for value in values:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
        return out

    def _resolve_file_path(file_id=None, fallback_path=None):
        file = get_file_by_id(file_id) if file_id is not None else None
        if file:
            return getattr(file, 'file_id', file_id), getattr(file, 'path', fallback_path)
        return file_id, fallback_path

    def _build_file_brief(file_id, path, source, week_index_list=None):
        if not path:
            return None
        item = {
            'file_id': file_id,
            'filename': os.path.basename(path),
            'path': path,
            'source': source,
        }
        if week_index_list:
            item['week_index_list'] = sorted({
                int(week_index)
                for week_index in week_index_list
                if week_index is not None
            })
        return item

    def _append_unique(result, seen_keys, item):
        if not item:
            return
        dedupe_key = (item['source'], item['file_id'], item['path'])
        if dedupe_key in seen_keys:
            return
        seen_keys.add(dedupe_key)
        result.append(item)

    result = []
    seen_keys = set()

    for graph_id in _normalize_id_list(graph_id_list):
        for file_id in list_files_by_graph(graph_id):
            resolved_file_id, resolved_path = _resolve_file_path(file_id=file_id)
            _append_unique(
                result,
                seen_keys,
                _build_file_brief(
                    file_id=resolved_file_id,
                    path=resolved_path,
                    source='graph-file',
                ),
            )

    for syllabus_id in _normalize_id_list(syllabus_id_list):
        syllabus = get_syllabus_by_id(syllabus_id)
        if not syllabus:
            continue

        resolved_calendar_file_id, resolved_calendar_path = _resolve_file_path(
            file_id=getattr(syllabus, 'file_id', None),
            fallback_path=getattr(syllabus, 'edu_calendar_path', None),
        )
        _append_unique(
            result,
            seen_keys,
            _build_file_brief(
                file_id=resolved_calendar_file_id,
                path=resolved_calendar_path,
                source='syllabus-file',
            ),
        )

        for material in list_materials_by_syllabus(syllabus_id):
            resolved_material_file_id, resolved_material_path = _resolve_file_path(
                file_id=getattr(material, 'file_id', None),
                fallback_path=getattr(material, 'pdf_path', None),
            )
            week_index_list = [
                binding.week_index
                for binding in get_syllabusmaterials_by_material(getattr(material, 'material_id', None))
                if getattr(binding, 'syllabus_id', None) == syllabus_id
            ]
            _append_unique(
                result,
                seen_keys,
                _build_file_brief(
                    file_id=resolved_material_file_id,
                    path=resolved_material_path,
                    source='syllabus-file',
                    week_index_list=week_index_list,
                ),
            )

    return result


def get_file_detail_info(file_id: int):
    try:
        normalized_file_id = int(file_id)
    except (TypeError, ValueError):
        return None

    file = get_file_by_id(normalized_file_id)
    if not file:
        return None

    path = getattr(file, 'path', None)
    upload_time = getattr(file, 'upload_time', None)

    return {
        'file_id': getattr(file, 'file_id', normalized_file_id),
        'filename': os.path.basename(path) if path else None,
        'path': path,
        'upload_time': upload_time.isoformat() if hasattr(upload_time, 'isoformat') else upload_time,
    }
