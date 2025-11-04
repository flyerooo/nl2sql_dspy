"""
DSPy LLM 配置
==============

配置 Azure OpenAI 作为 DSPy 的语言模型。
"""

import dspy
import os


def configure_azure_openai():
    """
    配置 Azure OpenAI 作为 DSPy 的默认 LLM。
    
    必须设置环境变量 AZURE_OPENAI_API_KEY。
    """
    # Azure OpenAI 配置
    azure_endpoint = "https://liby-ai-terminal-v1-koreacentral-gpt-5-01.openai.azure.com"
    deployment_name = "gpt-5"
    api_version = "2024-06-01"
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError(
            "AZURE_OPENAI_API_KEY environment variable is required.\n"
            "Please set it before running: export AZURE_OPENAI_API_KEY='your-key'"
        )
    
    # 创建 Azure OpenAI LM
    lm = dspy.LM(
        model=f"azure/{deployment_name}",
        api_base=azure_endpoint,
        api_version=api_version,
        api_key=api_key,
        temperature=1.0,
        max_tokens=16000
    )
    
    # 配置为默认 LM
    dspy.configure(lm=lm)
    
    return lm


def get_configured_lm():
    """
    获取已配置的 LM，如果没有则进行配置。
    
    Returns:
        配置好的 DSPy LM 对象
    """
    if dspy.settings.lm is None:
        return configure_azure_openai()
    return dspy.settings.lm


if __name__ == "__main__":
    # 测试配置
    print("配置 Azure OpenAI LLM...")
    lm = configure_azure_openai()
    print(f"✓ LLM 配置完成: {lm}")
    
    # 简单测试
    try:
        print("\n测试 LLM 调用...")
        response = lm("Hello, how are you?")
        print(f"✓ LLM 响应: {response}")
    except Exception as e:
        print(f"✗ LLM 调用失败: {e}")
