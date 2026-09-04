"""为全新数据库创建第一个可登录的店长账号。"""

import asyncio

from sqlalchemy import select

from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.crud.employees import create_employee
from app.models.employee import Employee
from app.models.enums import EmployeeRole

INITIAL_MANAGER_NAME = "初始店长"
INITIAL_MANAGER_PASSWORD = "123456"


async def bootstrap_manager() -> None:
    """数据库没有店长时创建一个初始店长，已有店长时保持不变。"""

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
            password_hash=hash_password(INITIAL_MANAGER_PASSWORD),
            db=db,
        )
        await db.commit()

        print("初始店长创建成功")
        print(f"员工编号：{manager.employee_no}")
        print(f"临时密码：{INITIAL_MANAGER_PASSWORD}")
        print("首次登录后必须修改密码")


async def main() -> None:
    """执行初始化并释放数据库连接池。"""

    try:
        await bootstrap_manager()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
