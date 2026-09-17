"""库存批次的数据访问函数。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    # db：当前请求使用的异步数据库会话。
    db: AsyncSession,
) -> tuple[list[InventoryBatch], int]:
    """按状态分页查询全部库存批次，并返回当前页数据及总记录数。"""

    # 第一步：分别创建总数查询和列表查询，两条语句必须使用相同筛选条件。
    count_statement = select(func.count(InventoryBatch.id))
    list_statement = select(InventoryBatch)

    # 第二步：只有前端传入 status 时才添加 WHERE 条件；不传则查询全部状态。
    if status is not None:
        count_statement = count_statement.where(InventoryBatch.status == status)
        list_statement = list_statement.where(InventoryBatch.status == status)

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


__all__ = ["get_inventory_batch_by_id", "get_inventory_batches_list"]
