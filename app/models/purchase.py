"""进货单 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import PurchaseStatus

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.employee import Employee
    from app.models.purchase_item import PurchaseItem


class Purchase(TimestampMixin, Base):
    """保存一次部门进货的汇总信息、到货时间和签收员工。"""

    # SQLAlchemy会把这个模型映射到MySQL中的purchase表。
    __tablename__ = "purchase"
    __table_args__ = (
        # 进货总金额不允许出现负数。
        CheckConstraint("total_amount >= 0", name="ck_purchase_total_amount_non_negative"),
        # 预计到货时间必须晚于下单时间。
        CheckConstraint(
            "expected_arrival_at > ordered_at",
            name="ck_purchase_expected_arrival_after_order",
        ),
        # 状态只允许使用当前模拟系统支持的待到货和已到货。
        CheckConstraint("status IN ('pending', 'arrived')", name="purchase_status"),
        # 待到货时不能有签收数据；已到货时必须同时记录签收人和到货时间。
        CheckConstraint(
            "(status = 'pending' AND received_by IS NULL AND arrived_at IS NULL) "
            "OR (status = 'arrived' AND received_by IS NOT NULL AND arrived_at IS NOT NULL)",
            name="ck_purchase_arrival_fields_match_status",
        ),
        {"mysql_charset": "utf8mb4", "comment": "进货单表"},
    )

    # 进货单ID是数据库自动递增的主键。
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="进货单主键"
    )
    # purchase_no保存前端展示和人工查询使用的唯一进货单号。
    purchase_no: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
        comment="进货单号",
    )
    # 一张进货单只属于一个部门，明细商品也必须属于这个部门。
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="进货所属部门ID",
    )
    # created_by指向创建这张进货单的员工。
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="创建进货单的员工ID",
    )
    # received_by在待到货阶段为空，两天后自动写入对应部门的一名正式员工ID。
    received_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="签收进货单的员工ID",
    )
    # ordered_at记录下单时间，是计算预计到货时间的起点。
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, comment="下单时间"
    )
    # expected_arrival_at通常等于ordered_at加48小时，后台任务根据它判断是否到货。
    expected_arrival_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="预计到货时间",
    )
    # arrived_at在自动入库完成后保存实际处理时间，待到货时为空。
    arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="实际到货入库时间",
    )
    # total_amount等于这张进货单所有明细subtotal之和，由后端计算。
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="进货总金额",
    )
    # status使用PurchaseStatus枚举，数据库中实际保存pending或arrived。
    status: Mapped[PurchaseStatus] = mapped_column(
        Enum(
            PurchaseStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="purchase_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=PurchaseStatus.PENDING,
        server_default=PurchaseStatus.PENDING.value,
        comment="进货单状态",
    )

    # department让代码可以通过purchase.department读取所属部门对象。
    department: Mapped[Department] = relationship(back_populates="purchases")
    # created_by_employee表示创建员工，foreign_keys用于区分同表中的两个员工外键。
    created_by_employee: Mapped[Employee] = relationship(
        back_populates="created_purchases",
        foreign_keys=[created_by],
    )
    # received_by_employee表示签收员工；待到货时该关系为None。
    received_by_employee: Mapped[Employee | None] = relationship(
        back_populates="received_purchases",
        foreign_keys=[received_by],
    )
    # items保存进货单的全部商品明细；删除进货单对象时同步删除尚未提交的明细对象。
    items: Mapped[list[PurchaseItem]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


__all__ = ["Purchase"]
