"""后台调度所需的候选记录查询；这里只读取数据，不执行业务操作。"""

from sqlalchemy import select

from app.models.inventory_batch import InventoryBatch
from app.models.purchase_plan import PurchasePlan


async def get_expired_product_ids(today, db):
    statement = (
        select(InventoryBatch.product_id)
        .where(InventoryBatch.expiration_date < today, InventoryBatch.remaining_quantity > 0)
        .distinct()
        .order_by(InventoryBatch.product_id)
    )
    result = await db.scalars(statement)
    return list(result.all())


async def get_due_plan_ids(latest_arrival_date, db):
    statement = (
        select(PurchasePlan.id)
        .where(
            PurchasePlan.purchase_id.is_(None),
            PurchasePlan.arrival_date <= latest_arrival_date,
        )
        .order_by(PurchasePlan.id)
    )
    result = await db.scalars(statement)
    return list(result.all())
