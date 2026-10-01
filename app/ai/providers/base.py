"""模型供应商统一接口及公共 HTTP 请求工具。"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas.ai_chat_requests import AiChatMessageRequest

PROVIDER_TIMEOUT_SECONDS = 40


@dataclass
class ProviderToolCall:
    """模型要求后端执行的一次结构化工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderTurn:
    """把不同供应商的回答统一为文字、工具调用和续传数据。"""

    text: str
    tool_calls: list[ProviderToolCall]
    continuation: Any


@dataclass
class ProviderError(Exception):
    """模型上游返回的安全错误信息。"""

    status_code: int | None
    message: str


def _read_http_error(error: HTTPError) -> str:
    """读取供应商错误正文；API Key 只在请求头中，不会进入返回信息。"""

    try:
        response_data = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "模型服务返回了无法解析的错误"

    error_data = response_data.get("error")
    if isinstance(error_data, dict) and isinstance(error_data.get("message"), str):
        return error_data["message"]
    if isinstance(error_data, str):
        return error_data
    return "模型服务请求失败"


def _post_json_sync(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """使用固定供应商地址发送 JSON，避免接受用户自定义 URL 造成 SSRF。"""

    request = Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict):
                raise ProviderError(None, "模型服务返回格式异常")
            return result
    except HTTPError as error:
        raise ProviderError(error.code, _read_http_error(error)) from error
    except URLError as error:
        raise ProviderError(None, "无法连接模型服务，请检查网络后重试") from error
    except (TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProviderError(None, "模型服务响应超时或格式异常") from error


async def post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """在线程池中执行标准库同步请求，避免阻塞 FastAPI 事件循环。"""

    return await asyncio.to_thread(_post_json_sync, url, headers, payload)


class AiProviderAdapter(ABC):
    """所有模型供应商必须实现的两阶段工具调用接口。"""

    name: str
    default_model: str

    @abstractmethod
    async def request_initial(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str,
        messages: list[AiChatMessageRequest],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """发送用户对话和工具定义，取得文字或工具调用。"""

    @abstractmethod
    async def request_followup(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str,
        messages: list[AiChatMessageRequest],
        tools: list[dict[str, Any]],
        initial_turn: ProviderTurn,
        tool_results: list[tuple[ProviderToolCall, dict[str, Any]]],
    ) -> ProviderTurn:
        """把后端工具执行结果交回模型，生成最终自然语言回答。"""


__all__ = [
    "AiProviderAdapter",
    "ProviderError",
    "ProviderToolCall",
    "ProviderTurn",
    "post_json",
]
