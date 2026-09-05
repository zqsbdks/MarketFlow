"""create employee detail table

Revision ID: 20260905_0005
Revises: 20260902_0004
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0005"
down_revision: str | Sequence[str] | None = "20260902_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建员工详情表，并为现有员工补充默认详情记录。"""

    op.create_table(
        "employee_detail",
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="员工ID"),
        sa.Column(
            "gender",
            sa.String(length=10),
            server_default=sa.text("'未填写'"),
            nullable=False,
            comment="性别",
        ),
        sa.Column("birth_date", sa.Date(), nullable=True, comment="出生日期"),
        sa.Column("hire_date", sa.Date(), nullable=False, comment="入职日期"),
        sa.Column("phone", sa.String(length=30), nullable=True, comment="联系电话"),
        sa.Column("address", sa.String(length=255), nullable=True, comment="居住地址"),
        sa.Column(
            "employment_status",
            sa.String(length=20),
            server_default=sa.text("'在职'"),
            nullable=False,
            comment="雇佣状态",
        ),
        sa.Column("separation_date", sa.Date(), nullable=True, comment="离职或解雇日期"),
        sa.Column(
            "separation_reason",
            sa.String(length=255),
            nullable=True,
            comment="离职或解雇原因",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
            comment="更新时间",
        ),
        sa.CheckConstraint(
            "gender IN ('男', '女', '未填写')",
            name="employee_detail_gender",
        ),
        sa.CheckConstraint(
            "employment_status IN ('在职', '休假', '离职', '解雇')",
            name="employee_detail_employment_status",
        ),
        sa.CheckConstraint(
            "separation_date IS NULL OR separation_date >= hire_date",
            name="ck_employee_detail_separation_after_hire",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            name="fk_employee_detail_employee_id_employee",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("employee_id"),
        comment="员工详情表",
        mysql_charset="utf8mb4",
    )

    # 账号创建时间暂作为历史员工的入职日期，之后可由店长在详情接口中修正。
    op.execute(
        sa.text(
            """
            INSERT INTO employee_detail (employee_id, hire_date)
            SELECT id, DATE(created_at)
            FROM employee
            """
        )
    )


def downgrade() -> None:
    """删除员工详情表。"""

    op.drop_table("employee_detail")


__all__ = ["downgrade", "upgrade"]
