"""商品查询的数据访问函数。"""

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.models.enums import InventoryBatchStatus, ProductStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product

StockInconsistency = tuple[int, str, str, int, int]
ProductInventorySummary = tuple[int, int, int, int, int, int]


# region 构建批次库存汇总子查询
def _build_batch_stock_summary() -> Subquery:
    """按商品汇总全部、可售、临期和过期批次库存，供列表与检查任务复用。"""

    return (
        select(
            InventoryBatch.product_id.label("product_id"),
            # 全部库存包含所有批次当前仍然存在的数量，包括临期和过期商品。
            func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0).label(
                "batch_stock_quantity"
            ),
            # 可售库存排除已经过期的批次；当天到期的商品当天仍允许销售。
            func.coalesce(
                func.sum(
                    case(
                        (
                            or_(
                                InventoryBatch.expiration_date.is_(None),
                                InventoryBatch.expiration_date >= func.current_date(),
                            ),
                            InventoryBatch.remaining_quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("saleable_stock_quantity"),
            # 临期数量和批次数使用定时任务维护的批次状态统计。
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.status == InventoryBatchStatus.NEAR_EXPIRY,
                                InventoryBatch.expiration_date >= func.current_date(),
                                InventoryBatch.remaining_quantity > 0,
                            ),
                            InventoryBatch.remaining_quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("near_expiry_stock_quantity"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.status == InventoryBatchStatus.NEAR_EXPIRY,
                                InventoryBatch.expiration_date >= func.current_date(),
                                InventoryBatch.remaining_quantity > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("near_expiry_batch_count"),
            # 过期统计直接比较到期日期，避免凌晨状态任务尚未执行时漏掉当天的新过期批次。
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.expiration_date < func.current_date(),
                                InventoryBatch.remaining_quantity > 0,
                            ),
                            InventoryBatch.remaining_quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("expired_stock_quantity"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.expiration_date < func.current_date(),
                                InventoryBatch.remaining_quantity > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("expired_batch_count"),
        )
        .group_by(InventoryBatch.product_id)
        .subquery()
    )


# endregion


# region 获取商品列表
async def get_products_list(
    page: int,
    page_size: int,
    keyword: str | None,
    department_id: int | None,
    category_id: int | None,
    status: ProductStatus | None,
    stock_consistent: bool | None,
    low_stock: bool | None,
    db: AsyncSession,
) -> tuple[list[tuple[Product, ProductInventorySummary]], int]:
    """按条件分页查询商品，并返回当前页商品和符合条件的总数。"""

    # 只添加调用方实际传入的条件；空条件列表表示查询全部商品。
    conditions: list[ColumnElement[bool]] = []
    if keyword is not None:
        conditions.append(Product.name.ilike(f"%{keyword}%"))
    if department_id is not None:
        conditions.append(Product.department_id == department_id)
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if status is not None:
        conditions.append(Product.status == status)

    # 先按商品分组汇总所有批次的剩余数量，再作为子查询关联商品表。
    # 已售罄批次的 remaining_quantity 是 0，因此无需按批次状态排除。
    batch_stock_summary = _build_batch_stock_summary()
    # 没有任何批次的商品经过外连接后得到 NULL，这里把它转换成库存 0。
    batch_stock_quantity = func.coalesce(batch_stock_summary.c.batch_stock_quantity, 0)
    saleable_stock_quantity = func.coalesce(
        batch_stock_summary.c.saleable_stock_quantity,
        0,
    )
    near_expiry_stock_quantity = func.coalesce(
        batch_stock_summary.c.near_expiry_stock_quantity,
        0,
    )
    near_expiry_batch_count = func.coalesce(
        batch_stock_summary.c.near_expiry_batch_count,
        0,
    )
    expired_stock_quantity = func.coalesce(
        batch_stock_summary.c.expired_stock_quantity,
        0,
    )
    expired_batch_count = func.coalesce(
        batch_stock_summary.c.expired_batch_count,
        0,
    )

    # stock_consistent 未传时不筛选；传 true/false 时分别查询一致或不一致商品。
    if stock_consistent is True:
        conditions.append(Product.stock_quantity == batch_stock_quantity)
    elif stock_consistent is False:
        conditions.append(Product.stock_quantity != batch_stock_quantity)

    # 低库存以“可售库存”和每个商品自己的预警阈值比较，不使用包含过期批次的全部库存。
    if low_stock is True:
        conditions.extend(
            [
                Product.low_stock_threshold.is_not(None),
                saleable_stock_quantity <= Product.low_stock_threshold,
            ]
        )
    elif low_stock is False:
        # 没有设置阈值的商品不会触发预警，因此也属于“未触发低库存预警”。
        conditions.append(
            or_(
                Product.low_stock_threshold.is_(None),
                saleable_stock_quantity > Product.low_stock_threshold,
            )
        )

    # 列表查询和数量查询使用完全相同的筛选条件，保证分页数据准确。
    count_statement = (
        select(func.count(Product.id))
        .outerjoin(
            batch_stock_summary,
            batch_stock_summary.c.product_id == Product.id,
        )
        .where(*conditions)
    )
    count_result = await db.scalar(count_statement)
    total = count_result if count_result is not None else 0

    offset = (page - 1) * page_size
    list_statement = (
        select(
            Product,
            batch_stock_quantity,
            saleable_stock_quantity,
            near_expiry_stock_quantity,
            near_expiry_batch_count,
            expired_stock_quantity,
            expired_batch_count,
        )
        # Service 需要部门名和分类名，因此在异步会话中提前加载两个关系。
        .options(
            selectinload(Product.department),
            selectinload(Product.category),
        )
        .outerjoin(
            batch_stock_summary,
            batch_stock_summary.c.product_id == Product.id,
        )
        .where(*conditions)
        .order_by(Product.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.execute(list_statement)
    products = [
        (
            product,
            (
                int(total_stock),
                int(saleable_stock),
                int(near_expiry_stock),
                int(near_expiry_batches),
                int(expired_stock),
                int(expired_batches),
            ),
        )
        for (
            product,
            total_stock,
            saleable_stock,
            near_expiry_stock,
            near_expiry_batches,
            expired_stock,
            expired_batches,
        ) in list_result.all()
    ]

    return products, total


# endregion


# region 检查商品与批次库存一致性
async def get_stock_inconsistencies(db: AsyncSession) -> list[StockInconsistency]:
    """查询库存不一致的商品；本函数只读取数据，不执行任何自动修复。"""

    batch_stock_summary = _build_batch_stock_summary()
    batch_stock_quantity = func.coalesce(batch_stock_summary.c.batch_stock_quantity, 0)
    statement = (
        select(
            Product.id,
            Product.product_no,
            Product.name,
            Product.stock_quantity,
            batch_stock_quantity,
        )
        .outerjoin(
            batch_stock_summary,
            batch_stock_summary.c.product_id == Product.id,
        )
        .where(Product.stock_quantity != batch_stock_quantity)
        .order_by(Product.id.asc())
    )
    result = await db.execute(statement)
    return [
        (product_id, product_no, name, product_stock, int(batch_stock))
        for product_id, product_no, name, product_stock, batch_stock in result.all()
    ]


# endregion


# region 根据ID获取商品
async def get_product_by_id(
    product_id: int,
    db: AsyncSession,
) -> Product | None:
    """根据商品 ID 查询商品，并提前加载所属部门和分类。"""

    select_statement = (
        select(Product)
        .options(
            selectinload(Product.department),
            selectinload(Product.category),
        )
        .where(Product.id == product_id)
        # 如果当前会话已经加载过这个商品，也用数据库最新值覆盖缓存。
        .execution_options(populate_existing=True)
    )
    result = await db.scalar(select_statement)
    return result


# endregion


# region 修改商品
async def update_product(
    # product_id：需要更新的商品主键。
    product_id: int,
    # update_data：经过 Service 校验后，真正需要写入数据库的字段和值。
    update_data: dict[str, object],
    # db：当前请求的异步数据库会话；CRUD 不在这里提交事务。
    db: AsyncSession,
) -> Product:
    """更新指定商品，并返回包含部门和分类关系的最新商品对象。"""

    # 第一步：创建 UPDATE 语句。
    # update_data 已由 Service 使用 exclude_unset=True 过滤，只包含前端传入的字段。
    update_statement = update(Product).where(Product.id == product_id).values(**update_data)

    # 第二步：把 UPDATE 语句发送给数据库。
    # 此处不调用 commit，由 Service 在全部业务操作成功后统一提交。
    await db.execute(update_statement)

    # 第三步：重新查询修改后的商品。
    # UPDATE 只能修改商品表，selectinload 不能放在 UPDATE 上加载关联对象。
    # 因此更新后重新查询一次，取得最新字段以及 department、category 关系。
    updated_product = await get_product_by_id(product_id=product_id, db=db)
    if updated_product is None:
        # Service 已提前确认商品存在；这里只处理极少见的并发删除情况。
        raise RuntimeError("商品更新后无法重新查询")

    return updated_product


# endregion


__all__ = [
    "ProductInventorySummary",
    "get_product_by_id",
    "get_products_list",
    "get_stock_inconsistencies",
    "update_product",
]
