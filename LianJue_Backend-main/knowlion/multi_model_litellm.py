import litellm
import base64
import os
from typing import List, Dict, Any


class LitellmMultiModel:
    def __init__(self, model_configs: Dict):
        """
        初始化LitellmMultiModel类

        Args:
            model_configs (Dict): 模型配置字典，包含text、image、embed三种模型的配置
        """
        self.MODEL_CONFIGS = model_configs

    def call_text_model(self, prompt: str, query: str, stream=False, history: list | None = None) -> str | None | Any:
        """调用文本模型处理纯文字对话

        Args:
            prompt: system prompt
            query: user query
            stream: whether to stream
            history: optional list of past turns, each item is dict with keys 'timestamp','question','answer'
        """
        messages = [{"role": "system", "content": prompt}]
        # if history provided, append as assistant/user turns between system and current user query
        if history:
            for h in history:
                q = h.get('question') or h.get('q') or ''
                a = h.get('answer') or h.get('a') or ''
                if q:
                    messages.append({"role": "user", "content": q})
                if a:
                    messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": query})
        config = self.MODEL_CONFIGS["text"]
        try:
            response = litellm.completion(
                model=config["model_name"],
                messages=messages,
                api_base=config["api_base"],
                api_key=config["api_key"],
                stream=stream
            )
            if not stream:
                return response.choices[0].message.content
            else:
                for chunk in response:
                    # 提取当前 chunk 的内容（不同模型格式已被 LiteLLM 统一）
                    content = chunk.choices[0].delta.get("content", "")
                    if content:
                        print(content, end="", flush=True)  # 实时打印，不换行
        except Exception as e:
            return f"文本模型调用失败: {str(e)}"

    def call_image_model(self, prompt: str, image_path_or_bytes: str|bytes, stream=False) -> str:
        """调用多模态模型处理文本+图片任务"""
        # 【修复】配置键名从 "visual" 改为 "image"（与MODEL_CONFIGS定义一致）
        try:
            config = self.MODEL_CONFIGS["image"]
        except KeyError as e:
            available_keys = list(self.MODEL_CONFIGS.keys())
            raise KeyError(
                f"配置错误：找不到键 'image'。\n"
                f"可用的配置键: {available_keys}\n"
                f"请检查 MODEL_CONFIGS 是否包含 'image' 配置项。"
            ) from e
        
        image_b64 = None
        if isinstance(image_path_or_bytes, bytes):
            image_b64 = base64.b64encode(image_path_or_bytes).decode("utf-8")
        else:
            image_path = image_path_or_bytes
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片不存在: {image_path}")
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 构造多模态消息（符合OpenAI规范）
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ]

        try:
            response = litellm.completion(
                model=config["model_name"],
                messages=messages,
                api_base=config["api_base"],
                api_key=config["api_key"],
                stream=stream
            )
            return response.choices[0].message.content
        except Exception as e:
            # 增强错误信息：显示异常类型、详细信息和API配置
            import traceback
            error_details = (
                f"多模态模型调用失败\n"
                f"  异常类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  使用模型: {config.get('model_name', 'N/A')}\n"
                f"  API地址: {config.get('api_base', 'N/A')}\n"
                f"  堆栈追踪:\n{traceback.format_exc()}"
            )
            raise RuntimeError(error_details) from e

    def call_embed_model(self, texts: List[str]) -> List[List[float]]:
        """调用向量模型生成文本嵌入向量（支持批量输入，返回向量列表的列表）"""
        config = self.MODEL_CONFIGS["embed"]
        try:
            # Some embedding endpoints require specifying encoding_format (float or base64).
            encoding_format = config.get("encoding_format", "float")
            response = litellm.embedding(
                model=config["model_name"],
                input=texts,  # 传入文本列表，实现批量生成
                api_base=config["api_base"],
                api_key=config["api_key"],
                encoding_format=encoding_format
            )
            # 提取每个文本对应的嵌入向量，保持与输入列表的顺序一致
            return [item['embedding'] for item in response.data]
        except Exception as e:
            # 提供更有用的错误信息并提示可能的fix
            msg = str(e)
            if "encoding_format" in msg or "only support with" in msg:
                msg += " -- try setting MODEL_CONFIGS['embed']['encoding_format']='float' in config.json"
            raise Exception(f"向量模型调用失败: {msg}")


from config import MODEL_CONFIGS

# --------------------------
# 3. 测试示例
# --------------------------
if __name__ == "__main__":
    # 创建模型实例
    model_instance = LitellmMultiModel(MODEL_CONFIGS)

    # 测试文本模型
    print("文本模型结果:", model_instance.call_text_model("请介绍一下AI的发展历史",""))

    # 测试多模态模型（替换为你的图片路径）
    image_path = "/media/raini/414bbabe-867c-4aae-b65f-f3a024550774/AbutionDify/dify-1.7.0/api/storage/f4dc66ac-0e6e-4264-a4cb-83382b858aed/5264f4c9-48ba-4d1d-8dcd-baab8edd6357/79a489ae-b72e-4668-a54a-4dbc84aafae1/image_pages/2.png"  # 请替换为实际图片路径
    if os.path.exists(image_path):
        print("多模态模型结果:", model_instance.call_image_model(
            prompt="请描述这张图片的内容",
            image_path=image_path
        ))
    else:
        print(f"多模态模型测试跳过：图片文件不存在 - {image_path}")

    # 测试向量模型（批量输入）
    embed_texts = [
        "LiteLLM是一个统一的LLM调用工具",
        "Qwen-VL是支持图文理解的多模态模型",
        "文本嵌入可用于语义相似度计算"
    ]
    try:
        embeddings = model_instance.call_embed_model(embed_texts)
        # 打印每个文本的向量维度
        for i, emb in enumerate(embeddings):
            print(f"第{i + 1}个文本的向量: {emb}")
            print(f"第{i + 1}个文本的向量维度: {len(emb)}")
        # 打印完整向量列表（可选，长向量可能导致输出冗长）
        # print("向量列表:", embeddings)
    except Exception as e:
        print(e)
