"""replace inventory adjustment with operation audit log

Revision ID: 20260917_0010
Revises: 20260917_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0010"
down_revision: str | Sequence[str] | None = "20260917_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """建立统一审计表，迁移已有库存调整历史后删除专用表。"""

    op.create_table(
        "operation_audit_log",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="审计记录主键"
        ),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="操作员工ID"),
        sa.Column("module", sa.String(50), nullable=False, comment="业务模块"),
        sa.Column("action", sa.String(50), nullable=False, comment="操作类型"),
        sa.Column("target_type", sa.String(50), nullable=False, comment="目标类型"),
        sa.Column("target_id", sa.BigInteger(), nullable=False, comment="目标记录ID"),
        sa.Column("before_data", sa.JSON(), nullable=True, comment="修改前数据"),
        sa.Column("after_data", sa.JSON(), nullable=True, comment="修改后数据"),
        sa.Column("reason", sa.String(255), nullable=True, comment="修改理由"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        comment="操作审计记录表",
    )
    for column in ("employee_id", "module", "target_type", "target_id"):
        op.create_index(op.f(f"ix_operation_audit_log_{column}"), "operation_audit_log", [column])

    # 0009 版本若已经记录过库存调整，先转换到统一审计格式，避免历史丢失。
    op.execute(
        sa.text(
            "INSERT INTO operation_audit_log "
            "(employee_id, module, action, target_type, target_id, "
            "before_data, after_data, reason, created_at) "
            "SELECT employee_id, 'inventory', 'update_quantity', "
            "'inventory_batch', inventory_batch_id, "
            "JSON_OBJECT('remaining_quantity', before_quantity), "
            "JSON_OBJECT('remaining_quantity', after_quantity), reason, created_at "
            "FROM inventory_adjustment"
        )
    )
    op.drop_table("inventory_adjustment")


def downgrade() -> None:
    """恢复专用库存调整表并删除统一审计表。"""

    op.create_table(
        "inventory_adjustment",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="库存调整记录主键"
        ),
        sa.Column("inventory_batch_id", sa.BigInteger(), nullable=False, comment="库存批次ID"),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="商品ID"),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="操作员工ID"),
        sa.Column("before_quantity", sa.Integer(), nullable=False, comment="修改前数量"),
        sa.Column("after_quantity", sa.Integer(), nullable=False, comment="修改后数量"),
        sa.Column("quantity_difference", sa.Integer(), nullable=False, comment="数量差异"),
        sa.Column("reason", sa.String(255), nullable=True, comment="修改原因"),
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
    for column in ("inventory_batch_id", "product_id", "employee_id"):
        op.create_index(op.f(f"ix_inventory_adjustment_{column}"), "inventory_adjustment", [column])

    for column in ("employee_id", "module", "target_type", "target_id"):
        op.drop_index(op.f(f"ix_operation_audit_log_{column}"), table_name="operation_audit_log")
    op.drop_table("operation_audit_log")
