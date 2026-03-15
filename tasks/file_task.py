
from datetime import datetime

from repositories.file_repo import create_file

#########
# 上传文件
def add_file(file_path, upload_time: str = None): # TODO 这里之后准备从api那边接收内容
    # 这里可以添加文件上传的逻辑，比如保存文件到服务器或云存储
    # 然后创建一个新的任务来处理这个文件
    if not upload_time:
        upload_time = datetime.utcnow().isoformat()
    file = create_file(file_path, upload_time=upload_time)
    return file.file_id
#########