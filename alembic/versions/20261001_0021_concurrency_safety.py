"""add concurrency safety fields and business sequences

Revision ID: 20261001_0021
Revises: 20261001_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0021"
down_revision: str | Sequence[str] | None = "20261001_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建编号计数器，并为商品和折扣规则增加乐观锁版本号。"""

    # MySQL 的 DDL 不参与事务；以下存在性检查也能安全恢复一次中途失败的迁移。
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "business_sequence" not in inspector.get_table_names():
        op.create_table(
            "business_sequence",
            sa.Column("sequence_key", sa.String(64), nullable=False, comment="业务计数器键"),
            sa.Column("current_value", sa.BigInteger(), nullable=False, comment="最后已分配流水号"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("sequence_key"),
            mysql_charset="utf8mb4",
            comment="业务编号计数器表",
        )

    def column_names(table_name: str) -> set[str]:
        return {column["name"] for column in sa.inspect(connection).get_columns(table_name)}

    if "version" not in column_names("product"):
        op.add_column(
            "product",
            sa.Column(
                "version", sa.Integer(), server_default="1", nullable=False, comment="乐观锁版本号"
            ),
        )
    if "version" not in column_names("discount_rule"):
        op.add_column(
            "discount_rule",
            sa.Column(
                "version", sa.Integer(), server_default="1", nullable=False, comment="乐观锁版本号"
            ),
        )
    if "client_request_id" not in column_names("sale"):
        op.add_column(
            "sale",
            sa.Column(
                "client_request_id", sa.String(36), nullable=True, comment="客户端幂等请求ID"
            ),
        )
    sale_unique_names = {
        item["name"] for item in sa.inspect(connection).get_unique_constraints("sale")
    }
    if "uq_sale_client_request_id" not in sale_unique_names:
        op.create_unique_constraint("uq_sale_client_request_id", "sale", ["client_request_id"])
    if "client_request_id" not in column_names("purchase"):
        op.add_column(
            "purchase",
            sa.Column(
                "client_request_id", sa.String(36), nullable=True, comment="客户端幂等请求ID"
            ),
        )
    purchase_unique_names = {
        item["name"] for item in sa.inspect(connection).get_unique_constraints("purchase")
    }
    if "uq_purchase_client_request_id" not in purchase_unique_names:
        op.create_unique_constraint(
            "uq_purchase_client_request_id", "purchase", ["client_request_id"]
        )

    # 从既有编号初始化计数器，升级后继续递增，不会重新从1开始造成唯一键冲突。
    op.execute(
        sa.text(
            "INSERT IGNORE INTO business_sequence (sequence_key, current_value) "
            "SELECT 'supplier', COALESCE(MAX(CAST(SUBSTRING(supplier_no, 4) AS UNSIGNED)), 0) "
            "FROM supplier"
        )
    )
    op.execute(
        sa.text(
            "INSERT IGNORE INTO business_sequence (sequence_key, current_value) "
            "SELECT CONCAT('purchase:', SUBSTRING(purchase_no, 4, 8)), "
            "MAX(CAST(SUBSTRING(purchase_no, 12) AS UNSIGNED)) FROM purchase "
            "GROUP BY CONCAT('purchase:', SUBSTRING(purchase_no, 4, 8))"
        )
    )
    op.execute(
        sa.text(
            "INSERT IGNORE INTO business_sequence (sequence_key, current_value) "
            "SELECT CONCAT('sale:', SUBSTRING(sale_no, 2, 8)), "
            "MAX(CAST(SUBSTRING(sale_no, 10) AS UNSIGNED)) FROM sale "
            "GROUP BY CONCAT('sale:', SUBSTRING(sale_no, 2, 8))"
        )
    )


def downgrade() -> None:
    """移除并发安全结构。"""

    op.drop_constraint("uq_purchase_client_request_id", "purchase", type_="unique")
    op.drop_column("purchase", "client_request_id")
    op.drop_constraint("uq_sale_client_request_id", "sale", type_="unique")
    op.drop_column("sale", "client_request_id")
    op.drop_column("discount_rule", "version")
    op.drop_column("product", "version")
    op.drop_table("business_sequence")
