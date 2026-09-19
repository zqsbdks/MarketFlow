"""add expired inventory batch status

Revision ID: 20260920_0012
Revises: 20260917_0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260920_0012"
down_revision: str | Sequence[str] | None = "20260917_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """允许库存批次使用 expired（已过期）状态。"""

    op.drop_constraint("inventory_batch_status", "inventory_batch", type_="check")
    op.create_check_constraint(
        "inventory_batch_status",
        "inventory_batch",
        "status IN ('available', 'near_expiry', 'expired', 'sold_out')",
    )


def downgrade() -> None:
    """移除 expired 状态，并将已有过期批次恢复为临期状态。"""

    # 回滚前先转换已有数据，否则旧检查约束会拒绝 expired 值。
    op.drop_constraint("inventory_batch_status", "inventory_batch", type_="check")
    op.execute("UPDATE inventory_batch SET status = 'near_expiry' WHERE status = 'expired'")
    op.create_check_constraint(
        "inventory_batch_status",
        "inventory_batch",
        "status IN ('available', 'near_expiry', 'sold_out')",
    )
