"""验证异步 MySQL 驱动，并提供按需启用的真实连接测试。"""

import os

import pytest
from sqlalchemy import func, select, text

from app.core.database import async_engine, async_session_factory
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail


def test_engine_uses_async_mysql_driver() -> None:
    """模板必须使用 aiomysql，避免在异步路由中调用同步数据库驱动。"""

    assert async_engine.url.drivername == "mysql+aiomysql"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_TESTS") != "1",
    reason="set RUN_MYSQL_TESTS=1 to use the configured MySQL database",
)
async def test_mysql_connection() -> None:
    """检查 MySQL 连通性，并确认每名员工都有一条详情记录。"""

    # 环境变量开关防止普通单元测试意外依赖外部数据库。
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        employee_count = await session.scalar(select(func.count(Employee.id)))
        detail_count = await session.scalar(select(func.count(EmployeeDetail.employee_id)))

    # scalar_one 同时验证查询有且只有一个结果。
    assert result.scalar_one() == 1
    assert detail_count == employee_count
