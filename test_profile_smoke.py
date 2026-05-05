#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小化 smoke test - 验证工具链走通并返回 profile

运行环境：需要Flask应用上下文
"""
import sys
import json
from pathlib import Path

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add repo to path
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))

# 创建Flask应用和上下文
from app import create_app

app = create_app()

def test_learning_profile_smoke():
    """最小化smoke test - 验证工具链完整走通"""
    from tasks.learning_profile_task import build_learning_profile
    from repositories.user_repo import get_user_by_id
    
    print("\n" + "=" * 70)
    print("学习画像 - 工具链完整性验证 (Smoke Test)")
    print("=" * 70)
    
    with app.app_context():
        try:
            # 测试参数
            user_id = 1
            dialogue_texts = ['我想学习Python编程', '能帮我讲解一下数据结构吗']
            learning_goal = '掌握Python基础和数据结构'
            learning_records = [
                {'timestamp': 1700000000, 'event_type': 'view', 'material_id': 'mat_001', 'duration': 600},
                {'timestamp': 1700000100, 'event_type': 'view', 'material_id': 'mat_002', 'duration': 300},
            ]
            answer_records = [
                {'timestamp': 1700000200, 'question_id': 'q_001', 'answer': '递归是一种编程技术', 'score': 0.8},
                {'timestamp': 1700000300, 'question_id': 'q_002', 'answer': '数组和列表的区别在于...', 'score': 0.7},
            ]
            resource_usage = [
                {'material_id': 'mat_001', 'resource_type': 'video', 'viewed': True},
                {'material_id': 'mat_002', 'resource_type': 'document', 'viewed': True},
            ]
            
            print(f"\n[准备] 输入参数:")
            print(f"  user_id: {user_id}")
            print(f"  dialogue_texts: {len(dialogue_texts)} 条")
            print(f"  learning_goal: {learning_goal}")
            print(f"  learning_records: {len(learning_records)} 条")
            print(f"  answer_records: {len(answer_records)} 条")
            print(f"  resource_usage: {len(resource_usage)} 条")
            
            # 验证用户存在
            user = get_user_by_id(user_id)
            if not user:
                print(f"\n[WARN] 用户 {user_id} 不存在，测试将跳过数据库依赖")
                # 创建mock用户对象
                class MockUser:
                    user_id = 1
                    user_name = "测试用户"
                    email = "test@example.com"
                user = MockUser()
            else:
                print(f"[OK] 用户已存在: {user.user_name}")
            
            # 调用工具链
            print(f"\n[执行] 调用 build_learning_profile()...")
            profile = build_learning_profile(
                user_id=user_id,
                dialogue_text=dialogue_texts,
                learning_goal=learning_goal,
                learning_records=learning_records,
                answer_records=answer_records,
                resource_usage=resource_usage,
            )
            
            # 验证结果
            if profile is None:
                print(f"\n[FAIL] 返回 None，工具链未完成")
                return False
            
            if not isinstance(profile, dict):
                print(f"\n[FAIL] 返回类型不对: {type(profile)}")
                return False
            
            # 检查关键字段
            required_keys = [
                'user_id', 'knowledge_mastery', 'concept_gaps', 
                'learning_style', 'confidence'
            ]
            missing_keys = [k for k in required_keys if k not in profile]
            
            if missing_keys:
                print(f"\n[FAIL] 缺少关键字段: {missing_keys}")
                return False
            
            print(f"\n[PASS] 工具链完整走通！")
            print(f"\n[结果] 学习画像摘要:")
            print(f"  - 用户ID: {profile.get('user_id')}")
            print(f"  - 知识掌握总分: {profile.get('knowledge_mastery', {}).get('overall_score')}")
            print(f"  - 学习风格: {profile.get('learning_style')}")
            print(f"  - 学习信心度: {profile.get('confidence')}")
            print(f"  - 概念缺陷数: {len(profile.get('concept_gaps', []))}")
            print(f"  - 输出字段总数: {len(profile)}")
            
            # 显示部分原始数据
            print(f"\n[详情] 画像数据（节选）:")
            print(f"  - 学习目标: {profile.get('learning_goal')}")
            print(f"  - 自报难度: {profile.get('self_reported_difficulty')}")
            print(f"  - 情绪状态: {profile.get('emotion_state')}")
            print(f"  - 掌握周数: {len(profile.get('knowledge_mastery', {}).get('mastered_weeks', []))}")
            print(f"  - 薄弱周数: {len(profile.get('knowledge_mastery', {}).get('weak_weeks', []))}")
            
            return True
            
        except Exception as e:
            print(f"\n[FAIL] 异常: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == '__main__':
    try:
        success = test_learning_profile_smoke()
        
        print("\n" + "=" * 70)
        if success:
            print("✓ 验证通过: 工具链完整走通，成功返回 profile")
        else:
            print("✗ 验证失败: 工具链未完整")
        print("=" * 70 + "\n")
        
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n致命错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
