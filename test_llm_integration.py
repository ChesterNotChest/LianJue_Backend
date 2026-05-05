#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试LLM是否真正被调用
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

from tasks.learning_profile_task import (
    run_learning_profile_agent,
    get_learning_profile_agent,
    LearningProfileDeps,
    _build_learning_profile_model,
)


def test_model_initialization():
    """测试模型是否能正确初始化"""
    print("\n=== 测试1: 模型初始化 ===")
    try:
        model = _build_learning_profile_model()
        print(f"[PASS] 模型初始化成功: {model}")
        print(f"       模型类型: {type(model)}")
        return True
    except Exception as e:
        print(f"[FAIL] 模型初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_initialization():
    """测试Agent是否能正确初始化"""
    print("\n=== 测试2: Agent初始化 ===")
    try:
        agent = get_learning_profile_agent()
        print(f"[PASS] Agent初始化成功: {agent}")
        print(f"       Agent名称: {agent.name}")
        print(f"       Agent模型: {agent.model}")
        return True
    except Exception as e:
        print(f"[FAIL] Agent初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_call_with_minimal_state():
    """测试Agent是否能调用LLM (最小化state)"""
    print("\n=== 测试3: LLM调用 (最小化state) ===")
    
    # 创建最小化的state
    minimal_state = {
        'user_id': 1,
        'syllabus_id': None,
        'user': None,
        'user_syllabuses': [],
        'profile_scope': [],
        'dialogue_texts': ['简单的对话测试'],
        'learning_goal': '学习基础概念',
        'learning_records': [],
        'answer_records': [],
        'resource_usage': [],
        'now_ts': 1714953600,
        'history_entries': [],
        'loaded_personal_syllabuses': [],
        'history_loaded': False,
        'personal_syllabus_loaded': False,
        'normalized_events': {},
        'feature_bundle': {},
        'profile': None,
        'tool_trace': [],
    }
    
    try:
        print(f"状态准备: user_id={minimal_state['user_id']}")
        print(f"开始调用agent.run_sync()...")
        
        result = run_learning_profile_agent(minimal_state)
        
        print(f"[PASS] LLM调用成功!")
        print(f"       返回类型: {type(result)}")
        result_dict = result.dict() if hasattr(result, 'dict') else result
        print(f"       返回结果摘要: success={result_dict.get('success')}, has_profile={result_dict.get('profile') is not None}")
        print(f"       state中的profile: {minimal_state.get('profile') is not None}")
        return True
    except Exception as e:
        print(f"[FAIL] LLM调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("LLM 集成验证测试")
    print("=" * 60)
    
    results = []
    
    # 测试1: 模型初始化
    results.append(("模型初始化", test_model_initialization()))
    
    # 测试2: Agent初始化
    results.append(("Agent初始化", test_agent_initialization()))
    
    # 测试3: LLM调用
    results.append(("LLM调用", test_llm_call_with_minimal_state()))
    
    print("\n" + "=" * 60)
    print("测试总结:")
    print("=" * 60)
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + ("所有测试通过！LLM已成功接入!" if all_passed else "部分测试失败，请检查配置"))
    
    sys.exit(0 if all_passed else 1)
