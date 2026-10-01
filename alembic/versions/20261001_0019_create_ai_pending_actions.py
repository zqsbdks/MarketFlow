"""create AI pending action table

Revision ID: 20261001_0019
Revises: 20260927_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0019"
down_revision: str | Sequence[str] | None = "20260927_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# region 创建AI待确认操作表
def upgrade() -> None:
    """创建一次性待确认操作表，避免 AI 未经用户确认直接修改业务数据。"""

    op.create_table(
        "ai_pending_action",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="待确认操作主键"
        ),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="发起操作的员工ID"),
        sa.Column("provider", sa.String(20), nullable=False, comment="提出操作的模型供应商"),
        sa.Column("action_type", sa.String(50), nullable=False, comment="后端白名单操作类型"),
        sa.Column("arguments", sa.JSON(), nullable=False, comment="经过校验的操作参数"),
        sa.Column("summary", sa.String(255), nullable=False, comment="向用户展示的修改预览"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="确认操作状态",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="确认截止时间"),
        sa.Column("executed_at", sa.DateTime(), nullable=True, comment="实际执行完成时间"),
        sa.Column("failure_reason", sa.String(255), nullable=True, comment="执行失败原因"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'executed', 'cancelled', 'expired', 'failed')",
            name="ck_ai_pending_action_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            name="fk_ai_pending_action_employee_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        comment="AI待确认操作表",
    )
    op.create_index("ix_ai_pending_action_employee_id", "ai_pending_action", ["employee_id"])
    op.create_index("ix_ai_pending_action_action_type", "ai_pending_action", ["action_type"])
    op.create_index("ix_ai_pending_action_status", "ai_pending_action", ["status"])
    op.create_index("ix_ai_pending_action_expires_at", "ai_pending_action", ["expires_at"])


# endregion


# region 删除AI待确认操作表
def downgrade() -> None:
    """删除 AI 待确认操作表及其索引。"""

    op.drop_index("ix_ai_pending_action_expires_at", table_name="ai_pending_action")
    op.drop_index("ix_ai_pending_action_status", table_name="ai_pending_action")
    op.drop_index("ix_ai_pending_action_action_type", table_name="ai_pending_action")
    op.drop_index("ix_ai_pending_action_employee_id", table_name="ai_pending_action")
    op.drop_table("ai_pending_action")


# endregion
