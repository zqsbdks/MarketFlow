"""折扣规则适用范围 ORM 模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.enums import DiscountScopeType

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.department import Department
    from app.models.discount_rule import DiscountRule
    from app.models.product import Product


# region 折扣规则适用范围模型
class DiscountRuleScope(CreatedAtMixin, Base):
    """把一条折扣规则关联到某个商品、分类或部门。"""

    __tablename__ = "discount_rule_scope"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('product', 'category', 'department')",
            name="discount_rule_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'product' AND product_id IS NOT NULL "
            "AND category_id IS NULL AND department_id IS NULL) "
            "OR (scope_type = 'category' AND product_id IS NULL "
            "AND category_id IS NOT NULL AND department_id IS NULL) "
            "OR (scope_type = 'department' AND product_id IS NULL "
            "AND category_id IS NULL AND department_id IS NOT NULL)",
            name="ck_discount_rule_scope_single_target",
        ),
        UniqueConstraint(
            "discount_rule_id",
            "product_id",
            name="uq_discount_rule_scope_product",
        ),
        UniqueConstraint(
            "discount_rule_id",
            "category_id",
            name="uq_discount_rule_scope_category",
        ),
        UniqueConstraint(
            "discount_rule_id",
            "department_id",
            name="uq_discount_rule_scope_department",
        ),
        {"mysql_charset": "utf8mb4", "comment": "折扣规则适用范围表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="折扣规则范围主键",
    )
    discount_rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("discount_rule.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="折扣规则ID",
    )
    scope_type: Mapped[DiscountScopeType] = mapped_column(
        Enum(
            DiscountScopeType,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="discount_rule_scope_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        index=True,
        comment="适用范围类型",
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="适用商品ID",
    )
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("category.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="适用商品分类ID",
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="适用部门ID",
    )

    rule: Mapped[DiscountRule] = relationship(back_populates="scopes")
    product: Mapped[Product | None] = relationship(back_populates="discount_scopes")
    category: Mapped[Category | None] = relationship(back_populates="discount_scopes")
    department: Mapped[Department | None] = relationship(back_populates="discount_scopes")


# endregion


__all__ = ["DiscountRuleScope"]
