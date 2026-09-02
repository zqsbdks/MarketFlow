"""localize employee role values

Revision ID: 20260902_0004
Revises: 20260901_0003
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0004"
down_revision: str | Sequence[str] | None = "20260901_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将员工角色存储值及相关检查约束由英文改为中文。"""

    op.drop_constraint("employee_role", "employee", type_="check")
    op.drop_constraint(
        "ck_employee_department_required",
        "employee",
        type_="check",
    )

    op.execute(
        sa.text(
            """
            UPDATE employee
            SET role = CASE role
                WHEN 'store_manager' THEN '店长'
                WHEN 'regular_employee' THEN '正式员工'
                WHEN 'contract_worker' THEN '契约工'
                ELSE role
            END
            """
        )
    )

    op.create_check_constraint(
        "employee_role",
        "employee",
        "role IN ('店长', '正式员工', '契约工')",
    )
    op.create_check_constraint(
        "ck_employee_department_required",
        "employee",
        "role = '店长' OR department_id IS NOT NULL",
    )


def downgrade() -> None:
    """恢复员工角色的英文存储值及检查约束。"""

    op.drop_constraint("employee_role", "employee", type_="check")
    op.drop_constraint(
        "ck_employee_department_required",
        "employee",
        type_="check",
    )

    op.execute(
        sa.text(
            """
            UPDATE employee
            SET role = CASE role
                WHEN '店长' THEN 'store_manager'
                WHEN '正式员工' THEN 'regular_employee'
                WHEN '契约工' THEN 'contract_worker'
                ELSE role
            END
            """
        )
    )

    op.create_check_constraint(
        "employee_role",
        "employee",
        "role IN ('store_manager', 'regular_employee', 'contract_worker')",
    )
    op.create_check_constraint(
        "ck_employee_department_required",
        "employee",
        "role = 'store_manager' OR department_id IS NOT NULL",
    )


__all__ = ["downgrade", "upgrade"]
