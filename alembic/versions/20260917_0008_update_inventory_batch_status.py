"""replace discarded inventory status with near expiry

Revision ID: 20260917_0008
Revises: 20260913_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0008"
down_revision: str | Sequence[str] | None = "20260913_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """删除报废状态，增加临期状态并更新数据库检查约束。"""

    # 先删除旧约束，历史 discarded 数据才能被转换为新的合法状态。
    op.drop_constraint("inventory_batch_status", "inventory_batch", type_="check")
    op.execute(
        sa.text("UPDATE inventory_batch SET status = 'available' WHERE status = 'discarded'")
    )
    op.create_check_constraint(
        "inventory_batch_status",
        "inventory_batch",
        "status IN ('available', 'near_expiry', 'sold_out')",
    )


def downgrade() -> None:
    """恢复报废状态并移除临期状态。"""

    op.drop_constraint("inventory_batch_status", "inventory_batch", type_="check")
    op.execute(
        sa.text("UPDATE inventory_batch SET status = 'available' WHERE status = 'near_expiry'")
    )
    op.create_check_constraint(
        "inventory_batch_status",
        "inventory_batch",
        "status IN ('available', 'sold_out', 'discarded')",
    )
