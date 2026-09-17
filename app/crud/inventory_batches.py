"""库存批次的数据访问函数。"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.enums import InventoryBatchStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase_item import PurchaseItem


# region 获取库存批次列表
async def get_inventory_batches_list(
    # page：当前页码，从 1 开始。
    page: int,
    # page_size：每页最多返回的批次数量。
    page_size: int,
    # status：可选批次状态；None 表示不按照状态筛选。
    status: InventoryBatchStatus | None,
    # supplier_id：可选供应商 ID，通过来源进货明细筛选。
    supplier_id: int | None,
    # product_id：可选正式商品 ID。
    product_id: int | None,
    # department_id：可选所属部门 ID，通过正式商品筛选。
    department_id: int | None,
    # expiration_start 和 expiration_end：可选到期日期范围，包含边界日期。
    expiration_start: date | None,
    expiration_end: date | None,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
) -> tuple[list[InventoryBatch], int]:
    """按状态分页查询全部库存批次，并返回当前页数据及总记录数。"""

    # 第一步：只添加前端实际传入的筛选条件；空列表表示查询全部批次。
    # 现在存在多个可选条件，使用列表可以确保总数查询和列表查询完全一致。
    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(InventoryBatch.status == status)
    if supplier_id is not None:
        conditions.append(InventoryBatch.purchase_item.has(PurchaseItem.supplier_id == supplier_id))
    if product_id is not None:
        conditions.append(InventoryBatch.product_id == product_id)
    if department_id is not None:
        conditions.append(InventoryBatch.product.has(Product.department_id == department_id))
    if expiration_start is not None:
        conditions.append(InventoryBatch.expiration_date >= expiration_start)
    if expiration_end is not None:
        conditions.append(InventoryBatch.expiration_date <= expiration_end)

    # 第二步：数量查询和列表查询使用同一组 WHERE 条件。
    count_statement = select(func.count(InventoryBatch.id)).where(*conditions)
    list_statement = select(InventoryBatch).where(*conditions)

    # 第三步：执行数量查询。数据库没有符合条件的记录时按 0 处理。
    total = int(await db.scalar(count_statement) or 0)

    # 第四步：把页码转换为需要跳过的记录数，例如第 2 页每页 10 条会跳过 10 条。
    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(
            # Service 需要商品编号、名称和部门名称，因此提前加载两层关系。
            selectinload(InventoryBatch.product).selectinload(Product.department),
        )
        # 最新到货的批次优先显示；到货时间相同时再按批次 ID 倒序排列。
        .order_by(InventoryBatch.arrived_at.desc(), InventoryBatch.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    # 第五步：执行列表查询，并把 ScalarResult 转换成普通列表。
    result = await db.scalars(list_statement)
    batches = list(result.all())

    return batches, total


# endregion


# region 自动刷新库存批次状态
async def refresh_inventory_batch_statuses(
    current_date: date,
    db: AsyncSession,
) -> int:
    """根据剩余数量和临期日期刷新全部批次状态，并返回变更数量。"""

    # 临期提醒天数保存在商品表，因此提前加载每个批次对应的正式商品。
    statement = select(InventoryBatch).options(selectinload(InventoryBatch.product))
    result = await db.scalars(statement)
    batches = list(result.all())

    changed_count = 0
    for batch in batches:
        # 状态优先级：售完 > 临期 > 可用。
        if batch.remaining_quantity == 0:
            new_status = InventoryBatchStatus.SOLD_OUT
        elif (
            batch.expiration_date is not None
            and batch.product.expiry_warning_days is not None
            and batch.expiration_date
            <= current_date + timedelta(days=batch.product.expiry_warning_days)
        ):
            new_status = InventoryBatchStatus.NEAR_EXPIRY
        else:
            new_status = InventoryBatchStatus.AVAILABLE

        if batch.status != new_status:
            batch.status = new_status
            changed_count += 1

    # 这里只修改当前事务中的 ORM 对象，commit 仍由调用方统一执行。
    await db.flush()
    return changed_count


# endregion


# region 根据ID获取库存批次详情
async def get_inventory_batch_by_id(
    # batch_id：要查询的库存批次主键。
    batch_id: int,
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
) -> InventoryBatch | None:
    """根据批次 ID 查询批次，并提前加载商品和进货来源关系。"""

    # 第一步：以库存批次为主对象，并声明详情响应需要提前加载的关系路径。
    statement = (
        select(InventoryBatch)
        .options(
            # 批次 → 商品 → 部门。
            selectinload(InventoryBatch.product).selectinload(Product.department),
            # 批次 → 商品 → 分类。
            selectinload(InventoryBatch.product).selectinload(Product.category),
            # 批次 → 进货明细 → 进货单。
            selectinload(InventoryBatch.purchase_item).selectinload(PurchaseItem.purchase),
        )
        .where(InventoryBatch.id == batch_id)
    )

    # 第二步：执行查询。batch_id 是唯一主键，未查到时返回 None。
    return await db.scalar(statement)


# endregion


# region 修改库存批次数量
async def update_inventory_batch_quantity(
    batch: InventoryBatch,
    remaining_quantity: int,
    employee_id: int,
    reason: str | None,
    db: AsyncSession,
) -> InventoryBatch:
    """修改批次剩余数量，记录调整历史并重新汇总商品总库存。"""

    before_quantity = batch.remaining_quantity
    batch.remaining_quantity = remaining_quantity

    # 修改后立即同步批次状态，不必等待半小时定时任务。
    if remaining_quantity == 0:
        batch.status = InventoryBatchStatus.SOLD_OUT
    elif (
        batch.expiration_date is not None
        and batch.product.expiry_warning_days is not None
        and batch.expiration_date
        <= date.today() + timedelta(days=batch.product.expiry_warning_days)
    ):
        batch.status = InventoryBatchStatus.NEAR_EXPIRY
    else:
        batch.status = InventoryBatchStatus.AVAILABLE

    # 先把新批次数量发送到数据库，使后面的 SUM 查询能读取本次修改。
    await db.flush()
    batch_stock_statement = select(
        func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0)
    ).where(InventoryBatch.product_id == batch.product_id)
    batch.product.stock_quantity = int(await db.scalar(batch_stock_statement) or 0)

    # 保存人工调整历史。原因可以为空，但前后数量、差异和操作人始终保留。
    await create_operation_audit_log(
        employee_id=employee_id,
        module="inventory",
        action="update_quantity",
        target_type="inventory_batch",
        target_id=batch.id,
        before_data={"remaining_quantity": before_quantity},
        after_data={"remaining_quantity": remaining_quantity},
        reason=reason,
        db=db,
    )
    return batch


# endregion


__all__ = [
    "get_inventory_batch_by_id",
    "get_inventory_batches_list",
    "refresh_inventory_batch_statuses",
    "update_inventory_batch_quantity",
]
