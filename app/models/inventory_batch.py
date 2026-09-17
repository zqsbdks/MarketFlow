"""库存批次 ORM 模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import InventoryBatchStatus

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.purchase_item import PurchaseItem


class InventoryBatch(TimestampMixin, Base):
    """保存每条已到货进货明细对应的批次库存及到期日期。"""

    # SQLAlchemy会把这个模型映射到MySQL中的inventory_batch表。
    __tablename__ = "inventory_batch"
    __table_args__ = (
        # 到货时的初始数量必须大于0。
        CheckConstraint("initial_quantity > 0", name="ck_inventory_batch_initial_positive"),
        # 当前剩余数量不能小于0，也不能超过最初到货数量。
        CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= initial_quantity",
            name="ck_inventory_batch_remaining_range",
        ),
        # 同时填写两个日期时，到期日期不能早于生产日期。
        CheckConstraint(
            "expiration_date IS NULL OR production_date IS NULL "
            "OR expiration_date >= production_date",
            name="ck_inventory_batch_expiration_after_production",
        ),
        # 批次状态只允许使用可用、临期和售完三个自动状态。
        CheckConstraint(
            "status IN ('available', 'near_expiry', 'sold_out')",
            name="inventory_batch_status",
        ),
        {"mysql_charset": "utf8mb4", "comment": "库存批次表"},
    )

    # 库存批次ID是数据库自动递增的主键。
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="库存批次主键"
    )
    # batch_no保存前端展示和人工查询使用的唯一批次号。
    batch_no: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
        comment="库存批次号",
    )
    # product_id表示这批库存属于哪个商品。
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="商品ID",
    )
    # purchase_item_id记录批次来源，并用unique保证一条明细不会重复生成批次。
    purchase_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("purchase_item.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        comment="来源进货明细ID",
    )
    # 生产日期来自进货明细；没有明确日期时可以为空。
    production_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="生产日期",
    )
    # 到期日期用于动态判断正常、临期或过期状态。
    expiration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="到期日期",
    )
    # initial_quantity保存到货时的数量，入库后不随销售改变。
    initial_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="到货初始数量",
    )
    # remaining_quantity保存这批库存当前还剩多少件。
    remaining_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="当前剩余数量",
    )
    # status由剩余数量、到期日期和商品临期提醒天数自动维护。
    status: Mapped[InventoryBatchStatus] = mapped_column(
        Enum(
            InventoryBatchStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="inventory_batch_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=InventoryBatchStatus.AVAILABLE,
        server_default=InventoryBatchStatus.AVAILABLE.value,
        comment="库存批次状态",
    )
    # arrived_at保存系统自动签收并把本批次加入库存的时间。
    arrived_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="批次到货入库时间",
    )

    # product让代码可以从库存批次读取对应商品。
    product: Mapped[Product] = relationship(back_populates="inventory_batches")
    # purchase_item让代码可以追溯该批次来源于哪条进货明细。
    purchase_item: Mapped[PurchaseItem] = relationship(back_populates="inventory_batch")


@event.listens_for(InventoryBatch, "before_insert")
@event.listens_for(InventoryBatch, "before_update")
def _sync_sold_out_status(_mapper, _connection, batch: InventoryBatch) -> None:
    """批次写入数据库前，根据剩余数量自动同步售完状态。"""

    # 售完状态优先级最高；只要剩余数量为 0，就强制改为 sold_out。
    if batch.remaining_quantity == 0:
        batch.status = InventoryBatchStatus.SOLD_OUT
    # 如果库存后来由 0 调整为正数，先恢复为可用；每日任务会继续判断是否临期。
    elif batch.status == InventoryBatchStatus.SOLD_OUT:
        batch.status = InventoryBatchStatus.AVAILABLE


__all__ = ["InventoryBatch"]
