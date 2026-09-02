"""创建员工 Service、CRUD 与 API 响应测试。"""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.crud.employees import create_employee
from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.main import create_app
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.schemas.employees_requests import EmployeesCreateRequest
from app.schemas.employees_responses import EmployeesCreateResponse
from app.services.employees import DEFAULT_EMPLOYEE_PASSWORD, create_employee_service


def build_employee(
    *,
    employee_id: int,
    employee_no: str,
    role: EmployeeRole,
    is_active: bool = True,
    department_id: int | None = None,
    must_change_password: bool = True,
) -> Employee:
    """构造不依赖数据库的员工测试对象。"""

    return Employee(
        id=employee_id,
        employee_no=employee_no,
        name="测试员工",
        password_hash=hash_password("password"),
        role=role,
        department_id=department_id,
        is_active=is_active,
        must_change_password=must_change_password,
    )


async def override_db():
    """路由测试使用的占位数据库依赖。"""

    yield None


async def override_manager_id() -> int:
    """路由测试固定使用店长 ID。"""

    return 1


def test_create_employee_request_strips_and_validates_name() -> None:
    """员工姓名清除两端空格，并拒绝只包含空格的输入。"""

    request = EmployeesCreateRequest(
        name="  张三  ",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
    )
    assert request.name == "张三"

    with pytest.raises(ValidationError):
        EmployeesCreateRequest(
            name="   ",
            role=EmployeeRole.REGULAR_EMPLOYEE,
            department_id=1,
        )


def test_create_employee_returns_documented_response(monkeypatch) -> None:
    """创建成功时返回员工编号和默认临时密码。"""

    async def create(**_kwargs):
        return EmployeesCreateResponse(
            id=2,
            employee_no="E00002",
        )

    monkeypatch.setattr("app.routers.employees.create_employee_service", create)
    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_employee_id] = override_manager_id

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/employees/create",
            json={
                "name": "正式员工",
                "role": "正式员工",
                "department_id": 1,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "员工创建成功",
        "data": {
            "id": 2,
            "employee_no": "E00002",
            "temporary_password": "123456",
            "must_change_password": True,
        },
    }


async def test_create_employee_service_hashes_default_password(monkeypatch) -> None:
    """Service 使用默认密码哈希并返回首次修改标记。"""

    manager = build_employee(
        employee_id=1,
        employee_no="E00001",
        role=EmployeeRole.STORE_MANAGER,
        must_change_password=False,
    )
    department = Department(id=1, code="MEAT", name="精肉部", is_active=True)
    created_employee = build_employee(
        employee_id=2,
        employee_no="E00002",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
    )
    received: dict[str, object] = {}

    async def get_current(**_kwargs):
        return manager

    async def get_department(**_kwargs):
        return department

    async def create(**kwargs):
        received.update(kwargs)
        return created_employee

    monkeypatch.setattr("app.services.employees.get_employee_by_id", get_current)
    monkeypatch.setattr("app.services.employees.get_department_by_id", get_department)
    monkeypatch.setattr("app.services.employees.create_employee", create)
    session = AsyncMock(spec=AsyncSession)

    result = await create_employee_service(
        name="正式员工",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
        current_employee_id=manager.id,
        db=session,
    )

    assert verify_password(DEFAULT_EMPLOYEE_PASSWORD, str(received["password_hash"]))
    assert result.employee_no == "E00002"
    assert result.temporary_password == DEFAULT_EMPLOYEE_PASSWORD
    assert result.must_change_password is True
    session.commit.assert_awaited_once()


async def test_create_employee_service_rejects_non_manager(monkeypatch) -> None:
    """非店长不能创建员工。"""

    employee = build_employee(
        employee_id=2,
        employee_no="E00002",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
        must_change_password=False,
    )

    async def get_current(**_kwargs):
        return employee

    monkeypatch.setattr("app.services.employees.get_employee_by_id", get_current)
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await create_employee_service(
            name="新员工",
            role=EmployeeRole.CONTRACT_WORKER,
            department_id=1,
            current_employee_id=employee.id,
            db=session,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "只有店长可以创建员工"
    session.commit.assert_not_awaited()


async def test_create_employee_service_requires_department(monkeypatch) -> None:
    """正式员工和契约工必须选择部门。"""

    manager = build_employee(
        employee_id=1,
        employee_no="E00001",
        role=EmployeeRole.STORE_MANAGER,
        must_change_password=False,
    )

    async def get_current(**_kwargs):
        return manager

    monkeypatch.setattr("app.services.employees.get_employee_by_id", get_current)

    with pytest.raises(HTTPException) as exc_info:
        await create_employee_service(
            name="新员工",
            role=EmployeeRole.CONTRACT_WORKER,
            department_id=None,
            current_employee_id=manager.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "正式员工和契约工必须选择所属部门"


async def test_create_employee_service_requires_password_change(monkeypatch) -> None:
    """仍使用初始密码的店长不能进入员工管理业务。"""

    manager = build_employee(
        employee_id=1,
        employee_no="E00001",
        role=EmployeeRole.STORE_MANAGER,
        must_change_password=True,
    )

    async def get_current(**_kwargs):
        return manager

    monkeypatch.setattr("app.services.employees.get_employee_by_id", get_current)

    with pytest.raises(HTTPException) as exc_info:
        await create_employee_service(
            name="新员工",
            role=EmployeeRole.REGULAR_EMPLOYEE,
            department_id=1,
            current_employee_id=manager.id,
            db=AsyncMock(spec=AsyncSession),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "请先修改初始密码"


async def test_create_employee_crud_generates_employee_number() -> None:
    """CRUD 根据数据库自增 ID 生成 E00001 格式员工编号。"""

    session = AsyncMock(spec=AsyncSession)

    async def flush() -> None:
        employee = session.add.call_args.args[0]
        if employee.id is None:
            employee.id = 12

    session.flush.side_effect = flush
    password_hash = hash_password(DEFAULT_EMPLOYEE_PASSWORD)

    employee = await create_employee(
        name="正式员工",
        role=EmployeeRole.REGULAR_EMPLOYEE,
        department_id=1,
        password_hash=password_hash,
        db=session,
    )

    assert employee.id == 12
    assert employee.employee_no == "E00012"
    assert employee.password_hash == password_hash
    assert employee.must_change_password is True
    assert session.flush.await_count == 2
    session.commit.assert_not_awaited()
