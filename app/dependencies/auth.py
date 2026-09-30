"""从 Authorization 请求头解析并验证 JWT Bearer 令牌。

基础模板只验证签名、算法、过期时间和 ``sub`` 声明，不绑定具体 User 表。
业务项目可以基于返回载荷继续加载用户、检查权限或执行令牌撤销校验。
"""

from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.auth import get_employee_by_id
from app.dependencies.db import get_db

# auto_error=False 让缺少请求头的情况进入自定义逻辑，返回项目约定的中文提示。
bearer_scheme = HTTPBearer(auto_error=False)


# region 验证JWT载荷
async def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """校验 Bearer 令牌并返回 JWT 载荷。

    Args:
        credentials: FastAPI 从 Authorization 请求头解析出的 Bearer 凭据。

    Raises:
        HTTPException: 请求未携带令牌，或令牌无效、已过期时返回 401。

    Returns:
        dict[str, Any]: 已验证的 JWT 载荷，其中保证包含非空 ``sub``。
    """

    if not credentials:
        # 明确返回 Bearer 认证挑战头，客户端可以据此触发重新登录。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization 请求头",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # PyJWT 会同时校验签名、允许的算法以及标准 exp 过期声明。
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # 对外隐藏签名错误等内部细节，避免泄露安全实现信息。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌或令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not isinstance(payload.get("sub"), str) or not payload["sub"].strip():
        # sub 是调用方身份的稳定标识，业务层通常用它查询用户或服务账号。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# endregion


# region 获取当前员工ID
async def get_current_employee_id(
    token_payload: dict[str, Any] = Depends(get_current_token_payload),
) -> int:
    """从已验证的 JWT 载荷中取得数字类型的员工 ID。"""

    try:
        return int(token_payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌中的员工标识无效",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# endregion


# region 获取已验证状态的当前员工ID
async def get_verified_current_employee_id(
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> int:
    """在解析JWT后，继续检查员工账号的最新可用状态。

    缓存命中时路由函数本身不会再次执行，但 FastAPI 仍会先解析依赖。缓存接口使用
    本依赖，可以避免已停用或尚未修改初始密码的员工读取已有缓存。
    """

    employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )
    if employee.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    return employee.id


# endregion

__all__ = [
    "get_current_employee_id",
    "get_current_token_payload",
    "get_verified_current_employee_id",
]
