"""销售明细 ORM 模型。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.product import Product
    from app.models.sale import Sale


class SaleItem(Base):
    """保留成交时商品信息和价格成本快照的销售行。"""

    __tablename__ = "sale_item"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sale_item_unit_price_non_negative"),
        CheckConstraint("unit_cost >= 0", name="ck_sale_item_unit_cost_non_negative"),
        CheckConstraint(
            "subtotal = unit_price * quantity",
            name="ck_sale_item_subtotal_matches",
        ),
        CheckConstraint(
            "cost_subtotal = unit_cost * quantity",
            name="ck_sale_item_cost_subtotal_matches",
        ),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sale.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_no_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="sale_items")
    department: Mapped[Department] = relationship(back_populates="sale_items")


__all__ = ["SaleItem"]
