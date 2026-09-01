"""员工账号 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import EmployeeRole

if TYPE_CHECKING:
    from app.models.department import Department


class Employee(TimestampMixin, Base):
    """登录账号和员工身份。"""

    __tablename__ = "employee"
    __table_args__ = (
        CheckConstraint(
            "role = 'store_manager' OR department_id IS NOT NULL",
            name="ck_employee_department_required",
        ),
        UniqueConstraint("employee_no", name="uq_employee_employee_no"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_no: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[EmployeeRole] = mapped_column(
        Enum(
            EmployeeRole,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="employee_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=30,
        ),
        nullable=False,
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    department: Mapped[Department | None] = relationship(back_populates="employees")


__all__ = ["Employee"]
