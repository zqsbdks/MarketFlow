"""AI 聊天请求校验、Gemini 参数组装与错误转换测试。"""

from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.services.ai_chat as ai_chat_module
from app.schemas.ai_chat_requests import AiChatMessageRequest, AiChatRequest
from app.services.ai_chat import GeminiUpstreamError, ai_chat_service

# region 请求模型与参数组装测试


def test_ai_chat_request_rejects_unsafe_model_name() -> None:
    """模型名只能包含安全字符，避免用户通过路径字符改变上游请求地址。"""

    with pytest.raises(ValidationError):
        AiChatRequest(
            model="../unsafe-model",
            messages=[AiChatMessageRequest(role="user", content="你好")],
        )


def test_build_gemini_payload_keeps_roles_and_contents() -> None:
    """发送给 Gemini 的内容应保留用户和模型的多轮对话顺序。"""

    request = AiChatRequest(
        messages=[
            AiChatMessageRequest(role="user", content="进货单是什么？"),
            AiChatMessageRequest(role="model", content="它用于记录进货。"),
            AiChatMessageRequest(role="user", content="批次呢？"),
        ],
    )

    payload = ai_chat_module._build_gemini_payload(request)

    assert payload["contents"][0]["role"] == "user"
    assert payload["contents"][1]["role"] == "model"
    assert payload["contents"][2]["parts"][0]["text"] == "批次呢？"
    assert "systemInstruction" in payload


# endregion


# region AI 聊天服务测试


async def test_ai_chat_service_returns_gemini_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """上游正常响应时，服务层应提取回答正文并返回模型名。"""

    def fake_request(api_key: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert api_key == "test-api-key"
        assert model == "gemini-3.5-flash-lite"
        assert payload["contents"][0]["role"] == "user"
        return {
            "candidates": [
                {"content": {"parts": [{"text": "库存批次用于记录每批商品的数量和到期日。"}]}}
            ]
        }

    monkeypatch.setattr(ai_chat_module, "_request_gemini", fake_request)
    request = AiChatRequest(
        messages=[AiChatMessageRequest(role="user", content="库存批次有什么作用？")]
    )

    result = await ai_chat_service(request=request, api_key="test-api-key")

    assert result.message == "库存批次用于记录每批商品的数量和到期日。"
    assert result.model == "gemini-3.5-flash-lite"


async def test_ai_chat_service_requires_last_message_from_user() -> None:
    """最后一条为模型消息时不应继续请求，避免产生没有新问题的调用。"""

    request = AiChatRequest(messages=[AiChatMessageRequest(role="model", content="已有回答")])

    with pytest.raises(HTTPException) as error_info:
        await ai_chat_service(request=request, api_key="test-api-key")

    assert error_info.value.status_code == 400


async def test_ai_chat_service_hides_upstream_auth_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API Key 无效时只返回安全提示，不把上游详细错误或密钥暴露给前端。"""

    def fake_request(api_key: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise GeminiUpstreamError(403, f"invalid credential: {api_key}")

    monkeypatch.setattr(ai_chat_module, "_request_gemini", fake_request)
    request = AiChatRequest(messages=[AiChatMessageRequest(role="user", content="你好")])

    with pytest.raises(HTTPException) as error_info:
        await ai_chat_service(request=request, api_key="secret-test-key")

    assert error_info.value.status_code == 400
    assert "secret-test-key" not in str(error_info.value.detail)


# endregion
