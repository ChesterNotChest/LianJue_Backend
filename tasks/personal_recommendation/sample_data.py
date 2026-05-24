learning_tree = {
    'n1': {'id':'n1','title':'Intro to Data','difficulty':1,'prerequisites':[],'learning_time_est':2,'outcomes':['data_basic']},
    'n2': {'id':'n2','title':'Statistics 101','difficulty':2,'prerequisites':['n1'],'learning_time_est':4,'outcomes':['stats_basic']},
    'n3': {'id':'n3','title':'Python for Data','difficulty':2,'prerequisites':['n1'],'learning_time_est':5,'outcomes':['python_basic']},
    'n4': {'id':'n4','title':'Machine Learning Intro','difficulty':3,'prerequisites':['n2','n3'],'learning_time_est':8,'outcomes':['ml_basic']},
    'n5': {'id':'n5','title':'Deep Learning Primer','difficulty':4,'prerequisites':['n4'],'learning_time_est':10,'outcomes':['dl_basic']},
}

user_profile = {
    'knowledge_levels': {'data_basic':1, 'stats_basic':0, 'python_basic':0},
    'preferences': {'time_per_day':2,'preferred_formats':['video','text'],'risk_aversion':0.3},
    'constraints': {'deadline_days':30,'max_total_time':30}
}

goals = ['ml_basic','dl_basic']
