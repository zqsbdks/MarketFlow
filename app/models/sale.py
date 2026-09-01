"""销售单 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.enums import SaleSource

if TYPE_CHECKING:
    from app.models.sale_item import SaleItem


class Sale(CreatedAtMixin, Base):
    """一次销售的金额、成本和毛利润汇总。"""

    __tablename__ = "sale"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_sale_total_amount_non_negative"),
        CheckConstraint("total_cost >= 0", name="ck_sale_total_cost_non_negative"),
        CheckConstraint(
            "gross_profit = total_amount - total_cost",
            name="ck_sale_gross_profit_matches_totals",
        ),
        UniqueConstraint("sale_no", name="uq_sale_sale_no"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sale_no: Mapped[str] = mapped_column(String(30), nullable=False)
    sold_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source: Mapped[SaleSource] = mapped_column(
        Enum(
            SaleSource,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="sale_source",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=30,
        ),
        nullable=False,
        default=SaleSource.DEMO_SEED,
        server_default=SaleSource.DEMO_SEED.value,
    )

    items: Mapped[list[SaleItem]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


__all__ = ["Sale"]
