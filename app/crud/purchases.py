"""进货管理的数据访问函数。"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.crud.operation_audit_logs import create_operation_audit_log
from app.models.employee import Employee
from app.models.enums import EmployeeRole, InventoryBatchStatus, ProductStatus, PurchaseStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier_product import SupplierProduct
from app.schemas.purchases_requests import CreatePurchaseRequest


# region 获取进货单列表
async def get_all_purchases(
    offset: int,
    page_size: int,
    purchase_no: str | None,
    department_id: int | None,
    ordered_at: date | None,
    arrived_at: date | None,
    purchase_status: PurchaseStatus | None,
    db: AsyncSession,
) -> tuple[list[tuple[Purchase, int, int]], int]:
    """分页查询进货单，同时统计每张单的明细数和商品总数量。"""

    conditions: list[ColumnElement[bool]] = []
    if purchase_no is not None:
        # 两侧的%表示只要进货单号中包含关键字即可匹配。
        conditions.append(Purchase.purchase_no.ilike(f"%{purchase_no}%"))
    if department_id is not None:
        conditions.append(Purchase.department_id == department_id)
    if purchase_status is not None:
        conditions.append(Purchase.status == purchase_status)
    if ordered_at is not None:
        # 请求传入的是日期，查询范围从当天00:00到第二天00:00之前。
        day_start = datetime.combine(ordered_at, time.min)
        next_day_start = day_start + timedelta(days=1)
        conditions.append(Purchase.ordered_at >= day_start)
        conditions.append(Purchase.ordered_at < next_day_start)
    if arrived_at is not None:
        # arrived_at是实际到货时间；按日期查询时同样转换成一天的时间范围。
        arrival_day_start = datetime.combine(arrived_at, time.min)
        next_arrival_day_start = arrival_day_start + timedelta(days=1)
        conditions.append(Purchase.arrived_at >= arrival_day_start)
        conditions.append(Purchase.arrived_at < next_arrival_day_start)

    # 先按进货单分组统计明细行数和所有明细quantity之和。
    item_summary = (
        select(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.count(PurchaseItem.id).label("item_count"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("total_quantity"),
        )
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )

    # 外连接统计结果，因此即使某张进货单暂时没有明细也仍然会出现在列表中。
    list_statement = (
        select(
            Purchase,
            func.coalesce(item_summary.c.item_count, 0),
            func.coalesce(item_summary.c.total_quantity, 0),
        )
        .outerjoin(item_summary, item_summary.c.purchase_id == Purchase.id)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
        )
        .where(*conditions)
        .order_by(Purchase.ordered_at.desc(), Purchase.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = select(func.count(Purchase.id)).where(*conditions)

    total = int(await db.scalar(count_statement) or 0)
    query_result = await db.execute(list_statement)

    purchases: list[tuple[Purchase, int, int]] = []
    for purchase, item_count, total_quantity in query_result.all():
        purchases.append((purchase, int(item_count), int(total_quantity)))
    return purchases, total


# endregion


# region 获取进货单详情
async def get_purchase_by_id(
    purchase_id: int,
    db: AsyncSession,
) -> Purchase | None:
    """根据ID查询进货单，并加载部门、员工和全部进货明细。"""

    statement = (
        select(Purchase)
        .options(
            selectinload(Purchase.department),
            selectinload(Purchase.created_by_employee),
            selectinload(Purchase.received_by_employee),
            selectinload(Purchase.items),
        )
        .where(Purchase.id == purchase_id)
        .execution_options(populate_existing=True)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 创建进货单
async def create_purchase(
    purchase: CreatePurchaseRequest,
    created_by: int,
    db: AsyncSession,
) -> Purchase:
    """创建一张进货单及其全部进货明细，并发送到当前数据库事务。"""

    # 创建时间由后端统一确定；预计到货时间固定为下单时间的两天后。
    ordered_at = datetime.now()
    expected_arrival_at = ordered_at + timedelta(days=2)

    # 进货单号格式为 PUR + 下单日期 + 当天四位流水号，例如 PUR202609130001。
    # substr(..., 12) 从编号第 12 个字符开始取出最后四位流水号。
    purchase_no_prefix = f"PUR{ordered_at:%Y%m%d}"
    number_part = cast(func.substr(Purchase.purchase_no, 12), Integer)
    number_statement = select(func.coalesce(func.max(number_part), 0)).where(
        Purchase.purchase_no.like(f"{purchase_no_prefix}%")
    )
    current_max_number = int(await db.scalar(number_statement) or 0)
    purchase_no = f"{purchase_no_prefix}{current_max_number + 1:04d}"

    # 一次查询取得请求中使用的所有供应商商品，避免在循环里重复访问数据库。
    supplier_product_ids = [item.supplier_product_id for item in purchase.items]
    catalog_statement = (
        select(SupplierProduct)
        .options(
            selectinload(SupplierProduct.supplier),
            selectinload(SupplierProduct.product),
        )
        .where(SupplierProduct.id.in_(supplier_product_ids))
    )
    catalog_result = await db.scalars(catalog_statement)
    catalog_products = {
        catalog_product.id: catalog_product for catalog_product in catalog_result.all()
    }

    # CRUD 层必须拿到每一条目录数据，才能保存可信的名称、供应商和单价快照。
    missing_ids = sorted(set(supplier_product_ids) - catalog_products.keys())
    if missing_ids:
        missing_text = ", ".join(str(item_id) for item_id in missing_ids)
        raise ValueError(f"供应商商品目录不存在：{missing_text}")

    purchase_items: list[PurchaseItem] = []
    total_amount = Decimal("0.00")

    for requested_item in purchase.items:
        # requested_item 是前端提交的一条进货明细；catalog_product 是数据库目录记录。
        catalog_product = catalog_products[requested_item.supplier_product_id]
        subtotal = catalog_product.unit_cost * requested_item.quantity
        total_amount += subtotal

        # 创建进货单时还没有实际到货时间，因此暂用预计到货日期作为默认生产日期。
        # 如果前端明确传了生产日期，则以前端日期为准。
        production_date = requested_item.production_date
        if production_date is None:
            production_date = expected_arrival_at.date()

        # 如果前端没有传到期日期，就使用“生产日期 + 目录默认保质期”计算。
        expiration_date = requested_item.expiration_date
        if expiration_date is None:
            if catalog_product.shelf_life_days is None:
                raise ValueError(
                    f"供应商商品目录ID {catalog_product.id} 未设置默认保质期，无法自动计算到期日期"
                )
            expiration_date = production_date + timedelta(days=catalog_product.shelf_life_days)

        # 生产日期由后端补齐时，也要再次检查两个日期的先后顺序。
        if expiration_date < production_date:
            raise ValueError(f"供应商商品目录ID {catalog_product.id} 的到期日期不能早于生产日期")

        # 正式商品可能尚未生成，因此 product_id 和商品编号快照允许为空。
        product_id = None
        product_no_snapshot = None
        if catalog_product.product is not None:
            product_id = catalog_product.product.id
            product_no_snapshot = catalog_product.product.product_no

        purchase_items.append(
            PurchaseItem(
                product_id=product_id,
                supplier_product_id=catalog_product.id,
                supplier_id=catalog_product.supplier_id,
                product_no_snapshot=product_no_snapshot,
                product_name_snapshot=catalog_product.name,
                supplier_name_snapshot=catalog_product.supplier.name,
                quantity=requested_item.quantity,
                unit_cost=catalog_product.unit_cost,
                subtotal=subtotal,
                production_date=production_date,
                expiration_date=expiration_date,
            )
        )

    # 将明细对象放入 relationship，SQLAlchemy 会在写入主表后自动填写 purchase_id。
    new_purchase = Purchase(
        purchase_no=purchase_no,
        department_id=purchase.department_id,
        created_by=created_by,
        received_by=None,
        ordered_at=ordered_at,
        expected_arrival_at=expected_arrival_at,
        arrived_at=None,
        total_amount=total_amount,
        status=PurchaseStatus.PENDING,
        items=purchase_items,
    )
    db.add(new_purchase)

    # flush 会执行 INSERT 并取得自动生成的 ID，但不会提交事务；commit 由 Service 控制。
    await db.flush()
    return new_purchase


# endregion


# region 自动签收到货
async def auto_receive_due_purchases(
    arrived_at: datetime,
    employee_id: int | None,
    db: AsyncSession,
) -> list[Purchase]:
    """签收所有达到预计到货时间的待到货进货单，并同步商品与批次库存。"""

    statement = (
        select(Purchase)
        .options(
            selectinload(Purchase.items)
            .selectinload(PurchaseItem.supplier_product)
            .selectinload(SupplierProduct.product),
            selectinload(Purchase.items)
            .selectinload(PurchaseItem.supplier_product)
            .selectinload(SupplierProduct.category),
        )
        .where(
            Purchase.status == PurchaseStatus.PENDING,
            Purchase.expected_arrival_at <= arrived_at,
        )
        .order_by(Purchase.id.asc())
        .with_for_update()
    )
    due_purchases = list((await db.scalars(statement)).all())

    product_number = int(
        await db.scalar(
            select(func.coalesce(func.max(cast(func.substr(Product.product_no, 2), Integer)), 0))
        )
        or 0
    )
    batch_number = int(
        await db.scalar(
            select(
                func.coalesce(func.max(cast(func.substr(InventoryBatch.batch_no, 12), Integer)), 0)
            ).where(InventoryBatch.batch_no.like(f"BAT{arrived_at:%Y%m%d}%"))
        )
        or 0
    )

    for purchase in due_purchases:
        # 模拟自动签收：选择该部门 ID 最小的一名启用正式员工作为签收人。
        receiver = await db.scalar(
            select(Employee)
            .where(
                Employee.department_id == purchase.department_id,
                Employee.role == EmployeeRole.REGULAR_EMPLOYEE,
                Employee.is_active.is_(True),
            )
            .order_by(Employee.id.asc())
            .limit(1)
        )
        if receiver is None:
            raise ValueError(f"部门ID {purchase.department_id} 没有可用的正式员工")

        for purchase_item in purchase.items:
            catalog_product = purchase_item.supplier_product
            product = catalog_product.product
            product_was_created = product is None
            if product is None:
                if catalog_product.category_id is None or catalog_product.category is None:
                    raise ValueError(f"供应商商品目录ID {catalog_product.id} 尚未设置商品分类")
                if catalog_product.category.department_id != purchase.department_id:
                    raise ValueError(f"供应商商品目录ID {catalog_product.id} 的分类不属于进货部门")
                product_number += 1
                product = Product(
                    product_no=f"P{product_number:05d}",
                    name=catalog_product.name,
                    supplier_product_id=catalog_product.id,
                    department_id=purchase.department_id,
                    category_id=catalog_product.category_id,
                    purchase_price=purchase_item.unit_cost,
                    sale_price=purchase_item.unit_cost * Decimal("2"),
                    stock_quantity=0,
                    expiry_warning_days=1,
                    status=ProductStatus.ON_SALE,
                )
                db.add(product)
                await db.flush()

            before_product_stock = product.stock_quantity
            before_purchase_price = product.purchase_price
            product.purchase_price = purchase_item.unit_cost
            product.stock_quantity += purchase_item.quantity
            purchase_item.product_id = product.id

            batch_number += 1
            inventory_batch = InventoryBatch(
                batch_no=f"BAT{arrived_at:%Y%m%d}{batch_number:04d}",
                product_id=product.id,
                purchase_item_id=purchase_item.id,
                production_date=purchase_item.production_date,
                expiration_date=purchase_item.expiration_date,
                initial_quantity=purchase_item.quantity,
                remaining_quantity=purchase_item.quantity,
                status=InventoryBatchStatus.AVAILABLE,
                arrived_at=arrived_at,
            )
            db.add(inventory_batch)
            await db.flush()

            # 首次到货会生成正式商品；后续到货则只增加已有商品的汇总库存。
            await create_operation_audit_log(
                employee_id=employee_id,
                module="product",
                action="create_from_purchase" if product_was_created else "increase_stock",
                target_type="product",
                target_id=product.id,
                before_data=None
                if product_was_created
                else {
                    "stock_quantity": before_product_stock,
                    "purchase_price": before_purchase_price,
                },
                after_data={
                    "product_no": product.product_no,
                    "stock_quantity": product.stock_quantity,
                    "purchase_price": product.purchase_price,
                },
                reason="进货单签收入库",
                db=db,
            )
            await create_operation_audit_log(
                employee_id=employee_id,
                module="inventory",
                action="create_batch",
                target_type="inventory_batch",
                target_id=inventory_batch.id,
                before_data=None,
                after_data={
                    "batch_no": inventory_batch.batch_no,
                    "product_id": inventory_batch.product_id,
                    "purchase_item_id": inventory_batch.purchase_item_id,
                    "remaining_quantity": inventory_batch.remaining_quantity,
                    "expiration_date": inventory_batch.expiration_date,
                    "status": inventory_batch.status,
                },
                reason="进货单签收入库",
                db=db,
            )

        before_purchase_status = purchase.status
        purchase.received_by = receiver.id
        purchase.arrived_at = arrived_at
        purchase.status = PurchaseStatus.ARRIVED

        await create_operation_audit_log(
            employee_id=employee_id,
            module="purchase",
            action="auto_receive" if employee_id is None else "manual_receive",
            target_type="purchase",
            target_id=purchase.id,
            before_data={"status": before_purchase_status},
            after_data={
                "status": purchase.status,
                "received_by": purchase.received_by,
                "arrived_at": purchase.arrived_at,
            },
            reason="系统按预计到货时间自动签收" if employee_id is None else "店长手动补执行签收",
            db=db,
        )

    await db.flush()
    return due_purchases


# endregion


__all__ = [
    "auto_receive_due_purchases",
    "create_purchase",
    "get_all_purchases",
    "get_purchase_by_id",
]
