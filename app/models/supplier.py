"""供货商 ORM 模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.purchase_item import PurchaseItem
    from app.models.supplier_product import SupplierProduct


class Supplier(TimestampMixin, Base):
    """保存供货商的基础资料以及当前合作状态。"""

    # SQLAlchemy会把这个模型映射到MySQL中的supplier表。
    __tablename__ = "supplier"
    # 编号和名称都不能重复；表使用utf8mb4并附加中文说明。
    __table_args__ = (
        UniqueConstraint("supplier_no", name="uq_supplier_supplier_no"),
        UniqueConstraint("name", name="uq_supplier_name"),
        {"mysql_charset": "utf8mb4", "comment": "供货商表"},
    )

    # 供货商ID是数据库自动递增的主键。
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="供货商主键",
    )
    # supplier_no保存系统内部使用的唯一编号，例如SUP00001。
    supplier_no: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="供货商编号",
    )
    # name保存供货商对外使用的名称。
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="供货商名称")
    # 联系人、电话和地址不是建立供货商记录的必要条件，因此允许为空。
    contact_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="联系人姓名",
    )
    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="联系电话",
    )
    address: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="供货商地址",
    )
    # 停止合作时把is_active改为False，不删除历史供货商记录。
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="是否继续合作",
    )

    # 一个供货商可以出现在多条进货明细中。
    purchase_items: Mapped[list[PurchaseItem]] = relationship(back_populates="supplier")
    # catalog_products保存该供应商预先维护的商品目录和当前报价。
    catalog_products: Mapped[list[SupplierProduct]] = relationship(
        back_populates="supplier",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


__all__ = ["Supplier"]
