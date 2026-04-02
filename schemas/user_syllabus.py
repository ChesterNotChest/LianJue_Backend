from extensions import db

class UserSyllabus(db.Model):
    __tablename__ = 'user_syllabus'

    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id '), primary_key=True,  nullable=False)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), primary_key=True,  nullable=False)
    syllabus_permission = db.Column(db.String(50), nullable=False, default='read') # 这个字段表示用户对这个syllabus的权限，可以是 'read'（只读）或者 'write'（可编辑）。默认是 'read'。
    personal_syllabus_path = db.Column(db.String(255), nullable=True, unique=True, default=None) # 用户个性化教学进度文件路径，允许为空，且唯一（如果不为空的话）。这个路径是用户上传的个性化教学进度文件在服务器上的存储路径。

    def __repr__(self):
        return f"<UserSyllabus user_id={self.user_id} syllabus_id={self.syllabus_id}>"