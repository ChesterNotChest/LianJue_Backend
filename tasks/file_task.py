
from datetime import datetime
import os
import time
from typing import Union

from repositories.file_repo import create_file
from schemas.file import File

#########
# 上传文件
def add_file(save_path, file_name, file_bytes: Union[bytes, str] = None, upload_time: str = None):
    """
    
    """

    if not upload_time:
        upload_time = datetime.utcnow().isoformat()

    # build absolute path from save_path + file_name
    if save_path:
        abs_path = os.path.abspath(os.path.join(save_path, file_name))
    else:
        abs_path = os.path.abspath(file_name)

    if file_bytes is not None:
        # check for existing by DB path or filesystem
        db_exists = File.query.filter_by(path=abs_path).first() is not None
        fs_exists = os.path.exists(abs_path)
        if db_exists or fs_exists:
            base, ext = os.path.splitext(abs_path)
            suffix = f"_{int(time.time())}"
            abs_path = f"{base}{suffix}{ext}"

        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # write file bytes
        content = file_bytes if isinstance(file_bytes, (bytes, bytearray)) else str(file_bytes).encode('utf-8')
        with open(abs_path, 'wb') as wf:
            wf.write(content)

        file = create_file(abs_path, upload_time=upload_time)
        return file.file_id

    # no bytes provided — only register path in DB (create_file will return existing if any)
    file = create_file(abs_path, upload_time=upload_time)
    return file.file_id
#########

def list_all_files_brief_info(graph_id_list: list = None, syllabus_id_list: list = None, material_id_list: list = None):
    # 这里可以添加逻辑来查询数据库，获取所有文件的简要信息
    # 返回一个列表，每个元素是一个字典，包含文件的基本信息（取并集）
    pass

def get_file_detail_info(file_id: int):
    # 这里可以添加逻辑来查询数据库，获取指定文件的详细信息
    # 返回一个字典，包含文件的所有相关信息
    pass