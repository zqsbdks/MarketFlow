"""Google Gemini 模型供应商适配器。"""

from typing import Any

from app.ai.providers.base import (
    AiProviderAdapter,
    ProviderError,
    ProviderToolCall,
    ProviderTurn,
    post_json,
)
from app.schemas.ai_chat_requests import AiChatMessageRequest

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AiProviderAdapter):
    """把统一聊天与工具格式转换成 Gemini generateContent 格式。"""

    name = "gemini"
    default_model = "gemini-3.5-flash-lite"

    def _build_contents(self, messages: list[AiChatMessageRequest]) -> list[dict[str, Any]]:
        """Gemini 使用 model 角色，因此项目历史消息可以直接映射。"""

        return [
            {"role": message.role, "parts": [{"text": message.content}]} for message in messages
        ]

    def _parse_turn(self, response_data: dict[str, Any]) -> ProviderTurn:
        """提取 Gemini 第一个候选答案中的文字和函数调用。"""

        candidates = response_data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderError(None, "模型没有生成回答，内容可能被安全策略拦截")
        candidate = candidates[0]
        if not isinstance(candidate, dict) or not isinstance(candidate.get("content"), dict):
            raise ProviderError(None, "Gemini 返回格式异常")

        content = candidate["content"]
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise ProviderError(None, "Gemini 没有返回有效内容")

        texts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            function_call = part.get("functionCall")
            if isinstance(function_call, dict) and isinstance(function_call.get("name"), str):
                arguments = function_call.get("args")
                if not isinstance(arguments, dict):
                    arguments = {}
                tool_calls.append(
                    ProviderToolCall(
                        id=f"gemini-{index}",
                        name=function_call["name"],
                        arguments=arguments,
                    )
                )
        return ProviderTurn(text="\n".join(texts), tool_calls=tool_calls, continuation=content)

    async def request_initial(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str,
        messages: list[AiChatMessageRequest],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """发送第一阶段 Gemini 请求。"""

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": self._build_contents(messages),
            "tools": [{"functionDeclarations": tools}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000},
        }
        response = await post_json(
            f"{GEMINI_API_BASE_URL}/{model}:generateContent",
            {"x-goog-api-key": api_key},
            payload,
        )
        turn = self._parse_turn(response)
        # 保存本轮模型内容，后续连续工具调用时需要把完整对话链一并回传。
        turn.continuation = [turn.continuation]
        return turn

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
        """向 Gemini 回传 MarketFlow 工具结果并取得最终回答。"""

        function_parts = []
        for tool_call, result in tool_results:
            function_parts.append(
                {
                    "functionResponse": {
                        "name": tool_call.name,
                        "response": {"result": result},
                    }
                }
            )
        contents = self._build_contents(messages)
        previous_contents = initial_turn.continuation
        if isinstance(previous_contents, list):
            contents.extend(previous_contents)
        else:
            contents.append(previous_contents)
        function_response = {"role": "user", "parts": function_parts}
        contents.append(function_response)
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "tools": [{"functionDeclarations": tools}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000},
        }
        response = await post_json(
            f"{GEMINI_API_BASE_URL}/{model}:generateContent",
            {"x-goog-api-key": api_key},
            payload,
        )
        turn = self._parse_turn(response)
        # continuation只保存原始用户消息之后的增量内容，避免下一轮重复用户历史。
        previous_list = (
            previous_contents if isinstance(previous_contents, list) else [previous_contents]
        )
        turn.continuation = [*previous_list, function_response, turn.continuation]
        return turn


__all__ = ["GeminiProvider"]
