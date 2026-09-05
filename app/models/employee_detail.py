"""员工个人资料与雇佣状态 ORM 模型。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, Enum, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import EmployeeGender, EmploymentStatus

if TYPE_CHECKING:
    from app.models.employee import Employee


class EmployeeDetail(TimestampMixin, Base):
    """保存员工个人资料以及当前雇佣状态。"""

    __tablename__ = "employee_detail"
    __table_args__ = (
        CheckConstraint(
            "gender IN ('男', '女', '未填写')",
            name="employee_detail_gender",
        ),
        CheckConstraint(
            "employment_status IN ('在职', '休假', '离职', '解雇')",
            name="employee_detail_employment_status",
        ),
        CheckConstraint(
            "separation_date IS NULL OR separation_date >= hire_date",
            name="ck_employee_detail_separation_after_hire",
        ),
        {"mysql_charset": "utf8mb4", "comment": "员工详情表"},
    )

    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="CASCADE"),
        primary_key=True,
        comment="员工ID",
    )
    gender: Mapped[EmployeeGender] = mapped_column(
        Enum(
            EmployeeGender,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="employee_detail_gender",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=10,
        ),
        nullable=False,
        default=EmployeeGender.UNSPECIFIED,
        server_default=text("'未填写'"),
        comment="性别",
    )
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    hire_date: Mapped[date] = mapped_column(Date, nullable=False, comment="入职日期")
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="联系电话")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="居住地址")
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(
            EmploymentStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            name="employee_detail_employment_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=EmploymentStatus.EMPLOYED,
        server_default=text("'在职'"),
        comment="雇佣状态",
    )
    separation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="离职或解雇日期",
    )
    separation_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="离职或解雇原因",
    )

    employee: Mapped[Employee] = relationship(back_populates="detail")


__all__ = ["EmployeeDetail"]
