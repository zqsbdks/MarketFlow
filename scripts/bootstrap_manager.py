"""为全新数据库创建第一个可登录的店长账号。"""

import asyncio
import sys
from io import TextIOWrapper

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.crud.employees import create_employee
from app.models.employee import Employee
from app.models.enums import EmployeeRole

INITIAL_MANAGER_NAME = "初始店长"

# Windows 可能使用 cp932 等控制台编码，显式切换为 UTF-8 以正常显示中文结果。
if isinstance(sys.stdout, TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


async def bootstrap_manager() -> None:
    """数据库没有店长时创建一个初始店长，已有店长时保持不变。"""

    initial_manager_password = settings.initial_manager_password
    if initial_manager_password is None:
        raise RuntimeError("请先在 .env 中配置 APP_INITIAL_MANAGER_PASSWORD")

    async with async_session_factory() as db:
        statement = select(Employee).where(Employee.role == EmployeeRole.STORE_MANAGER)
        manager = await db.scalar(statement)

        if manager is not None:
            print(f"店长账号已存在：{manager.employee_no}")
            return

        manager = await create_employee(
            name=INITIAL_MANAGER_NAME,
            role=EmployeeRole.STORE_MANAGER,
            department_id=None,
            password_hash=hash_password(initial_manager_password),
            db=db,
        )
        await db.commit()

        print("初始店长创建成功")
        print(f"员工编号：{manager.employee_no}")
        print(f"临时密码：{initial_manager_password}")
        print("首次登录后必须修改密码")


async def main() -> None:
    """执行初始化并释放数据库连接池。"""

    try:
        await bootstrap_manager()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
