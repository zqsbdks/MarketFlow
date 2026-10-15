"""员工 AI 密钥的加密保存、读取和删除。"""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import ai_credentials as data_access
from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.ai_provider_credential import AiProviderCredential
from app.models.enums import EmployeeRole
from app.schemas.ai_chat_requests import AiProviderName


def _cipher() -> Fernet:
    """加密主密钥只从服务端环境变量读取，绝不发送给前端。"""

    if not settings.ai_key_encryption_key:
        raise HTTPException(status_code=503, detail="AI 密钥加密功能尚未配置")
    try:
        return Fernet(settings.ai_key_encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("APP_AI_KEY_ENCRYPTION_KEY 不是有效的 Fernet 密钥") from exc


async def _get_credential(
    employee_id: int, provider: AiProviderName, db: AsyncSession
) -> AiProviderCredential | None:
    return await data_access.get_employee_credential(
        db=db, employee_id=employee_id, provider=provider
    )


async def has_ai_credential(
    employee_id: int,
    provider: AiProviderName,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> bool:
    """只向前端返回是否已配置，不返回密文或明文。"""

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
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    return await _get_credential(employee_id, provider, db) is not None


async def save_ai_credential(
    employee_id: int,
    provider: AiProviderName,
    api_key: str,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> None:
    """用独立环境密钥加密员工的供应商 Key。"""
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
            selected_store_id = None
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and (raw_store_id != "all"):
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    encrypted = _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")
    credential = await _get_credential(employee_id, provider, db)
    if credential is None:
        credential = AiProviderCredential(
            employee_id=employee_id, provider=provider, encrypted_key=encrypted
        )
        data_access.add_employee_credential(db=db, credential=credential)
    else:
        credential.encrypted_key = encrypted
    await db.flush()
    await create_operation_audit_log(
        employee_id=employee_id,
        module="ai_assistant",
        action="save_credential",
        target_type="ai_provider_credential",
        target_id=credential.id,
        before_data=None,
        after_data={"provider": provider, "configured": True},
        reason="员工配置自己的AI模型密钥",
        db=db,
    )
    await db.commit()


async def read_ai_credential(
    employee_id: int,
    provider: AiProviderName,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> str:
    """仅供后端调用模型时解密；解密失败不泄露密文。"""

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
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    credential = await _get_credential(employee_id, provider, db)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置该模型的 API Key"
        )
    try:
        return _cipher().decrypt(credential.encrypted_key.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(status_code=503, detail="AI Key 无法解密，请联系管理员") from exc


async def delete_ai_credential(
    employee_id: int,
    provider: AiProviderName,
    db: AsyncSession,
    *,
    http_request: Request | None = None,
) -> None:
    """删除本人密钥。"""

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
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    credential = await _get_credential(employee_id, provider, db)
    if credential is not None:
        credential_id = credential.id
        await data_access.delete_employee_credential(db=db, credential=credential)
        await create_operation_audit_log(
            employee_id=employee_id,
            module="ai_assistant",
            action="delete_credential",
            target_type="ai_provider_credential",
            target_id=credential_id,
            before_data={"provider": provider, "configured": True},
            after_data={"configured": False},
            reason="员工删除自己的AI模型密钥",
            db=db,
        )
        await db.commit()


__all__ = ["delete_ai_credential", "has_ai_credential", "read_ai_credential", "save_ai_credential"]
