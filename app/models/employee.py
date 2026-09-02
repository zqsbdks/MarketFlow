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
            "role = '店长' OR department_id IS NOT NULL",
            name="ck_employee_department_required",
        ),
        CheckConstraint(
            "role IN ('店长', '正式员工', '契约工')",
            name="employee_role",
        ),
        UniqueConstraint("employee_no", name="uq_employee_employee_no"),
        {"mysql_charset": "utf8mb4", "comment": "员工表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="员工主键",
    )
    employee_no: Mapped[str] = mapped_column(String(20), nullable=False, comment="员工编号")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="员工姓名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    role: Mapped[EmployeeRole] = mapped_column(
        Enum(
            EmployeeRole,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="employee_role",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=30,
        ),
        nullable=False,
        comment="员工类型",
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("department.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="所属部门",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="账号是否启用",
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="是否必须修改密码",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最后登录时间",
    )

    department: Mapped[Department | None] = relationship(back_populates="employees")


__all__ = ["Employee"]
