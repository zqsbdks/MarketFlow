"""从废弃单快照汇总损耗，不重复计算明细或改变销售毛利口径。"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.models.enums import EmployeeRole
from app.models.inventory_discard import InventoryDiscard
from app.models.store import Store
from app.schemas.discard_analysis import (
    DiscardAnalysisGroup,
    DiscardAnalysisRequest,
    DiscardAnalysisResponse,
)

REASONS = {
    "expired": "过期",
    "damaged": "破损",
    "spoiled": "腐败",
    "contaminated": "污染",
    "other": "其他",
}


async def get_discard_analysis(
    db: AsyncSession, employee_id: int, request: DiscardAnalysisRequest
) -> DiscardAnalysisResponse:
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if not employee.is_active or employee.must_change_password:
        raise HTTPException(403, "账号已停用" if not employee.is_active else "请先修改初始密码")
    if request.start_date > request.end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if request.end_date == date.max:
        raise HTTPException(400, "结束日期超出支持范围")
    if (request.end_date - request.start_date).days > 366:
        raise HTTPException(400, "查询范围不能超过367天")
    if (
        db.info.get("store_context")
        and db.info.get("read_store_id") is None
        and employee.role != EmployeeRole.HEADQUARTERS
    ):
        raise HTTPException(403, "只有总部经营报表支持全公司汇总")
    conditions = [
        InventoryDiscard.created_at >= datetime.combine(request.start_date, time.min),
        InventoryDiscard.created_at
        < datetime.combine(request.end_date + timedelta(days=1), time.min),
    ]
    if request.department_id is not None:
        conditions.append(InventoryDiscard.department_id == request.department_id)
    # One grouped query gives a consistent snapshot for every total and breakdown.
    rows = (
        await db.execute(
            select(
                InventoryDiscard.store_id,
                Store.store_no,
                Store.name,
                InventoryDiscard.department_id,
                InventoryDiscard.department_name,
                InventoryDiscard.reason_code,
                func.count(InventoryDiscard.id),
                func.sum(InventoryDiscard.quantity),
                func.sum(InventoryDiscard.total_cost),
            )
            .join(Store, Store.id == InventoryDiscard.store_id)
            .where(*conditions)
            .group_by(
                InventoryDiscard.store_id,
                Store.store_no,
                Store.name,
                InventoryDiscard.department_id,
                InventoryDiscard.department_name,
                InventoryDiscard.reason_code,
            )
        )
    ).all()
    groups: list[dict[str, list]] = [{}, {}, {}]
    count, quantity, cost = 0, 0, Decimal("0.00")
    for store_id, store_no, store_name, dept_id, dept_name, reason, records, qty, amount in rows:
        count += records
        quantity += qty
        cost += amount
        names = [
            (reason, REASONS.get(reason, reason)),
            (str(dept_id), dept_name),
            (str(store_id), f"{store_no} {store_name.removeprefix('MarketFlow ')}"),
        ]
        for group, (key, name) in zip(groups, names, strict=True):
            entry = group.setdefault(key, [name, 0, Decimal("0.00")])
            entry[1] += qty
            entry[2] += amount

    def output(group):
        return [
            DiscardAnalysisGroup(
                key=key,
                name=value[0],
                quantity=value[1],
                cost=value[2],
                cost_share=(value[2] * 100 / cost).quantize(Decimal("0.01"))
                if cost
                else Decimal("0.00"),
            )
            for key, value in sorted(group.items(), key=lambda item: (-item[1][2], item[0]))
        ]

    return DiscardAnalysisResponse(
        record_count=count,
        quantity=quantity,
        cost=cost,
        reasons=output(groups[0]),
        departments=output(groups[1]),
        stores=output(groups[2]) if employee.role == EmployeeRole.HEADQUARTERS else [],
    )
