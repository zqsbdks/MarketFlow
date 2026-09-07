"""进货明细 ORM 模型。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.inventory_batch import InventoryBatch
    from app.models.product import Product
    from app.models.purchase import Purchase
    from app.models.supplier import Supplier
    from app.models.supplier_product import SupplierProduct


class PurchaseItem(CreatedAtMixin, Base):
    """保存进货单中的商品、供货商、数量、成本和保质期信息。"""

    # SQLAlchemy会把这个模型映射到MySQL中的purchase_item表。
    __tablename__ = "purchase_item"
    __table_args__ = (
        # 每条明细的进货数量必须大于0。
        CheckConstraint("quantity > 0", name="ck_purchase_item_quantity_positive"),
        # 本次进货单价不允许为负数。
        CheckConstraint("unit_cost >= 0", name="ck_purchase_item_unit_cost_non_negative"),
        # 明细小计必须等于进货单价乘以进货数量。
        CheckConstraint(
            "subtotal = unit_cost * quantity",
            name="ck_purchase_item_subtotal_matches",
        ),
        # 同时填写两个日期时，到期日期不能早于生产日期。
        CheckConstraint(
            "expiration_date IS NULL OR production_date IS NULL "
            "OR expiration_date >= production_date",
            name="ck_purchase_item_expiration_after_production",
        ),
        {"mysql_charset": "utf8mb4", "comment": "进货明细表"},
    )

    # 进货明细ID是数据库自动递增的主键。
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="进货明细主键"
    )
    # purchase_id表示这条明细属于哪一张进货单。
    purchase_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("purchase.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属进货单ID",
    )
    # product_id表示本次订购的是哪个商品。
    product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="签收后生成或匹配的正式商品ID",
    )
    # 下单时商品可能尚未进入正式商品表，因此先关联供应商商品目录。
    supplier_product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "supplier_product.id",
            name="fk_purchase_item_supplier_product_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="供应商商品目录ID",
    )
    # supplier_id表示这批商品由哪个供货商提供。
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("supplier.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="供货商ID",
    )
    # 商品编号快照用于保证商品以后改编号时，历史进货单仍显示原编号。
    product_no_snapshot: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="下单时商品编号快照",
    )
    # 商品名称快照用于保证商品以后改名时，历史进货单仍显示原名称。
    product_name_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="下单时商品名称快照",
    )
    # 供货商名称快照用于保证供货商以后改名时，历史进货单仍保持原始记录。
    supplier_name_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="下单时供货商名称快照",
    )
    # quantity保存本次向供货商订购的商品件数。
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="进货数量")
    # unit_cost保存本次实际进货单价，不受商品以后修改默认进货价的影响。
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="本次进货单价",
    )
    # subtotal由后端按照quantity乘以unit_cost计算，不直接信任前端金额。
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="进货金额小计",
    )
    # production_date保存包装标注的生产日期；没有明确日期的商品可以为空。
    production_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="生产日期",
    )
    # expiration_date保存包装标注或后端计算出的到期日期。
    expiration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="到期日期",
    )

    # purchase让代码可以从明细读取所属进货单。
    purchase: Mapped[Purchase] = relationship(back_populates="items")
    # product让代码可以从明细读取当前商品资料。
    product: Mapped[Product | None] = relationship(back_populates="purchase_items")
    # supplier_product保存下单时选择的供应商目录商品。
    supplier_product: Mapped[SupplierProduct] = relationship(back_populates="purchase_items")
    # supplier让代码可以从明细读取当前供货商资料。
    supplier: Mapped[Supplier] = relationship(back_populates="purchase_items")
    # 第一版每条进货明细最多生成一个库存批次，尚未到货时为None。
    inventory_batch: Mapped[InventoryBatch | None] = relationship(
        back_populates="purchase_item",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


__all__ = ["PurchaseItem"]
