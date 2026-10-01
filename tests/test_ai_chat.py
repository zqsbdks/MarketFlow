"""多供应商AI聊天、工具调用编排和安全限制测试。"""

from copy import deepcopy
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.ai.providers.gemini as gemini_module
import app.services.ai_actions as ai_actions_module
import app.services.ai_chat as ai_chat_module
from app.ai.action_registry import validate_business_action
from app.ai.providers.base import ProviderError, ProviderToolCall, ProviderTurn
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai import OpenAiProvider
from app.ai.tools import MARKETFLOW_TOOL_DEFINITIONS, ToolExecutionResult, select_marketflow_tools
from app.core.business_time import business_now
from app.models.ai_pending_action import AiPendingAction
from app.schemas.ai_chat_requests import AiChatMessageRequest, AiChatRequest
from app.services.ai_actions import confirm_ai_action_service
from app.services.ai_chat import ai_chat_service


# region 请求模型和供应商解析测试
def test_ai_chat_request_rejects_unknown_provider_and_unsafe_model() -> None:
    """只允许白名单供应商和安全模型ID，前端不能传入任意服务地址。"""

    with pytest.raises(ValidationError):
        AiChatRequest(
            provider="unknown",  # type: ignore[arg-type]
            messages=[AiChatMessageRequest(role="user", content="你好")],
        )
    with pytest.raises(ValidationError):
        AiChatRequest(
            provider="gemini",
            model="../unsafe-model",
            messages=[AiChatMessageRequest(role="user", content="你好")],
        )


def test_gemini_provider_extracts_text_and_function_call() -> None:
    """Gemini响应应转换为统一文字和工具调用格式。"""

    turn = GeminiProvider()._parse_turn(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "我来查询。"},
                            {
                                "functionCall": {
                                    "name": "search_products",
                                    "args": {"keyword": "レタス"},
                                }
                            },
                        ],
                    }
                }
            ]
        }
    )

    assert turn.text == "我来查询。"
    assert turn.tool_calls[0].name == "search_products"
    assert turn.tool_calls[0].arguments == {"keyword": "レタス"}


