"""折扣规则 ORM 模型。"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import DiscountScheduleType, DiscountType

if TYPE_CHECKING:
    from app.models.discount_rule_scope import DiscountRuleScope
    from app.models.employee import Employee


# region 折扣规则模型
class DiscountRule(TimestampMixin, Base):
    """保存实际参与商品展示、扫码试算和销售结算的折扣规则。"""

    __tablename__ = "discount_rule"
    __table_args__ = (
        UniqueConstraint("name", name="uq_discount_rule_name"),
        CheckConstraint(
            "discount_type IN ('percentage', 'amount_off', 'fixed_price')",
            name="discount_rule_type",
        ),
        CheckConstraint(
            "schedule_type IN ('once', 'daily', 'weekly')",
            name="discount_rule_schedule_type",
        ),
        CheckConstraint(
            "discount_value > 0 AND (discount_type <> 'percentage' OR discount_value < 1)",
            name="ck_discount_rule_value",
        ),
        CheckConstraint(
            "(schedule_type = 'once' AND starts_at IS NOT NULL AND ends_at IS NOT NULL) "
            "OR (schedule_type IN ('daily', 'weekly') "
            "AND daily_start_time IS NOT NULL AND daily_end_time IS NOT NULL)",
            name="ck_discount_rule_schedule_fields",
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
            name="ck_discount_rule_datetime_range",
        ),
        CheckConstraint(
            "daily_start_time IS NULL OR daily_end_time IS NULL "
            "OR daily_start_time < daily_end_time",
            name="ck_discount_rule_daily_time_range",
        ),
        CheckConstraint(
            "start_stock_threshold IS NULL OR start_stock_threshold >= 0",
            name="ck_discount_rule_start_stock_non_negative",
        ),
        CheckConstraint(
            "end_stock_threshold IS NULL OR end_stock_threshold >= 0",
            name="ck_discount_rule_end_stock_non_negative",
        ),
        CheckConstraint(
            "start_stock_threshold IS NULL OR end_stock_threshold IS NULL "
            "OR end_stock_threshold < start_stock_threshold",
            name="ck_discount_rule_stock_range",
        ),
        Index("ix_discount_rule_active_schedule", "is_active", "schedule_type"),
        {"mysql_charset": "utf8mb4", "comment": "折扣规则表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="折扣规则主键",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="折扣规则名称")
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(
            DiscountType,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="discount_rule_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        comment="折扣计算方式",
    )
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="折扣比例、立减金额或固定价格",
    )
    schedule_type: Mapped[DiscountScheduleType] = mapped_column(
        Enum(
            DiscountScheduleType,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="discount_rule_schedule_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        comment="折扣执行周期",
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        comment="单次活动开始时间",
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        comment="单次活动结束时间",
    )
    daily_start_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
        comment="每日循环开始时间",
    )
    daily_end_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
        comment="每日循环结束时间",
    )
    weekdays: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="每周执行日列表；1至7表示周一至周日",
    )
    start_stock_threshold: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="可售库存小于等于该值时开始打折",
    )
    end_stock_threshold: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="可售库存小于等于该值时停止打折",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="折扣规则是否启用",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="创建员工ID",
    )

    creator: Mapped[Employee] = relationship(back_populates="created_discount_rules")
    scopes: Mapped[list[DiscountRuleScope]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        single_parent=True,
    )


# endregion


__all__ = ["DiscountRule"]
