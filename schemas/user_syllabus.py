from extensions import db


class UserSyllabus(db.Model):
    __tablename__ = 'user_syllabus'

    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), primary_key=True, nullable=False)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), primary_key=True, nullable=False)
    syllabus_permission = db.Column(db.String(50), nullable=False, default='user')
    personal_syllabus_path = db.Column(db.String(255), nullable=True, unique=True, default=None)

    def __repr__(self):
        return f"<UserSyllabus user_id={self.user_id} syllabus_id={self.syllabus_id}>"
