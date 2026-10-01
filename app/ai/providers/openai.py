"""OpenAI 模型供应商适配器。"""

import json
from typing import Any

from app.ai.providers.base import (
    AiProviderAdapter,
    ProviderError,
    ProviderToolCall,
    ProviderTurn,
    post_json,
)
from app.schemas.ai_chat_requests import AiChatMessageRequest

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class OpenAiProvider(AiProviderAdapter):
    """把统一格式转换成 OpenAI Chat Completions 工具调用格式。"""

    name = "openai"
    default_model = "gpt-5.6-luna"

    def _build_messages(
        self,
        system_instruction: str,
        messages: list[AiChatMessageRequest],
    ) -> list[dict[str, Any]]:
        """把项目中的 model 角色转换为 OpenAI 使用的 assistant 角色。"""

        result: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for message in messages:
            role = "assistant" if message.role == "model" else "user"
            result.append({"role": role, "content": message.content})
        return result

    def _parse_turn(self, response_data: dict[str, Any]) -> ProviderTurn:
        """解析 OpenAI 第一条 choice 中的文字和工具调用。"""

        choices = response_data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(None, "OpenAI 没有生成回答")
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ProviderError(None, "OpenAI 返回格式异常")
        message = choice["message"]
        content = message.get("content")
        text = content.strip() if isinstance(content, str) else ""

        parsed_calls: list[ProviderToolCall] = []
        raw_calls = message.get("tool_calls")
        if isinstance(raw_calls, list):
            for raw_call in raw_calls:
                if not isinstance(raw_call, dict):
                    continue
                function = raw_call.get("function")
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    continue
                arguments: dict[str, Any] = {}
                raw_arguments = function.get("arguments")
                if isinstance(raw_arguments, str):
                    try:
                        loaded_arguments = json.loads(raw_arguments)
                        if isinstance(loaded_arguments, dict):
                            arguments = loaded_arguments
                    except json.JSONDecodeError:
                        arguments = {}
                parsed_calls.append(
                    ProviderToolCall(
                        id=str(raw_call.get("id", f"openai-{len(parsed_calls)}")),
                        name=function["name"],
                        arguments=arguments,
                    )
                )
        return ProviderTurn(text=text, tool_calls=parsed_calls, continuation=message)

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": tool} for tool in tools]

    async def request_initial(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str,
        messages: list[AiChatMessageRequest],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """发送第一阶段 OpenAI 请求。"""

        payload = {
            "model": model,
            "messages": self._build_messages(system_instruction, messages),
            "tools": self._tools(tools),
            "tool_choice": "auto",
        }
        response = await post_json(
            OPENAI_CHAT_COMPLETIONS_URL,
            {"Authorization": f"Bearer {api_key}"},
            payload,
        )
        turn = self._parse_turn(response)
        # 保存本轮assistant消息，供后续多轮工具调用继续使用。
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
        """向 OpenAI 回传工具结果并取得最终回答。"""

        api_messages = self._build_messages(system_instruction, messages)
        previous_messages = initial_turn.continuation
        if isinstance(previous_messages, list):
            api_messages.extend(previous_messages)
        else:
            api_messages.append(previous_messages)
        tool_messages: list[dict[str, Any]] = []
        for tool_call, result in tool_results:
            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
            tool_messages.append(tool_message)
            api_messages.append(tool_message)
        payload = {
            "model": model,
            "messages": api_messages,
            "tools": self._tools(tools),
            "tool_choice": "auto",
        }
        response = await post_json(
            OPENAI_CHAT_COMPLETIONS_URL,
            {"Authorization": f"Bearer {api_key}"},
            payload,
        )
        turn = self._parse_turn(response)
        previous_list = (
            previous_messages if isinstance(previous_messages, list) else [previous_messages]
        )
        turn.continuation = [*previous_list, *tool_messages, turn.continuation]
        return turn


__all__ = ["OpenAiProvider"]
