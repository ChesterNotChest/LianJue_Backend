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

    def call_text_model(self, prompt: str, query: str, stream=False) -> str | None | Any:
        """调用文本模型处理纯文字对话"""
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": query}]
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
        config = self.MODEL_CONFIGS["visual"]
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
            return f"多模态模型调用失败: {str(e)}"

    def call_embed_model(self, texts: List[str]) -> List[List[float]]:
        """调用向量模型生成文本嵌入向量（支持批量输入，返回向量列表的列表）"""
        config = self.MODEL_CONFIGS["embed"]
        try:
            response = litellm.embedding(
                model=config["model_name"],
                input=texts,  # 传入文本列表，实现批量生成
                api_base=config["api_base"],
                api_key=config["api_key"]
            )
            # 提取每个文本对应的嵌入向量，保持与输入列表的顺序一致
            return [item['embedding'] for item in response.data]
        except Exception as e:
            raise Exception(f"向量模型调用失败: {str(e)}")


# --------------------------
# 2. 模型配置管理（统一存储所有模型参数）
# --------------------------
MODEL_CONFIGS = {
    # 文本模型（仅处理文字对话）
    "text": {
        "model_name": "openai/qwen-max",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
    },
    # 多模态模型（处理文本+图片）
    "visual": {
        "model_name": "openai/qwen-vl-plus",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
    },
    # 向量模型（生成文本嵌入向量）
    "embed": {
        "model_name": "openai/text-embedding-v2",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
    }
}

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
