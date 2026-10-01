"""多模型AI助手与MarketFlow工具调用编排业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import ProviderError, get_provider_adapter
from app.ai.tools import (
    WRITE_TOOL_NAMES,
    execute_marketflow_tool,
    select_marketflow_tools,
)
from app.crud.operation_audit_logs import create_operation_audit_log
from app.schemas.ai_chat_requests import AiChatRequest
from app.schemas.ai_chat_responses import AiChatResponse, AiPendingActionResponse

MAX_TOOL_CALLS_PER_TURN = 4

MARKETFLOW_SYSTEM_INSTRUCTION = """你是 MarketFlow 超市经营管理系统的业务助手。
请使用简体中文，回答准确、简洁。系统已经向你提供受控工具：需要实时库存、批次、
进货或营业数据时必须调用查询工具，严禁凭空编造数字。用户要求修改数据时，只能调用
名称以 prepare_ 开头的工具生成待确认操作；工具结果出现 requires_confirmation 时，
明确告诉用户必须点击界面的“确认执行”，绝不能声称修改已经完成。
你可以协助查询或处理商品、库存批次、供应商、供应商商品、进货、销售、员工和折扣规则；
具体操作是否允许，最终由后端按当前员工的账号、角色、所属部门和业务状态重新验证。
不要索取密码、JWT、数据库连接信息或API Key。不要生成SQL。工具返回错误时如实说明，
不要绕过员工权限、部门权限、有效期、行锁或审计规则。"""


def _map_provider_error(error: ProviderError) -> HTTPException:
    """把不同供应商错误转换为统一且不会泄露API Key的HTTP错误。"""

    normalized_message = error.message.casefold()
    if error.status_code in {401, 403} or "api key" in normalized_message:
        return HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="API Key无效或没有调用该模型的权限",
        )
    if error.status_code == 404:
        return HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="模型名称不存在或当前API版本不支持该模型",
        )
    if error.status_code == 400:
        return HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="模型请求格式不兼容，请检查模型名称或工具定义",
        )
    if error.status_code == 429:
        return HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="模型API请求过于频繁或额度不足，请稍后重试",
        )
    return HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail=error.message,
    )


# region AI聊天与工具编排
async def ai_chat_service(
    *,
    request: AiChatRequest,
    api_key: str,
    current_employee_id: int,
    db: AsyncSession,
) -> AiChatResponse:
    """调用所选模型，执行受控只读工具，并把修改请求保存为待确认操作。"""

    if request.messages[-1].role != "user":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="聊天记录最后一条必须是用户消息",
        )

    provider = get_provider_adapter(request.provider)
    model = request.model or provider.default_model
    selected_tools = select_marketflow_tools(request.messages[-1].content)
    try:
        current_turn = await provider.request_initial(
            api_key=api_key,
            model=model,
            system_instruction=MARKETFLOW_SYSTEM_INSTRUCTION,
            messages=request.messages,
            tools=selected_tools,
        )

        # 没有工具调用时直接返回模型文字；此时不会访问业务数据库。
        if not current_turn.tool_calls:
            if not current_turn.text:
                raise ProviderError(None, "模型没有返回可显示的回答")
            return AiChatResponse(
                message=current_turn.text,
                provider=request.provider,
                model=model,
            )

        pending_actions: list[AiPendingActionResponse] = []
        write_tool_used = False
        total_tool_calls = 0

        # 允许模型先查询真实ID，再根据查询结果生成确认卡片；总调用数受严格上限控制。
        while current_turn.tool_calls:
            total_tool_calls += len(current_turn.tool_calls)
            if total_tool_calls > MAX_TOOL_CALLS_PER_TURN:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="模型单次请求的工具数量过多，请缩小问题范围",
                )

            tool_results = []
            new_pending_actions: list[AiPendingActionResponse] = []
            for tool_call in current_turn.tool_calls:
                if tool_call.name in WRITE_TOOL_NAMES:
                    if write_tool_used:
                        tool_results.append(
                            (
                                tool_call,
                                {"ok": False, "error": "一次对话只能提出一个数据修改操作"},
                            )
                        )
                        continue
                    write_tool_used = True

                execution = await execute_marketflow_tool(
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                    employee_id=current_employee_id,
                    provider=request.provider,
                    db=db,
                )
                tool_results.append((tool_call, execution.data))
                if execution.pending_action is not None:
                    pending_action = AiPendingActionResponse.model_validate(
                        execution.pending_action
                    )
                    pending_actions.append(pending_action)
                    new_pending_actions.append(pending_action)

            # 待确认记录要在继续请求模型前落库；即使模型总结失败也可继续确认或取消。
            for pending_action in new_pending_actions:
                await create_operation_audit_log(
                    employee_id=current_employee_id,
                    module="ai_assistant",
                    action="prepare_action",
                    target_type="ai_pending_action",
                    target_id=pending_action.id,
                    before_data=None,
                    after_data={
                        "action_type": pending_action.action_type,
                        "arguments": pending_action.arguments,
                        "status": pending_action.status,
                    },
                    reason="AI助手生成待确认操作",
                    db=db,
                )
            if new_pending_actions:
                await db.commit()

            current_turn = await provider.request_followup(
                api_key=api_key,
                model=model,
                system_instruction=MARKETFLOW_SYSTEM_INSTRUCTION,
                messages=request.messages,
                tools=selected_tools,
                initial_turn=current_turn,
                tool_results=tool_results,
            )

        message = current_turn.text or "工具已经执行，但模型没有生成文字说明。"
        return AiChatResponse(
            message=message,
            provider=request.provider,
            model=model,
            pending_actions=pending_actions,
        )
    except ProviderError as error:
        raise _map_provider_error(error) from error


# endregion

__all__ = ["ai_chat_service"]
