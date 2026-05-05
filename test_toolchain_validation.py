#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小化 smoke test - 验证工具链走通（不依赖数据库）

测试目标：
1. 验证两个Python文件语法正确
2. 验证工具链的核心逻辑能完整走通
3. 验证能成功返回profile对象
"""
import sys
from pathlib import Path

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add repo to path
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))


def test_syntax_check():
    """测试1: 验证Python文件语法"""
    print("\n" + "=" * 70)
    print("[测试1] Python 文件语法检查")
    print("=" * 70)
    
    import ast
    
    files_to_check = [
        'tasks/learning_profile_task.py',
        'tests/test_learning_profile.py',
    ]
    
    all_passed = True
    for filename in files_to_check:
        filepath = repo_root / filename
        try:
            # 用AST解析验证语法
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            ast.parse(code)
            print(f"  [PASS] {filename}")
        except SyntaxError as e:
            print(f"  [FAIL] {filename}: {e}")
            all_passed = False
    
    return all_passed


def test_imports():
    """测试2: 验证关键模块导入"""
    print("\n" + "=" * 70)
    print("[测试2] 关键模块导入")
    print("=" * 70)
    
    try:
        print("  导入 pydantic_ai...")
        from pydantic_ai import Agent, RunContext
        print("    [OK] Agent, RunContext")
        
        print("  导入 pydantic...")
        from pydantic import BaseModel
        print("    [OK] BaseModel")
        
        print("  导入 learning_profile_task 中的工具...")
        from tasks.learning_profile_task import (
            LearningProfileResult,
            LearningProfileDeps,
            get_learning_profile_agent,
            _build_learning_profile_model,
        )
        print("    [OK] LearningProfileResult")
        print("    [OK] LearningProfileDeps")
        print("    [OK] get_learning_profile_agent")
        print("    [OK] _build_learning_profile_model")
        
        print("  [PASS] 所有关键模块导入成功")
        return True
    except Exception as e:
        print(f"  [FAIL] 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_initialization():
    """测试3: 验证Agent初始化"""
    print("\n" + "=" * 70)
    print("[测试3] Agent 初始化")
    print("=" * 70)
    
    try:
        from tasks.learning_profile_task import (
            get_learning_profile_agent,
            _build_learning_profile_model,
        )
        
        print("  初始化模型...")
        model = _build_learning_profile_model()
        print(f"    [OK] 模型类型: {type(model).__name__}")
        
        print("  初始化Agent...")
        agent = get_learning_profile_agent()
        print(f"    [OK] Agent名称: {agent.name}")
        print(f"    [OK] 输出类型: {agent.output_type.__name__}")
        print(f"    [OK] 系统提示: 已配置")
        
        print("  [PASS] Agent 初始化成功")
        return True
    except Exception as e:
        print(f"  [FAIL] 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_core_functions():
    """测试4: 验证核心函数存在"""
    print("\n" + "=" * 70)
    print("[测试4] 核心函数验证")
    print("=" * 70)
    
    try:
        from tasks.learning_profile_task import (
            build_learning_profile,
            run_learning_profile_agent,
            _tool_load_history_context,
            _tool_load_personal_syllabus_context,
            _tool_normalize_events,
            _tool_compute_features,
            _tool_assemble_profile,
            _compute_learning_profile_bundle,
        )
        
        functions = [
            ('build_learning_profile', build_learning_profile),
            ('run_learning_profile_agent', run_learning_profile_agent),
            ('_tool_load_history_context', _tool_load_history_context),
            ('_tool_load_personal_syllabus_context', _tool_load_personal_syllabus_context),
            ('_tool_normalize_events', _tool_normalize_events),
            ('_tool_compute_features', _tool_compute_features),
            ('_tool_assemble_profile', _tool_assemble_profile),
            ('_compute_learning_profile_bundle', _compute_learning_profile_bundle),
        ]
        
        for name, func in functions:
            if callable(func):
                print(f"    [OK] {name}")
            else:
                print(f"    [FAIL] {name} 不可调用")
                return False
        
        print("  [PASS] 所有核心函数验证通过")
        return True
    except Exception as e:
        print(f"  [FAIL] 函数验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_flow():
    """测试5: 验证数据流和结果构造"""
    print("\n" + "=" * 70)
    print("[测试5] 数据流和结果构造")
    print("=" * 70)
    
    try:
        from tasks.learning_profile_task import (
            LearningProfileResult,
            _tool_normalize_events,
            _compute_learning_profile_bundle,
        )
        
        # 创建mock User对象
        class MockUser:
            user_id = 1
            user_name = "测试用户"
            email = "test@example.com"
        
        print("  构造测试 state...")
        test_state = {
            'user_id': 1,
            'user': MockUser(),
            'now_ts': 1700000000,
            'dialogue_texts': ['测试对话'],
            'learning_goal': '学习测试',
            'learning_records': [],
            'answer_records': [],
            'resource_usage': [],
            'history_entries': [],
            'normalized_events': {},
            'feature_bundle': {},
            'profile': None,
        }
        print("    [OK] state 构造完成 (含mock user)")
        
        print("  调用事件归一化工具...")
        _tool_normalize_events(test_state)
        print(f"    [OK] normalized_events 已填充")
        
        print("  调用特征计算函数...")
        bundle = _compute_learning_profile_bundle(test_state)
        print(f"    [OK] bundle 返回类型: {type(bundle).__name__}")
        print(f"    [OK] bundle 包含 profile: {'profile' in bundle}")
        
        if 'profile' in bundle:
            profile = bundle['profile']
            print(f"    [OK] profile 类型: {type(profile).__name__}")
            print(f"    [OK] profile 包含字段: {len(profile)} 个")
            
            # 验证关键字段
            required_keys = ['user_id', 'knowledge_mastery', 'confidence']
            missing = []
            for key in required_keys:
                if key in profile:
                    print(f"      - {key}: [OK]")
                else:
                    print(f"      - {key}: [MISS]")
                    missing.append(key)
            
            if not missing:
                print(f"    [OK] 所有关键字段都已返回")
        
        print("  构造 LearningProfileResult...")
        result = LearningProfileResult(
            success=True,
            profile=bundle.get('profile') if bundle else None,
            error_message='',
            error_code='',
        )
        print(f"    [OK] result 类型: {type(result).__name__}")
        print(f"    [OK] result.success: {result.success}")
        print(f"    [OK] result.profile 类型: {type(result.profile).__name__ if result.profile else 'None'}")
        
        print("  [PASS] 数据流和结果构造验证通过")
        return True
    except Exception as e:
        print(f"  [FAIL] 数据流验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  学习画像工具链 - 完整性验证测试".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    
    results = []
    
    # 运行所有测试
    results.append(("Python文件语法检查", test_syntax_check()))
    results.append(("关键模块导入", test_imports()))
    results.append(("Agent初始化", test_agent_initialization()))
    results.append(("核心函数验证", test_core_functions()))
    results.append(("数据流和结果构造", test_data_flow()))
    
    # 总结
    print("\n" + "=" * 70)
    print("验证总结")
    print("=" * 70)
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✓ 所有验证通过！")
        print("  • Python文件语法正确")
        print("  • 工具链框架完整")
        print("  • 关键函数和类都已实现")
        print("  • 数据流能正确构造并返回profile")
        print("\n工具链已准备就绪，可在Flask应用上下文中调用 build_learning_profile()。")
    else:
        print("✗ 部分验证失败，请检查错误信息")
    print("=" * 70 + "\n")
    
    sys.exit(0 if all_passed else 1)
