"""商品废弃单及批次扣减明细，保存当时的商品、成本和操作人快照。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.store_scoped import StoreScopedMixin


class InventoryDiscard(StoreScopedMixin, Base):
    __tablename__ = "inventory_discard"
    __table_args__ = (
        UniqueConstraint("store_id", "request_key", name="uq_discard_store_request"),
        CheckConstraint("quantity > 0 AND total_cost >= 0", name="ck_discard_amount"),
        CheckConstraint(
            "reason_code IN ('expired', 'damaged', 'spoiled', 'contaminated', 'other')",
            name="ck_discard_reason",
        ),
        {"mysql_charset": "utf8mb4", "comment": "商品废弃单"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="废弃单主键"
    )
    request_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="门店内幂等请求编号"
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id"), nullable=False, index=True, comment="商品ID"
    )
    product_no: Mapped[str] = mapped_column(String(30), nullable=False, comment="商品编号快照")
    product_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="商品名称快照")
    department_id: Mapped[int] = mapped_column(
        ForeignKey("department.id"), nullable=False, index=True, comment="所属部门ID"
    )
    department_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="部门名称快照"
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee.id"), nullable=True, comment="操作员工ID；自动任务为空"
    )
    employee_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="操作员工姓名快照"
    )
    reason_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="废弃原因编码")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="补充说明")
    requested_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_batch.id"), nullable=True, comment="指定批次ID；自动分配为空"
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="废弃总数量")
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, comment="按批次进货成本计算的损耗金额"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, comment="日本时间处理时间"
    )
    items: Mapped[list[InventoryDiscardItem]] = relationship(
        back_populates="discard", cascade="all, delete-orphan", lazy="selectin"
    )


class InventoryDiscardItem(StoreScopedMixin, Base):
    __tablename__ = "inventory_discard_item"
    __table_args__ = (
        UniqueConstraint("discard_id", "batch_id", name="uq_discard_batch"),
        CheckConstraint(
            "quantity > 0 AND unit_cost >= 0 AND total_cost >= 0", name="ck_discard_item_amount"
        ),
        {"mysql_charset": "utf8mb4", "comment": "废弃批次明细"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="废弃明细主键"
    )
    discard_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_discard.id"), nullable=False, index=True, comment="所属废弃单ID"
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_batch.id"), nullable=False, comment="库存批次ID"
    )
    batch_no: Mapped[str] = mapped_column(String(30), nullable=False, comment="库存批次号快照")
    expiration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="批次到期日期快照"
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="本批次废弃数量")
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="批次进货单价快照"
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, comment="本批次损耗金额"
    )
    before_quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="扣减前剩余数量")
    after_quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="扣减后剩余数量")
    discard: Mapped[InventoryDiscard] = relationship(back_populates="items")
