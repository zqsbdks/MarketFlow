"""销售记录的数据访问函数。"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import InventoryBatchStatus, ProductStatus, SaleSource
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem


class InsufficientStockError(Exception):
    """商品未过期批次库存不足。"""

    def __init__(self, product_name: str, requested: int, available: int) -> None:
        # product_name：库存不足的商品名称，用于生成前端可读的错误信息。
        self.product_name = product_name
        # requested：顾客本次准备购买的数量。
        self.requested = requested
        # available：所有未过期可售批次的剩余数量合计。
        self.available = available
        super().__init__(product_name)


# region 获取销售单列表
async def get_sales_list(
    page: int,
    page_size: int,
    start_time: datetime | None,
    end_time: datetime | None,
    sale_no: str | None,
    db: AsyncSession,
) -> tuple[list[Sale], int]:
    """按条件分页查询销售单，并返回当前页销售单和总数。"""

    # 先创建不带筛选条件的基础查询。
    list_statement = select(Sale)
    count_statement = select(func.count(Sale.id))

    # 开始时间和结束时间都包含在查询范围内。
    if start_time is not None:
        list_statement = list_statement.where(Sale.sold_at >= start_time)
        count_statement = count_statement.where(Sale.sold_at >= start_time)

    if end_time is not None:
        list_statement = list_statement.where(Sale.sold_at <= end_time)
        count_statement = count_statement.where(Sale.sold_at <= end_time)

    # 销售单号使用唯一值精确查询。
    if sale_no is not None:
        list_statement = list_statement.where(Sale.sale_no == sale_no)
        count_statement = count_statement.where(Sale.sale_no == sale_no)

    count_result = await db.scalar(count_statement)
    total = count_result if count_result is not None else 0

    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(selectinload(Sale.items))
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.scalars(list_statement)
    sales = list(list_result.all())

    return sales, total


# endregion


# region 创建销售单并扣减批次库存
async def create_sale(
    # requested_quantities：商品ID和购买总数量，例如 {1: 8, 3: 2}。
    requested_quantities: dict[int, int],
    # sold_at：本次结账时间，同时用于生成销售单号。
    sold_at: datetime,
    # db：当前请求共用的数据库会话；本函数只 flush，不负责 commit。
    db: AsyncSession,
) -> Sale:
    """按先到期先销售原则扣减批次库存，并创建销售单和批次级明细。"""

    # 三个变量分别累计整张小票的销售额、成本和数据库销售明细。
    total_amount = Decimal("0.00")
    total_cost = Decimal("0.00")
    sale_items: list[SaleItem] = []

    # requested_quantities 已在 Service 中合并，因此每个商品只处理一次。
    for product_id, requested_quantity in requested_quantities.items():
        # 第一步：读取并锁定商品行，避免两个收银请求同时扣减同一商品库存。
        product = await db.scalar(select(Product).where(Product.id == product_id).with_for_update())
        if product is None:
            # LookupError 会由 Service 转成 404 响应。
            raise LookupError(product_id)
        if product.status != ProductStatus.ON_SALE:
            # 商品存在但已停售时不能继续创建销售明细。
            raise PermissionError(product.name)

        # 第二步：查询这个商品所有有库存且未过期的批次。
        # expiration_date >= 今天表示当天到期仍可销售；没有日期的历史批次排在最后。
        batch_statement = (
            select(InventoryBatch)
            .options(selectinload(InventoryBatch.purchase_item))
            .where(
                InventoryBatch.product_id == product_id,
                InventoryBatch.remaining_quantity > 0,
                or_(
                    InventoryBatch.expiration_date.is_(None),
                    InventoryBatch.expiration_date >= date.today(),
                ),
            )
            .order_by(
                # False 排在 True 前面，因此有明确到期日期的批次优先。
                InventoryBatch.expiration_date.is_(None),
                # 在有日期的批次中，越早到期越先扣减，即“先到期先出库”。
                InventoryBatch.expiration_date.asc(),
                # 到期日期相同则优先使用更早到货的批次，最后用主键保证顺序稳定。
                InventoryBatch.arrived_at.asc(),
                InventoryBatch.id.asc(),
            )
            # 锁定实际准备扣减的批次，防止并发销售导致同一库存被扣两次。
            .with_for_update()
        )
        batches = list((await db.scalars(batch_statement)).all())

        # 第三步：批次库存才是真正可售库存；商品表的汇总库存不作为扣减依据。
        available_quantity = sum(batch.remaining_quantity for batch in batches)
        if available_quantity < requested_quantity:
            raise InsufficientStockError(
                product_name=product.name,
                requested=requested_quantity,
                available=available_quantity,
            )

        # 第四步：从最早到期批次开始扣，直到满足本次商品购买数量。
        quantity_left = requested_quantity
        for batch in batches:
            if quantity_left == 0:
                break
            # 当前批次数量不足时全部扣完，剩余需求继续从下一个批次扣。
            deducted_quantity = min(batch.remaining_quantity, quantity_left)
            batch.remaining_quantity -= deducted_quantity
            if batch.remaining_quantity == 0:
                batch.status = InventoryBatchStatus.SOLD_OUT

            # 每个批次的进货成本可能不同，所以跨批次时分别生成 SaleItem。
            unit_cost = batch.purchase_item.unit_cost
            subtotal = product.sale_price * deducted_quantity
            cost_subtotal = unit_cost * deducted_quantity
            sale_items.append(
                SaleItem(
                    product_id=product.id,
                    inventory_batch_id=batch.id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    department_id=product.department_id,
                    quantity=deducted_quantity,
                    unit_price=product.sale_price,
                    unit_cost=unit_cost,
                    subtotal=subtotal,
                    cost_subtotal=cost_subtotal,
                )
            )
            total_amount += subtotal
            total_cost += cost_subtotal
            quantity_left -= deducted_quantity

        # 第五步：先把批次扣减写入当前事务，再重新求和同步商品总库存。
        # 这样不仅完成本次扣减，也能消除商品表之前可能存在的汇总差异。
        await db.flush()
        product.stock_quantity = int(
            await db.scalar(
                select(func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0)).where(
                    InventoryBatch.product_id == product.id
                )
            )
            or 0
        )

    # 第六步：生成当天递增销售单号，例如 S202609170001。
    sale_no_prefix = f"S{sold_at:%Y%m%d}"
    latest_sale_no = await db.scalar(
        select(func.max(Sale.sale_no)).where(Sale.sale_no.like(f"{sale_no_prefix}%"))
    )
    next_number = int(latest_sale_no[-4:]) + 1 if latest_sale_no else 1
    # 第七步：创建销售主表；items relationship 会自动给明细填写 sale_id。
    sale = Sale(
        sale_no=f"{sale_no_prefix}{next_number:04d}",
        sold_at=sold_at,
        total_amount=total_amount,
        total_cost=total_cost,
        gross_profit=total_amount - total_cost,
        source=SaleSource.POS,
        items=sale_items,
    )
    db.add(sale)
    # flush 取得数据库生成的 sale.id，但最终提交仍由 Service 统一负责。
    await db.flush()
    return sale


# endregion


# region 根据销售单号获取详情
async def get_sales_detail(
    db: AsyncSession,
    sale_no: str,
) -> Sale | None:
    """根据唯一销售单号查询销售单，并提前加载商品明细。"""

    detail_statement = select(Sale).where(Sale.sale_no == sale_no).options(selectinload(Sale.items))
    detail_result = await db.scalar(detail_statement)
    return detail_result


# endregion


__all__ = [
    "InsufficientStockError",
    "create_sale",
    "get_sales_detail",
    "get_sales_list",
]
