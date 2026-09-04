"""营业报表业务逻辑。"""

from datetime import datetime, time

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.employees import get_department_by_id
from app.crud.reports import get_departments_reports, get_rankings, get_reports
from app.models.enums import RankingGroupBy, RankingSortBy, RankingSortOrder
from app.schemas.reports_responses import (
    DepartmentResponse,
    RankingItemResponse,
    RankingsResponse,
    ReportResponse,
)

BUSINESS_OPENING_TIME = time(9, 0)
BUSINESS_CLOSING_TIME = time(21, 0)


# region 获取营业概览
async def overview_service(
    db: AsyncSession,
    employee_id: int,
    start_time: datetime | None,
    end_time: datetime | None,
    department_id: int | None,
) -> ReportResponse:
    """验证员工和查询条件，并返回营业概览。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 查询时间必须位于超市每天的营业时间之内。
    if start_time is not None:
        selected_start_time = start_time.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_time is not None:
        selected_end_time = end_time.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    # 传入部门ID时先确认部门真实存在；不传则统计整个店铺。
    if department_id is not None:
        department = await get_department_by_id(
            department_id=department_id,
            db=db,
        )
        if department is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )

    revenue, sales_cost, gross_profit, sales_quantity, sale_count = await get_reports(
        db=db,
        start_time=start_time,
        end_time=end_time,
        department_id=department_id,
    )

    return ReportResponse(
        revenue=revenue,
        sales_cost=sales_cost,
        gross_profit=gross_profit,
        sales_quantity=sales_quantity,
        sale_count=sale_count,
    )


# endregion


# region 获取部门营业对比
async def get_departments_service(
    db: AsyncSession,
    employee_id: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[DepartmentResponse]:
    """验证员工和查询时间，并返回所有部门的营业对比数据。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if start_time is not None:
        selected_start_time = start_time.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_time is not None:
        selected_end_time = end_time.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    department_values = await get_departments_reports(
        db=db,
        start_time=start_time,
        end_time=end_time,
    )

    departments: list[DepartmentResponse] = []
    for department_id, department_name, revenue, gross_profit, sales_quantity in department_values:
        department = DepartmentResponse(
            department_id=department_id,
            department_name=department_name,
            revenue=revenue,
            gross_profit=gross_profit,
            sales_quantity=sales_quantity,
        )
        departments.append(department)

    return departments


# endregion


# region 获取销售排行
async def get_rankings_service(
    db: AsyncSession,
    employee_id: int,
    start_date: datetime | None,
    end_date: datetime | None,
    department_id: int | None,
    group_by: RankingGroupBy,
    sort_by: RankingSortBy,
    sort_order: RankingSortOrder,
    page: int,
    page_size: int,
) -> RankingsResponse:
    """验证员工和查询参数，并返回销售排行。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if start_date is not None:
        selected_start_time = start_date.time()
        if not BUSINESS_OPENING_TIME <= selected_start_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="开始时间必须在 09:00 至 21:00 之间",
            )

    if end_date is not None:
        selected_end_time = end_date.time()
        if not BUSINESS_OPENING_TIME <= selected_end_time <= BUSINESS_CLOSING_TIME:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="结束时间必须在 09:00 至 21:00 之间",
            )

    if start_date is not None and end_date is not None and start_date >= end_date:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="开始时间必须早于结束时间",
        )

    if department_id is not None:
        department = await get_department_by_id(
            department_id=department_id,
            db=db,
        )
        if department is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="部门不存在",
            )

    offset = (page - 1) * page_size
    ranking_values, total = await get_rankings(
        db=db,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        page_size=page_size,
    )

    items: list[RankingItemResponse] = []
    for index, (item_id, item_name, quantity, amount) in enumerate(
        ranking_values,
        start=1,
    ):
        item = RankingItemResponse(
            rank=offset + index,
            id=item_id,
            name=item_name,
            quantity=quantity,
            amount=amount,
        )
        items.append(item)

    total_pages = (total + page_size - 1) // page_size
    return RankingsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


__all__ = [
    "BUSINESS_CLOSING_TIME",
    "BUSINESS_OPENING_TIME",
    "get_departments_service",
    "get_rankings_service",
    "overview_service",
]
