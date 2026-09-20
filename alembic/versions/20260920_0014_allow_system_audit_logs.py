"""allow system operation audit logs

Revision ID: 20260920_0014
Revises: 20260920_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0014"
down_revision: str | Sequence[str] | None = "20260920_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """允许系统定时任务在没有登录员工时写入审计记录。"""

    op.alter_column(
        "operation_audit_log",
        "employee_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        existing_comment="操作员工ID",
        comment="操作员工ID；系统自动任务为空",
    )


def downgrade() -> None:
    """恢复操作员工必填；降级前移除没有员工的系统审计记录。"""

    op.execute(sa.text("DELETE FROM operation_audit_log WHERE employee_id IS NULL"))
    op.alter_column(
        "operation_audit_log",
        "employee_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        existing_comment="操作员工ID；系统自动任务为空",
        comment="操作员工ID",
    )
