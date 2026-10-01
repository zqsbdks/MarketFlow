"""员工 AI 密钥的加密保存、读取和删除。"""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.ai_provider_credential import AiProviderCredential
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
    return await db.scalar(
        select(AiProviderCredential).where(
            AiProviderCredential.employee_id == employee_id,
            AiProviderCredential.provider == provider,
        )
    )


async def has_ai_credential(employee_id: int, provider: AiProviderName, db: AsyncSession) -> bool:
    """只向前端返回是否已配置，不返回密文或明文。"""

    return await _get_credential(employee_id, provider, db) is not None


async def save_ai_credential(
    employee_id: int, provider: AiProviderName, api_key: str, db: AsyncSession
) -> None:
    """用独立环境密钥加密员工的供应商 Key。"""

    encrypted = _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")
    credential = await _get_credential(employee_id, provider, db)
    if credential is None:
        credential = AiProviderCredential(
            employee_id=employee_id, provider=provider, encrypted_key=encrypted
        )
        db.add(credential)
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


async def read_ai_credential(employee_id: int, provider: AiProviderName, db: AsyncSession) -> str:
    """仅供后端调用模型时解密；解密失败不泄露密文。"""

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
    employee_id: int, provider: AiProviderName, db: AsyncSession
) -> None:
    """删除本人密钥。"""

    credential = await _get_credential(employee_id, provider, db)
    if credential is not None:
        credential_id = credential.id
        await db.delete(credential)
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
