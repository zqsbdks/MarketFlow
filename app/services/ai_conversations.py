"""ai_conversations：业务规则和响应组装。"""

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import ai_conversations as data_access
from app.crud.auth import get_employee_by_id
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
from app.schemas.base import ResponseModel
from app.services.ai_memory import conversation_list, owned_conversation


async def list_conversations_service(
    employee_id: int, db: AsyncSession, *, http_request: Request | None = None
):

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    conversations = await conversation_list(employee_id, db)
    data_value_values = []
    for data_value_item in conversations:
        data_value_values.append(
            {
                "id": data_value_item.id,
                "title": data_value_item.title,
                "provider": data_value_item.provider,
                "model": data_value_item.model,
                "store_id": data_value_item.store_id,
            }
        )
    data_value = data_value_values
    return ResponseModel(data=data_value)


async def get_conversation_service(
    conversation_id: int,
    before_id: int | None,
    employee_id: int,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
):

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    item = await owned_conversation(conversation_id, employee_id, db)
    messages = list(
        (await data_access.get_conversation_messages(db=db, before_id=before_id, item=item)).all()
    )
    messages.reverse()
    action_ids = []
    for message in messages:
        for action in message.actions or []:
            action_ids.append(action["id"])
    latest_actions = {}
    if action_ids:
        rows = (
            await data_access.get_message_actions(
                db=db, action_ids=action_ids, employee_id=employee_id
            )
        ).all()
        for action in rows:
            latest_actions[action.id] = action
    serialized = []
    for message in messages:
        actions = []
        for original in message.actions or []:
            current = latest_actions.get(original["id"])
            if current is not None:
                actions.append(
                    {
                        "id": current.id,
                        "action_type": current.action_type,
                        "summary": current.summary,
                        "arguments": current.arguments,
                        "status": current.status,
                        "expires_at": current.expires_at,
                        "executed_at": current.executed_at,
                        "failure_reason": current.failure_reason,
                    }
                )
        serialized.append(
            {"id": message.id, "role": message.role, "content": message.content, "actions": actions}
        )
    if len(messages) == 100:
        next_before_id_value = messages[0].id
    else:
        next_before_id_value = None
    return ResponseModel(
        data={
            "id": item.id,
            "title": item.title,
            "provider": item.provider,
            "model": item.model,
            "messages": serialized,
            "next_before_id": next_before_id_value,
        }
    )
