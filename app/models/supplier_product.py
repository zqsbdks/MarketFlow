"""供应商商品目录 ORM 模型。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.purchase_item import PurchaseItem
    from app.models.supplier import Supplier


class SupplierProduct(TimestampMixin, Base):
    """保存供应商提供的商品、当前报价以及默认保质期。"""

    __tablename__ = "supplier_product"
    __table_args__ = (
        UniqueConstraint("supplier_id", "name", name="uq_supplier_product_supplier_name"),
        CheckConstraint("unit_cost >= 0", name="ck_supplier_product_unit_cost_non_negative"),
        CheckConstraint(
            "shelf_life_days IS NULL OR shelf_life_days > 0",
            name="ck_supplier_product_shelf_life_days_positive",
        ),
        {"mysql_charset": "utf8mb4", "comment": "供应商商品目录表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="供应商商品目录ID"
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("supplier.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="供应商ID",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="供应商商品名称")
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="当前默认进货单价"
    )
    shelf_life_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="默认保质期天数"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="是否仍在供应",
    )

    supplier: Mapped[Supplier] = relationship(back_populates="catalog_products")
    product: Mapped[Product | None] = relationship(back_populates="supplier_product", uselist=False)
    purchase_items: Mapped[list[PurchaseItem]] = relationship(back_populates="supplier_product")


__all__ = ["SupplierProduct"]
