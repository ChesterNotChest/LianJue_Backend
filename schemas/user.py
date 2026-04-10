from extensions import db
class UserSyllabus(db.Model):
    __tablename__ = 'user_syllabus'

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(100), nullable=False, unique=True) # 存储用户的唯一标识符，要求唯一。
    password_hash = db.Column(db.String(255), nullable=False) # 存储用户密码的哈希值，使用安全的哈希算法（如 bcrypt）进行加密。
    email = db.Column(db.String(255), nullable=False, unique=True) # 存储用户的电子邮件地址，要求唯一。
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f"<UserSyllabus id={self.id} user_id={self.user_id} syllabus_id={self.syllabus_id}>"