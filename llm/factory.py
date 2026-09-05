import os

from llm.anthropic_client import AnthropicClient
from llm.openai_client import OpenAIClient
from llm.openrouter_client import OpenRouterClient


def create_client(provider: str, api_key: str):
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key)
    if provider == "openai":
        return OpenAIClient(api_key=api_key)
    if provider == "openrouter":
        model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        return OpenRouterClient(api_key=api_key, model=model)
    raise ValueError(f"Unknown LLM provider: {provider}")
