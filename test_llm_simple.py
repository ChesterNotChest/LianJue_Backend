#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的LLM连接测试 - 不需要Flask上下文
"""
import sys
import os
from pathlib import Path

# Set stdout encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add repo to path
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))

# Set Flask app context manually
os.environ['FLASK_ENV'] = 'testing'

def test_llm_connection():
    """直接测试LLM连接，不需要Flask上下文"""
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic import BaseModel
    from config import MODEL_CONFIGS
    
    print("\n=== 测试: 直接LLM连接 ===")
    
    try:
        # 构建模型
        text_config = MODEL_CONFIGS.get('text') or {}
        model_name = text_config.get('model_name')
        api_base = text_config.get('api_base')
        api_key = text_config.get('api_key')
        
        print(f"模型配置:")
        print(f"  - 模型名: {model_name}")
        print(f"  - API Base: {api_base}")
        print(f"  - API密钥已配置: {bool(api_key)}")
        
        provider = OpenAIProvider(base_url=api_base, api_key=api_key)
        model = OpenAIModel(model_name, provider=provider)
        
        print(f"\n[PASS] 模型创建成功")
        
        # 创建一个简单的Agent
        class SimpleResult(BaseModel):
            answer: str
        
        agent = Agent(
            model=model,
            output_type=SimpleResult,
            system_prompt="你是一个简单的助手。用简短的句子回答问题。",
        )
        
        print(f"[PASS] Agent创建成功")
        
        # 测试简单请求
        print(f"\n发送测试请求到LLM...")
        result = agent.run_sync("1+1等于多少？")
        
        print(f"[PASS] LLM响应成功!")
        print(f"  返回类型: {type(result)}")
        print(f"  回答: {result.output.answer}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("LLM 直接连接测试")
    print("=" * 60)
    
    success = test_llm_connection()
    
    print("\n" + "=" * 60)
    if success:
        print("LLM已成功接入！可以正常调用。")
    else:
        print("LLM连接失败，请检查配置。")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
