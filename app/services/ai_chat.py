"""Gemini AI 助手请求代理与响应解析业务逻辑。"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from fastapi import status as http_status

from app.schemas.ai_chat_requests import AiChatRequest
from app.schemas.ai_chat_responses import AiChatResponse

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TIMEOUT_SECONDS = 40

# 助手只负责解释和操作指引，不声称读取了没有传入的实时数据库数据。
MARKETFLOW_SYSTEM_INSTRUCTION = """你是 MarketFlow 超市经营管理系统中的基础帮助助手。
请使用简体中文，回答要准确、简洁、适合正在学习该项目的新手。
你可以解释以下功能：员工与权限、供应商、供应商商品目录、进货单、库存批次、
商品库存、销售收银、折扣规则、营业分析和操作审计。
如果用户询问当前实时营业额、具体库存数或某条数据库记录，必须明确说明你没有直接
访问数据库的能力，并引导用户前往对应页面查询。不要声称已经执行修改、删除、进货、
销售或其他业务操作。不要索取密码、JWT、数据库连接信息或 API Key。"""


@dataclass
class GeminiUpstreamError(Exception):
    """保存 Gemini 上游请求失败的类型和安全错误信息。"""

    status_code: int | None
    message: str


# region 构建与发送Gemini请求
def _build_gemini_payload(request: AiChatRequest) -> dict[str, Any]:
    """把项目请求模型转换为 Gemini generateContent 请求体。"""

    return {
        "systemInstruction": {
            "parts": [{"text": MARKETFLOW_SYSTEM_INSTRUCTION}],
        },
        "contents": [
            {
                "role": message.role,
                "parts": [{"text": message.content}],
            }
            for message in request.messages
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 800,
        },
    }


def _read_upstream_error(error: HTTPError) -> str:
    """从 Gemini 错误响应中读取可展示信息，不包含用户 API Key。"""

    try:
        response_data = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "模型服务返回了无法解析的错误"

    error_data = response_data.get("error")
    if isinstance(error_data, dict) and isinstance(error_data.get("message"), str):
        return error_data["message"]
    return "模型服务请求失败"


def _request_gemini(api_key: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """使用标准库同步调用 Gemini；由异步 Service 放入工作线程执行。"""

    url = f"{GEMINI_API_BASE_URL}/{model}:generateContent"
    upstream_request = Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(upstream_request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise GeminiUpstreamError(error.code, _read_upstream_error(error)) from error
    except URLError as error:
        raise GeminiUpstreamError(None, "无法连接 Gemini API，请检查网络后重试") from error
    except (TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GeminiUpstreamError(None, "Gemini API 响应超时或格式异常") from error


def _extract_response_text(response_data: dict[str, Any]) -> str:
    """合并 Gemini 第一个候选答案中的全部文本片段。"""

    candidates = response_data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiUpstreamError(None, "模型没有生成回答，内容可能被安全策略拦截")

    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        raise GeminiUpstreamError(None, "模型返回格式异常")
    content = first_candidate.get("content")
    if not isinstance(content, dict):
        raise GeminiUpstreamError(None, "模型没有返回文本内容")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise GeminiUpstreamError(None, "模型没有返回文本内容")

    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text = part["text"].strip()
            if text:
                texts.append(text)
    if not texts:
        raise GeminiUpstreamError(None, "模型没有返回可显示的回答")
    return "\n".join(texts)


# endregion


# region AI聊天业务入口
async def ai_chat_service(
    request: AiChatRequest,
    api_key: str,
) -> AiChatResponse:
    """校验会话顺序、调用 Gemini，并转换为项目响应模型。"""

    if request.messages[-1].role != "user":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="聊天记录最后一条必须是用户消息",
        )

    payload = _build_gemini_payload(request)
    try:
        response_data = await asyncio.to_thread(
            _request_gemini,
            api_key,
            request.model,
            payload,
        )
        answer = _extract_response_text(response_data)
    except GeminiUpstreamError as error:
        if error.status_code in {400, 401, 403}:
            status_code = http_status.HTTP_400_BAD_REQUEST
            detail = "Gemini API Key 无效、无权限或模型名称不可用"
        elif error.status_code == 429:
            status_code = http_status.HTTP_429_TOO_MANY_REQUESTS
            detail = "Gemini API 请求过于频繁或额度不足，请稍后重试"
        else:
            status_code = http_status.HTTP_502_BAD_GATEWAY
            detail = error.message
        raise HTTPException(status_code=status_code, detail=detail) from error

    return AiChatResponse(message=answer, model=request.model)


# endregion

__all__ = ["ai_chat_service"]
