"""商品查询的数据访问函数。"""

from typing import Any, cast

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.core.exceptions import ConcurrentUpdateError
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
    conditions: list[ColumnElement[bool]] = []
    if keyword is not None:
        conditions.append(
            or_(Product.name.ilike(f"%{keyword}%"), Product.product_no.ilike(f"%{keyword}%"))
        )
    if department_id is not None:
        conditions.append(Product.department_id == department_id)
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if status is not None:
        conditions.append(Product.status == status)
    batch_stock_summary = _build_batch_stock_summary()
    batch_stock_quantity = func.coalesce(batch_stock_summary.c.batch_stock_quantity, 0)
    saleable_stock_quantity = func.coalesce(batch_stock_summary.c.saleable_stock_quantity, 0)
    near_expiry_stock_quantity = func.coalesce(batch_stock_summary.c.near_expiry_stock_quantity, 0)
    near_expiry_batch_count = func.coalesce(batch_stock_summary.c.near_expiry_batch_count, 0)
    expired_stock_quantity = func.coalesce(batch_stock_summary.c.expired_stock_quantity, 0)
    expired_batch_count = func.coalesce(batch_stock_summary.c.expired_batch_count, 0)
    if stock_consistent is True:
        conditions.append(Product.stock_quantity == batch_stock_quantity)
    elif stock_consistent is False:
        conditions.append(Product.stock_quantity != batch_stock_quantity)
    if low_stock is True:
        conditions.extend(
            [
                Product.low_stock_threshold.is_not(None),
                saleable_stock_quantity <= Product.low_stock_threshold,
            ]
        )
    elif low_stock is False:
        conditions.append(
            or_(
                Product.low_stock_threshold.is_(None),
                saleable_stock_quantity > Product.low_stock_threshold,
            )
        )
    count_statement = (
        select(func.count(Product.id))
        .outerjoin(batch_stock_summary, batch_stock_summary.c.product_id == Product.id)
        .where(*conditions)
    )
    if db.info.get("read_store_id") is not None:
        count_statement = count_statement.where(Product.store_id == db.info["read_store_id"])
    count_result = await db.scalar(count_statement)
    if count_result is not None:
        total = count_result
    else:
        total = 0
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
        .options(selectinload(Product.department), selectinload(Product.category))
        .outerjoin(batch_stock_summary, batch_stock_summary.c.product_id == Product.id)
        .where(*conditions)
        .order_by(Product.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    if db.info.get("read_store_id") is not None:
        list_statement = list_statement.where(Product.store_id == db.info["read_store_id"])
    list_result = await db.execute(list_statement)
    products_values = []
    for (
        products_product,
        products_total_stock,
        products_saleable_stock,
        products_near_expiry_stock,
        products_near_expiry_batches,
        products_expired_stock,
        products_expired_batches,
    ) in list_result.all():
        products_values.append(
            (
                products_product,
                (
                    int(products_total_stock),
                    int(products_saleable_stock),
                    int(products_near_expiry_stock),
                    int(products_near_expiry_batches),
                    int(products_expired_stock),
                    int(products_expired_batches),
                ),
            )
        )
    products = products_values
    return (products, total)


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
        .outerjoin(batch_stock_summary, batch_stock_summary.c.product_id == Product.id)
        .where(Product.stock_quantity != batch_stock_quantity)
        .order_by(Product.id.asc())
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Product.store_id == db.info["read_store_id"])
    result = await db.execute(statement)
    result_values = []
    for (
        result_product_id,
        result_product_no,
        result_name,
        result_product_stock,
        result_batch_stock,
    ) in result.all():
        result_values.append(
            (
                result_product_id,
                result_product_no,
                result_name,
                result_product_stock,
                int(result_batch_stock),
            )
        )
    return result_values


# endregion


# region 根据ID获取商品
async def get_product_by_id(product_id: int, db: AsyncSession) -> Product | None:
    """根据商品 ID 查询商品，并提前加载所属部门和分类。"""
    select_statement = (
        select(Product)
        .options(selectinload(Product.department), selectinload(Product.category))
        .where(Product.id == product_id)
        .execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        select_statement = select_statement.where(Product.store_id == db.info["read_store_id"])
    result = await db.scalar(select_statement)
    return result


# endregion


# region 修改商品
async def update_product(
    product_id: int, update_data: dict[str, object], expected_version: int, db: AsyncSession
) -> Product:
    """更新指定商品，并返回包含部门和分类关系的最新商品对象。"""
    update_statement = (
        update(Product)
        .where(Product.id == product_id, Product.version == expected_version)
        .values(**update_data, version=Product.version + 1)
    )
    if db.info.get("own_store_id") is not None:
        update_statement = update_statement.where(Product.store_id == db.info["own_store_id"])
    result = await db.execute(update_statement)
    if cast(CursorResult[Any], result).rowcount != 1:
        raise ConcurrentUpdateError("商品资料已被其他员工修改，请刷新后重试")
    updated_product = await get_product_by_id(product_id=product_id, db=db)
    if updated_product is None:
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
