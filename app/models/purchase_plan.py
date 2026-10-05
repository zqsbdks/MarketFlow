"""截止前可修改、截止后生成一张进货单的每日订货计划。"""

from datetime import date

from sqlalchemy import JSON, BigInteger, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.store_scoped import StoreScopedMixin


class PurchasePlan(StoreScopedMixin, TimestampMixin, Base):
    """门店/部门/到货日唯一的计划头，分开保存人工覆盖与自动建议。

    两类JSON字典以供应目录ID字符串为键。0是明确人工取消，缺少键表示使用自动量。
    purchase_id只在订单成功创建的同一事务内填写，后台重试据此避免重复生成。
    """

    __tablename__ = "purchase_plan"
    __table_args__ = (
        UniqueConstraint("store_id", "department_id", "arrival_date", name="uq_purchase_plan_day"),
        {"mysql_charset": "utf8mb4", "comment": "每日自动提交订货计划"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="计划主键"
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("department.id"), nullable=False, comment="订货部门"
    )
    arrival_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="计划到货日期"
    )
    quantities: Mapped[dict[str, int]] = mapped_column(
        JSON, nullable=False, default=dict, comment="商品目录ID对应计划数量"
    )
    automatic_quantities: Mapped[dict[str, int]] = mapped_column(
        JSON, nullable=False, default=dict, comment="自动计算的订货数量"
    )
    updated_by: Mapped[int] = mapped_column(
        ForeignKey("employee.id"), nullable=False, comment="最后修改员工"
    )
    purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase.id"), nullable=True, unique=True, comment="自动生成的进货单ID"
    )
