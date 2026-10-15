"""所有员工可查询门店，总部独占门店配置、统一目录和员工异动权限。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_verified_current_employee_id
from app.dependencies.db import get_db
from app.schemas.stores import (
    CompanyCategoryRequest,
    CompanyDepartmentRequest,
    EmployeeTransferRequest,
    HeadquartersEmployeeCreateRequest,
    StoreDepartmentRequest,
    StoreWriteRequest,
)
from app.services.stores import (
    company_category_service,
    company_data_service,
    company_department_service,
    create_store_service,
    enable_department_service,
    headquarters_create_employee_service,
    list_stores_service,
    store_departments_service,
    transfer_employee_service,
    update_store_service,
)

stores_router = APIRouter(prefix="/stores", tags=["stores"])


# region 门店查询与维护
@stores_router.get("", summary="查询可查看的门店")
async def list_stores(
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await list_stores_service(employee_id=employee_id, db=db, http_request=http_request)


@stores_router.get("/company-data", summary="查询统一部门、分类及总部可管理的员工")
async def company_data(
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await company_data_service(employee_id=employee_id, db=db, http_request=http_request)


@stores_router.get("/{store_id}/departments", summary="查询门店部门启用配置")
async def store_departments(
    store_id: int,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await store_departments_service(
        store_id=store_id, employee_id=employee_id, db=db, http_request=http_request
    )


@stores_router.post("", summary="总部创建门店")
async def create_store(
    request: StoreWriteRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await create_store_service(
        request=request, employee_id=employee_id, db=db, http_request=http_request
    )


@stores_router.put("/{store_id}", summary="总部修改门店")
async def update_store(
    store_id: int,
    request: StoreWriteRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await update_store_service(
        store_id=store_id,
        request=request,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


@stores_router.put("/{store_id}/departments/{department_id}", summary="总部设置门店启用部门")
async def enable_department(
    store_id: int,
    department_id: int,
    request: StoreDepartmentRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await enable_department_service(
        store_id=store_id,
        department_id=department_id,
        request=request,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


# endregion


# region 员工调店和角色任命


@stores_router.put("/employees/{target_id}/assignment", summary="仅总部可以调店及任命店长")
async def transfer_employee(
    target_id: int,
    request: EmployeeTransferRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await transfer_employee_service(
        target_id=target_id,
        request=request,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


@stores_router.post("/employees", summary="总部创建门店店长或其他员工账号")
async def headquarters_create_employee(
    request: HeadquartersEmployeeCreateRequest,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await headquarters_create_employee_service(
        request=request, employee_id=employee_id, db=db, http_request=http_request
    )


# endregion


# region 全公司统一部门分类
@stores_router.post("/company-departments", summary="总部创建统一部门")
@stores_router.put("/company-departments/{record_id}", summary="总部修改统一部门")
async def company_department(
    request: CompanyDepartmentRequest,
    record_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await company_department_service(
        request=request,
        record_id=record_id,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


@stores_router.post("/company-categories", summary="总部创建统一分类")
@stores_router.put("/company-categories/{record_id}", summary="总部修改统一分类")
async def company_category(
    request: CompanyCategoryRequest,
    record_id: int | None = None,
    employee_id: int = Depends(get_verified_current_employee_id),
    db: AsyncSession = Depends(get_db),
    *,
    http_request: Request,
):
    return await company_category_service(
        request=request,
        record_id=record_id,
        employee_id=employee_id,
        db=db,
        http_request=http_request,
    )


# endregion
