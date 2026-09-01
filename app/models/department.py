"""部门 ORM 模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.employee import Employee
    from app.models.product import Product
    from app.models.sale_item import SaleItem


class Department(TimestampMixin, Base):
    """门店固定部门。"""

    __tablename__ = "department"
    __table_args__ = (
        UniqueConstraint("code", name="uq_department_code"),
        UniqueConstraint("name", name="uq_department_name"),
        {"mysql_charset": "utf8mb4", "comment": "部门表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="部门主键",
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, comment="部门代码")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="部门名称")
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="是否启用",
    )

    employees: Mapped[list[Employee]] = relationship(back_populates="department")
    categories: Mapped[list[Category]] = relationship(back_populates="department")
    products: Mapped[list[Product]] = relationship(
        back_populates="department",
        overlaps="category,products",
    )
    sale_items: Mapped[list[SaleItem]] = relationship(back_populates="department")


__all__ = ["Department"]
