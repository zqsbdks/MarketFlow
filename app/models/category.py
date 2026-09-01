"""商品分类 ORM 模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.product import Product


class Category(TimestampMixin, Base):
    """部门内唯一命名的商品分类。"""

    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("department_id", "name", name="uq_category_department_name"),
        # 为商品的复合外键提供候选键，确保分类和商品属于同一部门。
        UniqueConstraint("id", "department_id", name="uq_category_id_department_id"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    department: Mapped[Department] = relationship(back_populates="categories")
    products: Mapped[list[Product]] = relationship(
        back_populates="category",
        overlaps="department,products",
    )


__all__ = ["Category"]
