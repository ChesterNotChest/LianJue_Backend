# TODO 这里计划构建学生端的学习任务系统，负责管理学生的学习任务状态，提供方法供学生提问、获取学习资源等。

'''
模糊需求：
1. 学生提问的当前时间的时间戳，以匹配的形式来定位当前应该处在的进度。

2. 随后，将学生的提问做RAG检索，用检索结果来与教学大纲的描述性内容做语义比对，以锚定学生问的是第几周的内容。

3. 将1和2的内容，来确认学生学习进度与提问进度（已学，在学，未学）来完成不同程度指导，
再通过提问的质量来评判学生的掌握度是否薄弱。
如果薄弱，则标记薄弱
（每个学生有一个独立的拓展后的教学大纲
    （带有额外“competance”和"updated_at"的教学大纲json文件）
）。

如果提问质量比较一般，则标记为正常。如果询问特别有深度，则标记为掌握。
改完就把"updated_at"改成当前时间戳。一段时间后，自动降级一等。
'''


from time import time

'''
personal_sylllabus的*每个周*都多包括如下字段：
    competance: weak/normal/master/none
    competance_progress: -5 to +5, 每次提问根据质量提升或降低，达到+5则升级，-5则降级
    updated_at: 时间戳

'''


def ask_question(user_id: int, syllabus_id: int, question: str):
    '''
    1. 获取当前时间戳
    2. 获取personal_syllabus_path（从user_syllabus表中获取），并获取json文件内容，来定位应该在 第几周。
    3. 让大模型用 学生的提问 来与 教学大纲中每周的描述性内容 做语义比对，来判断学生提问对应的是 第几周。
    4. user_prompt: question + RAG结果 + 应处周次 + 实际周次 + 掌握度（如果有的话）
    5. system_prompt: 要求产出 {answer + document_names[...] + competance（掌握度） [{week_index: weak_far/weak/normal/master/master_far}, ...]}
        根据进度差异和掌握度来给出不同的指导建议。
        根据进度差异来给出不同的掌握度评判。
    6. documents用来和mysql的file表中的material_path模糊匹配，来找到对应的file_id。匹配不到的直接展示llm给的document名字
    7. 如果competance比json里的高/低 n 级，则向对应的competance_progress加 n / -n。(far表是距离normal有2级远，weak和master则距离normal有1级远）
        如果刚好处在同一个competance等级，对于normal自然+1，其余的(weak/master)则不变。
        如果初始json的competance是none，则设为llm给出的competance等级。（far的设为对应的非far等级）
    8. 更新personal_syllabus_json文件中的competance和updated_at字段。
    '''

    return 

def manage_forgetting_curve():
    '''
    定时任务，每天执行一次，来管理遗忘曲线。
    1. 遍历所有personal_syllabus_json文件，检查每个周次的updated_at字段。
    2. 如果updated_at距离当前时间超过一定阈值，则将competance降低一级，并将competance_progress重置为0。
    3. 更新personal_syllabus_json文件。
    '''
    return