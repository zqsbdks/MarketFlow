"""create inventory adjustment table

Revision ID: 20260917_0009
Revises: 20260917_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0009"
down_revision: str | Sequence[str] | None = "20260917_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建库存人工调整记录表。"""

    op.create_table(
        "inventory_adjustment",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="库存调整记录主键",
        ),
        sa.Column("inventory_batch_id", sa.BigInteger(), nullable=False, comment="库存批次ID"),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="商品ID"),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="操作员工ID"),
        sa.Column("before_quantity", sa.Integer(), nullable=False, comment="修改前数量"),
        sa.Column("after_quantity", sa.Integer(), nullable=False, comment="修改后数量"),
        sa.Column("quantity_difference", sa.Integer(), nullable=False, comment="数量差异"),
        sa.Column("reason", sa.String(length=255), nullable=True, comment="修改原因"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inventory_batch_id"], ["inventory_batch.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        comment="库存调整记录表",
    )
    op.create_index(
        op.f("ix_inventory_adjustment_inventory_batch_id"),
        "inventory_adjustment",
        ["inventory_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_adjustment_product_id"),
        "inventory_adjustment",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_adjustment_employee_id"),
        "inventory_adjustment",
        ["employee_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除库存人工调整记录表。"""

    op.drop_index(op.f("ix_inventory_adjustment_employee_id"), table_name="inventory_adjustment")
    op.drop_index(op.f("ix_inventory_adjustment_product_id"), table_name="inventory_adjustment")
    op.drop_index(
        op.f("ix_inventory_adjustment_inventory_batch_id"),
        table_name="inventory_adjustment",
    )
    op.drop_table("inventory_adjustment")
