
from flask import Blueprint, request, jsonify, send_file
import base64
import os
import logging
from tasks.file_task import (
    get_file_detail_info,
    get_file_download_info,
    list_all_files_brief_info,
    add_file as add_file_task,
)
from tasks import syllabus_task
from config import get_config
import constant

logger = logging.getLogger(__name__)
bp = Blueprint('file_transmit_api', __name__, url_prefix='/api')


@bp.route('/file_upload', methods=['POST'])
def upload_knowledge_source():
    '''
    通讯格式：
    输入：
    {
        "file_name": "example.pdf",   # 必须，包含扩展名
        "file_bytes": "base64_encoded_content",  # 必须
        "upload_time": "2023-10-01T12:00:00Z",  # 可选
        "file_type": "pdf|docx|pptx|..."  # 可选，优先级低于 file_name 后缀
    }

    输出：
    {
        "success": true | false,
        "file": {"file_id": 123},
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = None
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({
            "success": False,
            "file": None,
            "error_message": "invalid json",
            "error_code": "invalid_json"
        }), 400

    file_name = data.get('file_name')
    file_bytes_b64 = data.get('file_bytes')
    upload_time = data.get('upload_time')
    file_type = (data.get('file_type') or '').lower()

    if not file_name or not file_bytes_b64:
        return jsonify({
            "success": False,
            "file": None,
            "error_message": "file_name and file_bytes are required",
            "error_code": "missing_fields"
        }), 400

    try:
        file_bytes = base64.b64decode(file_bytes_b64)
    except Exception as e:
        logger.exception("base64 decode failed")
        return jsonify({
            "success": False,
            "file": None,
            "error_message": "invalid base64 file_bytes",
            "error_code": "invalid_base64"
        }), 400

    # prepare directories
    pdf_root = os.path.abspath(constant.BasePath.PDF_ROOT.value)
    tmp_cache = os.path.abspath(constant.BasePath.FILE_CACHE.value)

    # if already a pdf, write directly via add_file
    lower_name = file_name.lower()
    tmp_path = None
    try:
        if file_type == 'pdf' or lower_name.endswith('.pdf'):
            file_id = add_file_task(pdf_root, file_name, file_bytes=file_bytes, upload_time=upload_time)
            return jsonify({
                "success": True,
                "file": {"file_id": file_id},
                "error_message": "",
                "error_code": ""
            }), 200

        # otherwise: save to temp cache, convert to pdf, save pdf to pdf_root, register
        os.makedirs(tmp_cache, exist_ok=True)
        tmp_path = os.path.join(tmp_cache, file_name)
        with open(tmp_path, 'wb') as wf:
            wf.write(file_bytes)

        # create Document2Markdown instance; doc_to_pdf does not require vl_model for basic conversions
        cfg = get_config() or {}
        proc = cfg.get('PROCESSING_CONFIG', {}) if isinstance(cfg, dict) else {}
        model_path = str(proc.get('MODEL_PATH', './model'))
        from knowlion.doc_parsing_markdown import Document2Markdown

        d2m = Document2Markdown(None, model_path)

        try:
            pdf_bytes = d2m.doc_to_pdf(tmp_path)
        except Exception as e:
            logger.exception("doc_to_pdf failed")
            # fallback: if original file is already pdf-like or conversion failed, attempt to register original
            file_id = add_file_task(tmp_cache, file_name, file_bytes=file_bytes, upload_time=upload_time)
            return jsonify({
                "success": True,
                "file": {"file_id": file_id},
                "error_message": "conversion failed, original registered",
                "error_code": "conversion_failed_registered_original"
            }), 200

        # save pdf into pdf_root using the original name (preserve base name)
        os.makedirs(pdf_root, exist_ok=True)
        d2m.save_pdf_file(pdf_bytes, pdf_root)
        # Document2Markdown sets original_filename
        pdf_fname = f"{d2m.original_filename}.pdf"
        file_id = add_file_task(pdf_root, pdf_fname, file_bytes=pdf_bytes, upload_time=upload_time)

        return jsonify({
            "success": True,
            "file": {"file_id": file_id},
            "error_message": "",
            "error_code": ""
        }), 200
    finally:
        # cleanup tmp file
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


@bp.route('/file_upload_calendar', methods=['POST'])
def upload_calendar():
    '''
    通讯格式：
    输入：
    {
        "file_name": "calendar.pdf",   # 必须
        "file_bytes": "base64_encoded_content",  # 必须
        "upload_time": "2023-10-01T12:00:00Z",  # 可选
        "user_id": 7  # 可选，传入后会为该用户创建 syllabus owner 关联
    }

    输出：
    {
        "success": true | false,
        "file": {"file_id": 123},
        "syllabus": {"syllabus_id": 456},
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = None
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({
            "success": False,
            "file": None,
            "syllabus": None,
            "error_message": "invalid json",
            "error_code": "invalid_json"
        }), 400

    file_name = data.get('file_name')
    file_bytes_b64 = data.get('file_bytes')
    upload_time = data.get('upload_time')
    user_id = data.get('user_id')

    if not file_name or not file_bytes_b64:
        return jsonify({
            "success": False,
            "file": None,
            "syllabus": None,
            "error_message": "file_name and file_bytes are required",
            "error_code": "missing_fields"
        }), 400

    try:
        file_bytes = base64.b64decode(file_bytes_b64)
    except Exception:
        return jsonify({
            "success": False,
            "file": None,
            "syllabus": None,
            "error_message": "invalid base64 file_bytes",
            "error_code": "invalid_base64"
        }), 400

    # determine calendar save dir
    cal_root = os.path.abspath(constant.BasePath.CALENDAR_ROOT.value.lstrip('/'))
    os.makedirs(cal_root, exist_ok=True)
    file_path = os.path.join(cal_root, file_name)

    # delegate to syllabus_task.upload_calendar which will register the file and create a syllabus
    try:
        syllabus = syllabus_task.upload_calendar(
            file_path=file_path,
            file_name=file_name,
            file_bytes=file_bytes,
            upload_time=upload_time,
            user_id=user_id,
        )
        if syllabus is None:
            return jsonify({
                "success": False,
                "file": None,
                "syllabus": None,
                "error_message": "failed to create syllabus",
                "error_code": "create_failed"
            }), 500
        # syllabus object likely has syllabus_id and file_id
        return jsonify({
            "success": True,
            "file": {"file_id": getattr(syllabus, 'file_id', None)},
            "syllabus": {"syllabus_id": getattr(syllabus, 'syllabus_id', None)},
            "error_message": "",
            "error_code": ""
        }), 200
    except Exception as e:
        logger.exception("upload_calendar failed")
        return jsonify({
            "success": False,
            "file": None,
            "syllabus": None,
            "error_message": str(e),
            "error_code": "exception"
        }), 500


@bp.route('/file_list_graph_files', methods=['POST'])
def list_graph_files_api():
    data = request.get_json(silent=True) or {}
    graph_id_list = data.get('graph_id_list')

    if not isinstance(graph_id_list, list):
        return jsonify({
            "success": False,
            "files": [],
            "error_message": "missing graph_id_list",
            "error_code": "missing_fields"
        }), 400

    try:
        files = list_all_files_brief_info(graph_id_list=graph_id_list, syllabus_id_list=None, material_id_list=None)
        return jsonify({
            "success": True,
            "files": files,
            "error_message": "",
            "error_code": ""
        }), 200
    except Exception as e:
        logger.exception("list_graph_files_api failed")
        return jsonify({
            "success": False,
            "files": [],
            "error_message": str(e),
            "error_code": "exception"
        }), 500


@bp.route('/file_list_syllabus_files', methods=['POST'])
def list_syllabus_files_api():
    data = request.get_json(silent=True) or {}
    syllabus_id_list = data.get('syllabus_id_list')

    if not isinstance(syllabus_id_list, list):
        return jsonify({
            "success": False,
            "files": [],
            "error_message": "missing syllabus_id_list",
            "error_code": "missing_fields"
        }), 400

    try:
        files = list_all_files_brief_info(graph_id_list=None, syllabus_id_list=syllabus_id_list, material_id_list=None)
        return jsonify({
            "success": True,
            "files": files,
            "error_message": "",
            "error_code": ""
        }), 200
    except Exception as e:
        logger.exception("list_syllabus_files_api failed")
        return jsonify({
            "success": False,
            "files": [],
            "error_message": str(e),
            "error_code": "exception"
        }), 500
@bp.route('/file_detail', methods=['POST'])
def get_file_detail_api():
    data = request.get_json(silent=True) or {}
    file_id = data.get('file_id')

    if file_id is None or str(file_id).strip() == '':
        return jsonify({
            "success": False,
            "file": None,
            "error_message": "missing file_id",
            "error_code": "missing_fields"
        }), 400

    try:
        file = get_file_detail_info(int(file_id))
        if not file:
            return jsonify({
                "success": False,
                "file": None,
                "error_message": "not found",
                "error_code": "not_found"
            }), 404

        return jsonify({
            "success": True,
            "file": file,
            "error_message": "",
            "error_code": ""
        }), 200
    except Exception as e:
        logger.exception("get_file_detail_api failed")
        return jsonify({
            "success": False,
            "file": None,
            "error_message": str(e),
            "error_code": "exception"
        }), 500


@bp.route('/file_download', methods=['GET'])
def download_file_api():
    file_id = request.args.get('file_id')

    if file_id is None or str(file_id).strip() == '':
        return jsonify({
            "success": False,
            "error_message": "missing file_id",
            "error_code": "missing_fields",
        }), 400

    try:
        download_info = get_file_download_info(file_id)
        if not download_info:
            return jsonify({
                "success": False,
                "error_message": "not found",
                "error_code": "not_found",
            }), 404

        return send_file(
            download_info['path'],
            as_attachment=True,
            download_name=download_info['filename'],
            mimetype=download_info['mimetype'],
            conditional=True,
        )
    except Exception as e:
        logger.exception("download_file_api failed")
        return jsonify({
            "success": False,
            "error_message": str(e),
            "error_code": "exception",
        }), 500
