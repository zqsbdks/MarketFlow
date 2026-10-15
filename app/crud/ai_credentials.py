"""ai_credentials：数据库读写函数。"""

from sqlalchemy import select

from app.models.ai_provider_credential import AiProviderCredential


async def get_employee_credential(db, employee_id, provider):
    """执行_get_credential所需的数据库查询；权限由调用它的服务检查。"""
    return await db.scalar(
        select(AiProviderCredential).where(
            AiProviderCredential.employee_id == employee_id,
            AiProviderCredential.provider == provider,
        )
    )


def add_employee_credential(db, credential):
    """执行save_ai_credential所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(credential)


async def delete_employee_credential(db, credential):
    """执行delete_ai_credential所需的数据库删除；权限由调用它的服务检查。"""
    return await db.delete(credential)
