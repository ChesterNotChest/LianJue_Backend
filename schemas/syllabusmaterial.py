# [material_id, syllabus_id, week_index] , 3 个共同构成 syllabusmaterial 的唯一标识

from extensions import db

class SyllabusMaterial(db.Model):
    __tablename__ = 'syllabusmaterials'

    material_id = db.Column(db.Integer, db.ForeignKey('material.material_id'), primary_key=True)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), primary_key=True)
    week_index = db.Column(db.Integer, primary_key=True) # 最常被调的字段。
    ok_to_recommend = db.Column(db.Boolean, default=False) # 这个字段是为了后续推荐系统使用的，表示这个syllabus_id和week_index对应的material_id是否适合被推荐系统推荐。因为有些文件可能质量不高或者不适合被推荐系统推荐，所以需要这个字段来标记一下。
    # 但是一个记录只记录某个周次，例如，对于1-3周的记录就会有 3 个元组。
    # 一个material可以对应多个syllabus_id和week_index的组合，但每个组合只能对应一个material_id。
    # 一般的文件靠图谱的关系来关联教学进度 故这里不存那些东西。 material因为不会入库，所以需要这个表来关联syllabus。

    def __repr__(self):
        return f"<SyllabusMaterial material_id={self.material_id} syllabus_id={self.syllabus_id} week_index={self.week_index}>"