def test_openai_provider_extracts_tool_arguments() -> None:
    """OpenAI字符串形式的函数参数应解析成统一字典。"""

    turn = OpenAiProvider()._parse_turn(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "get_inventory_batch",
                                    "arguments": '{"id": 3}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )

    assert turn.tool_calls[0].id == "call-1"
    assert turn.tool_calls[0].arguments == {"id": 3}


def test_business_action_registry_validates_discount_and_rejects_missing_fields() -> None:
    """统一业务工具应按操作类型校验参数，而不是把模型生成的任意字典直接落库。"""

    values = validate_business_action(
        "add_discount_products",
        {"discount_rule_id": 5, "product_ids": [10, 11]},
    )
    assert values == {"discount_rule_id": 5, "product_ids": [10, 11]}

    with pytest.raises(ValidationError):
        validate_business_action("add_discount_products", {"discount_rule_id": 5})


def test_marketflow_tools_are_selected_by_business_topic() -> None:
    """每次只向模型发送当前业务相关工具，且不再出现Gemini不兼容的任意对象结构。"""

    tools = select_marketflow_tools("请创建一个晚间折扣并添加商品")
    tool_names = {tool["name"] for tool in tools}

    assert "prepare_create_discount_rule" in tool_names
    assert "prepare_add_discount_products" in tool_names
    assert len(tools) <= 20
    assert all("additionalProperties" not in str(tool["parameters"]) for tool in tools)


# endregion


# region Gemini出站请求兼容测试
async def test_gemini_sends_json_schema_in_correct_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """拦截真实适配器的两次出站请求，防止JSON Schema再次误放进parameters。"""

    original_tools = deepcopy(MARKETFLOW_TOOL_DEFINITIONS)
    post = AsyncMock(
        return_value={"candidates": [{"content": {"role": "model", "parts": [{"text": "你好"}]}}]}
    )
    monkeypatch.setattr(gemini_module, "post_json", post)
    provider = GeminiProvider()
    messages = [AiChatMessageRequest(role="user", content="你好")]
    initial = await provider.request_initial(
        api_key="test-key",
        model="test-model",
        system_instruction="test",
        messages=messages,
        tools=MARKETFLOW_TOOL_DEFINITIONS,
    )
    await provider.request_followup(
        api_key="test-key",
        model="test-model",
        system_instruction="test",
        messages=messages,
        tools=MARKETFLOW_TOOL_DEFINITIONS,
        initial_turn=initial,
        tool_results=[(ProviderToolCall("call-1", "search_products", {}), {"ok": True})],
    )
    assert post.await_count == 2
    for call in post.await_args_list:
        declarations = call.args[2]["tools"][0]["functionDeclarations"]
        assert len(declarations) == len(original_tools)
        for declaration, original in zip(declarations, original_tools, strict=True):
            assert "parameters" not in declaration
            assert declaration["parametersJsonSchema"] == original["parameters"]
    # 公共定义继续供其他供应商使用，不能被Gemini适配器原地修改。
    assert MARKETFLOW_TOOL_DEFINITIONS == original_tools


# endregion


# region AI修改确认测试
def _pending_inventory_action(employee_id: int = 7) -> AiPendingAction:
    """构造不依赖真实数据库的待确认库存修改记录。"""

    return AiPendingAction(
        id=10,
        employee_id=employee_id,
        provider="gemini",
        action_type="update_inventory_batch_quantity",
        arguments={"batch_id": 3, "remaining_quantity": 8, "reason": "AI盘点建议"},
        summary="将批次B003的库存修改为8件",
        status="pending",
        expires_at=business_now() + timedelta(minutes=5),
        executed_at=None,
        failure_reason=None,
    )


async def test_confirm_ai_action_rejects_other_employee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """待确认操作只能由最初发起它的员工处理。"""

    action = _pending_inventory_action(employee_id=7)

    async def fake_get(**_kwargs: Any) -> AiPendingAction:
        return action

    monkeypatch.setattr(ai_actions_module, "get_ai_pending_action_by_id", fake_get)
    with pytest.raises(HTTPException) as error_info:
        await confirm_ai_action_service(action_id=10, employee_id=8, db=AsyncMock())

    assert error_info.value.status_code == 403
    assert action.status == "pending"


async def test_confirm_ai_action_executes_existing_inventory_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认后必须复用原库存Service，而不是让AI直接写数据库。"""

    action = _pending_inventory_action()

    async def fake_get(**_kwargs: Any) -> AiPendingAction:
        return action

    class FakeBatchResult:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"id": 3, "remaining_quantity": 8}

    update_service = AsyncMock(return_value=FakeBatchResult())
    monkeypatch.setattr(ai_actions_module, "get_ai_pending_action_by_id", fake_get)
    monkeypatch.setattr(
        ai_actions_module,
        "update_inventory_batch_quantity_service",
        update_service,
    )
    monkeypatch.setattr(
        ai_actions_module,
        "create_operation_audit_log",
        AsyncMock(),
    )
    db = AsyncMock()
    db.info = {}

    response = await confirm_ai_action_service(action_id=10, employee_id=7, db=db)

    assert response.action.status == "executed"
    assert response.result == {"id": 3, "remaining_quantity": 8}
    update_service.assert_awaited_once()
    assert db.commit.await_count == 1


async def test_confirm_ai_action_executes_discount_product_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """折扣商品修改也必须在确认后复用原有Service及其权限检查。"""

    action = AiPendingAction(
        id=11,
        employee_id=7,
        provider="gemini",
        action_type="add_discount_products",
        arguments={"discount_rule_id": 5, "product_ids": [10, 11]},
        summary="为折扣规则ID 5添加2个商品",
        status="pending",
        expires_at=business_now() + timedelta(minutes=5),
        executed_at=None,
        failure_reason=None,
    )

    async def fake_get(**_kwargs: Any) -> AiPendingAction:
        return action

    class FakeDiscountResult:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"discount_rule_id": 5, "added_count": 2}

    discount_service = AsyncMock(return_value=FakeDiscountResult())
    monkeypatch.setattr(ai_actions_module, "get_ai_pending_action_by_id", fake_get)
    monkeypatch.setattr(
        ai_actions_module,
        "add_discount_rule_products_service",
        discount_service,
    )
    monkeypatch.setattr(ai_actions_module, "create_operation_audit_log", AsyncMock())

    db = AsyncMock()
    db.info = {}
    response = await confirm_ai_action_service(
        action_id=11,
        employee_id=7,
        db=db,
    )

    assert response.action.status == "executed"
    assert response.result == {"discount_rule_id": 5, "added_count": 2}
    discount_service.assert_awaited_once()


# endregion


class FakeProvider:
    """测试用模型适配器，不发送外部网络请求。"""

    default_model = "fake-model"

    def __init__(self, initial: ProviderTurn, final: ProviderTurn | None = None) -> None:
        self.initial = initial
        self.final = final

    async def request_initial(self, **_kwargs: Any) -> ProviderTurn:
        return self.initial

    async def request_followup(self, **_kwargs: Any) -> ProviderTurn:
        assert self.final is not None
        return self.final


# region AI聊天编排测试
async def test_ai_chat_returns_direct_model_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型不调用工具时直接返回文字，并使用供应商默认模型。"""

    provider = FakeProvider(ProviderTurn("基础回答", [], {}))
    monkeypatch.setattr(ai_chat_module, "get_provider_adapter", lambda _provider: provider)
    request = AiChatRequest(
        provider="gemini",
        messages=[AiChatMessageRequest(role="user", content="系统有什么功能？")],
    )

    result = await ai_chat_service(
        request=request,
        api_key="test-api-key",
        current_employee_id=1,
        db=AsyncMock(),
    )

    assert result.message == "基础回答"
    assert result.model == "fake-model"
    assert result.pending_actions == []


async def test_ai_chat_executes_read_tool_and_returns_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """实时查询由后端白名单工具执行，结果再交给模型组织答案。"""

    initial = ProviderTurn(
        "",
        [ProviderToolCall("call-1", "search_products", {"keyword": "レタス"})],
        {},
    )
    provider = FakeProvider(initial, ProviderTurn("当前可售库存83件。", [], {}))
    monkeypatch.setattr(ai_chat_module, "get_provider_adapter", lambda _provider: provider)

    async def fake_execute(**kwargs: Any) -> ToolExecutionResult:
        assert kwargs["employee_id"] == 7
        assert kwargs["name"] == "search_products"
        return ToolExecutionResult(data={"ok": True, "saleable_stock_quantity": 83})

    monkeypatch.setattr(ai_chat_module, "execute_marketflow_tool", fake_execute)
    request = AiChatRequest(
        provider="openai",
        model="test-model",
        messages=[AiChatMessageRequest(role="user", content="レタス还有多少？")],
    )

    result = await ai_chat_service(
        request=request,
        api_key="test-api-key",
        current_employee_id=7,
        db=AsyncMock(),
    )

    assert result.message == "当前可售库存83件。"
    assert result.provider == "openai"


async def test_ai_chat_can_query_then_prepare_one_write_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次对话可以先查询真实ID，再生成一条待确认修改，但不会直接执行修改。"""

    initial = ProviderTurn(
        "",
        [ProviderToolCall("call-1", "list_discount_rules", {"keyword": "晚间"})],
        {},
    )

    class MultiStepProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__(initial)
            self.followup_count = 0

        async def request_followup(self, **_kwargs: Any) -> ProviderTurn:
            self.followup_count += 1
            if self.followup_count == 1:
                return ProviderTurn(
                    "",
                    [
                        ProviderToolCall(
                            "call-2",
                            "prepare_update_discount_status",
                            {
                                "discount_rule_id": 5,
                                "is_active": True,
                            },
                        )
                    ],
                    {},
                )
            return ProviderTurn("已生成开启折扣的确认操作。", [], {})

    provider = MultiStepProvider()
    monkeypatch.setattr(ai_chat_module, "get_provider_adapter", lambda _provider: provider)
    pending_action = AiPendingAction(
        id=12,
        employee_id=7,
        provider="gemini",
        action_type="update_discount_status",
        arguments={"discount_rule_id": 5, "is_active": True},
        summary="开启折扣规则ID 5",
        status="pending",
        expires_at=business_now() + timedelta(minutes=5),
        executed_at=None,
        failure_reason=None,
    )

    async def fake_execute(**kwargs: Any) -> ToolExecutionResult:
        if kwargs["name"] == "list_discount_rules":
            return ToolExecutionResult(data={"ok": True, "items": [{"id": 5}]})
        return ToolExecutionResult(
            data={"ok": True, "requires_confirmation": True},
            pending_action=pending_action,
        )

    monkeypatch.setattr(ai_chat_module, "execute_marketflow_tool", fake_execute)
    monkeypatch.setattr(ai_chat_module, "create_operation_audit_log", AsyncMock())
    request = AiChatRequest(
        messages=[AiChatMessageRequest(role="user", content="开启晚间折扣")],
    )

    result = await ai_chat_service(
        request=request,
        api_key="test-api-key",
        current_employee_id=7,
        db=AsyncMock(),
    )

    assert result.message == "已生成开启折扣的确认操作。"
    assert result.pending_actions[0].id == 12
    assert provider.followup_count == 2


async def test_ai_chat_rejects_model_history_ending_with_model() -> None:
    """没有新用户问题时不应产生额外模型费用。"""

    request = AiChatRequest(messages=[AiChatMessageRequest(role="model", content="已有回答")])
    with pytest.raises(HTTPException) as error_info:
        await ai_chat_service(
            request=request,
            api_key="test-api-key",
            current_employee_id=1,
            db=AsyncMock(),
        )
    assert error_info.value.status_code == 400


async def test_ai_chat_hides_provider_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """供应商鉴权失败时不向页面回传可能包含密钥的上游详情。"""

    class FailingProvider(FakeProvider):
        async def request_initial(self, **_kwargs: Any) -> ProviderTurn:
            raise ProviderError(403, "invalid secret-test-key")

    monkeypatch.setattr(
        ai_chat_module,
        "get_provider_adapter",
        lambda _provider: FailingProvider(ProviderTurn("", [], {})),
    )
    request = AiChatRequest(messages=[AiChatMessageRequest(role="user", content="你好")])

    with pytest.raises(HTTPException) as error_info:
        await ai_chat_service(
            request=request,
            api_key="secret-test-key",
            current_employee_id=1,
            db=AsyncMock(),
        )

    assert error_info.value.status_code == 400
    assert "secret-test-key" not in str(error_info.value.detail)


# endregion
