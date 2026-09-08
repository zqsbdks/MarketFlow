"""商品 ORM 模型。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ProductStatus

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.department import Department
    from app.models.inventory_batch import InventoryBatch
    from app.models.purchase_item import PurchaseItem
    from app.models.sale_item import SaleItem
    from app.models.supplier_product import SupplierProduct


class Product(TimestampMixin, Base):
    """商品主数据及第一版的当前库存数量。"""

    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("purchase_price >= 0", name="ck_product_purchase_price_non_negative"),
        CheckConstraint("sale_price >= 0", name="ck_product_sale_price_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="ck_product_stock_quantity_non_negative"),
        CheckConstraint(
            "expiry_warning_days IS NULL OR expiry_warning_days >= 0",
            name="ck_product_expiry_warning_days_non_negative",
        ),
        CheckConstraint("status IN ('on_sale', 'stopped')", name="product_status"),
        UniqueConstraint("product_no", name="uq_product_product_no"),
        ForeignKeyConstraint(
            ["category_id", "department_id"],
            ["category.id", "category.department_id"],
            name="fk_product_category_department",
            ondelete="RESTRICT",
        ),
        {"mysql_charset": "utf8mb4", "comment": "商品表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="商品主键",
    )
    product_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="商品编号")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称")
    # 一个正式商品唯一来源于一个供应商商品目录项。
    supplier_product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "supplier_product.id",
            name="fk_product_supplier_product_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
        index=True,
        comment="来源供应商商品目录ID",
    )
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="所属部门",
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属分类",
    )
    purchase_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="进货价",
    )
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="销售价",
    )
    stock_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="当前库存数量",
    )
    # expiry_warning_days表示到期前多少天开始显示为临期商品。
    expiry_warning_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="临期提前提醒天数",
    )
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="product_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=ProductStatus.ON_SALE,
        server_default=ProductStatus.ON_SALE.value,
        comment="商品销售状态",
    )

    department: Mapped[Department] = relationship(
        back_populates="products",
        overlaps="category,products",
    )
    category: Mapped[Category] = relationship(
        back_populates="products",
        overlaps="department,products",
    )
    sale_items: Mapped[list[SaleItem]] = relationship(back_populates="product")
    # purchase_items保存该商品的所有历史进货明细。
    purchase_items: Mapped[list[PurchaseItem]] = relationship(back_populates="product")
    # inventory_batches保存该商品每次到货后生成的批次库存。
    inventory_batches: Mapped[list[InventoryBatch]] = relationship(back_populates="product")
    # supplier_product用于取得该商品的来源供应商、目录报价和默认保质期。
    supplier_product: Mapped[SupplierProduct] = relationship(back_populates="product")


__all__ = ["Product"]
