"""从废弃单快照汇总损耗，不重复计算明细或改变销售毛利口径。"""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import discard_analysis as data_access
from app.crud.auth import get_employee_by_id
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.enums import EmployeeRole
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
    db: AsyncSession,
    employee_id: int,
    request: DiscardAnalysisRequest,
    *,
    include_breakdowns: bool = True,
    limit_days: int | None = 367,
    http_request: Request | None = None,
) -> DiscardAnalysisResponse:
    """按完整废弃日期统计数量和成本，并按原因、部门、门店拆分。

    员工及门店读取范围先校验；只有总部可得到门店对比。
    成本来自废弃时的批次成本快照，比例按损耗成本计算，不按数量计算。
    无数据或总成本为0时返回空分组或0比例，避免除零。此查询不写入业务数据。"""
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            if not is_headquarters:
                raise HTTPException(403, "只有总部经营报表支持全公司汇总")
            selected_store_id = None
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and (raw_store_id != "all"):
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=False,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id
    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(401, "当前登录员工不存在")
    if not employee.is_active or employee.must_change_password:
        if not employee.is_active:
            selected_text = "账号已停用"
        else:
            selected_text = "请先修改初始密码"
        raise HTTPException(403, selected_text)
    if request.start_date > request.end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if request.end_date == date.max:
        raise HTTPException(400, "结束日期超出支持范围")
    if limit_days is not None and (request.end_date - request.start_date).days >= limit_days:
        raise HTTPException(400, "查询范围不能超过367天")
    if (
        db.info.get("store_context")
        and db.info.get("read_store_id") is None
        and (employee.role != EmployeeRole.HEADQUARTERS)
    ):
        raise HTTPException(403, "只有总部经营报表支持全公司汇总")
    if not include_breakdowns:
        records, qty, amount = (await data_access.get_loss_totals(db=db, request=request)).one()
        return DiscardAnalysisResponse(
            record_count=records, quantity=qty, cost=amount, reasons=[], departments=[], stores=[]
        )
    rows = (await data_access.get_loss_groups(db=db, request=request)).all()
    groups: list[dict[str, list]] = [{}, {}, {}]
    count, quantity, cost = (0, 0, Decimal("0.00"))
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
        items = []
        for key, value in sorted(group.items(), key=loss_group_sort_key):
            if cost:
                cost_share = (value[2] * 100 / cost).quantize(Decimal("0.01"))
            else:
                cost_share = Decimal("0.00")
            items.append(
                DiscardAnalysisGroup(
                    key=key,
                    name=value[0],
                    quantity=value[1],
                    cost=value[2],
                    cost_share=cost_share,
                )
            )
        return items

    if employee.role == EmployeeRole.HEADQUARTERS:
        stores_value = output(groups[2])
    else:
        stores_value = []
    return DiscardAnalysisResponse(
        record_count=count,
        quantity=quantity,
        cost=cost,
        reasons=output(groups[0]),
        departments=output(groups[1]),
        stores=stores_value,
    )


def loss_group_sort_key(item):
    """先按损耗金额从高到低排列；金额相同时按编号排列。"""
    group_id = item[0]
    totals = item[1]
    cost = totals[2]
    return -cost, group_id
