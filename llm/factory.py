from llm.anthropic_client import AnthropicClient
from llm.openai_client import OpenAIClient


def create_client(provider: str, api_key: str):
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key)
    if provider == "openai":
        return OpenAIClient(api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider}")
