"""模型供应商白名单与适配器选择。"""

from app.ai.providers.base import AiProviderAdapter
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai import OpenAiProvider
from app.schemas.ai_chat_requests import AiProviderName

_PROVIDERS: dict[str, AiProviderAdapter] = {
    "gemini": GeminiProvider(),
    "openai": OpenAiProvider(),
}


def get_provider_adapter(provider: AiProviderName) -> AiProviderAdapter:
    """只从固定白名单返回适配器，不接受前端传入任意 API 地址。"""

    return _PROVIDERS[provider]


__all__ = ["get_provider_adapter"]
