"""create MarketFlow first-version tables

Revision ID: 20260901_0001
Revises:
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建第一版六张业务表及其约束和索引。"""

    op.create_table(
        "department",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_department_code"),
        sa.UniqueConstraint("name", name="uq_department_name"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "employee",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_no", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "store_manager",
                "regular_employee",
                "contract_worker",
                name="employee_role",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role = 'store_manager' OR department_id IS NOT NULL",
            name="ck_employee_department_required",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_employee_department_id_department",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_no", name="uq_employee_employee_no"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_employee_department_id", "employee", ["department_id"])

    op.create_table(
        "category",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_category_department_id_department",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "department_id",
            "name",
            name="uq_category_department_name",
        ),
        sa.UniqueConstraint(
            "id",
            "department_id",
            name="uq_category_id_department_id",
        ),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_category_department_id", "category", ["department_id"])

    op.create_table(
        "product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_no", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("sale_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "on_sale",
                "stopped",
                name="product_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="on_sale",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purchase_price >= 0",
            name="ck_product_purchase_price_non_negative",
        ),
        sa.CheckConstraint("sale_price >= 0", name="ck_product_sale_price_non_negative"),
        sa.CheckConstraint(
            "stock_quantity >= 0",
            name="ck_product_stock_quantity_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "department_id"],
            ["category.id", "category.department_id"],
            name="fk_product_category_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_product_department_id_department",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_no", name="uq_product_product_no"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_product_category_id", "product", ["category_id"])
    op.create_index("ix_product_department_id", "product", ["department_id"])

    op.create_table(
        "sale",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sale_no", sa.String(length=30), nullable=False),
        sa.Column("sold_at", sa.DateTime(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("gross_profit", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "demo_seed",
                name="sale_source",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            server_default="demo_seed",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_sale_total_amount_non_negative"),
        sa.CheckConstraint("total_cost >= 0", name="ck_sale_total_cost_non_negative"),
        sa.CheckConstraint(
            "gross_profit = total_amount - total_cost",
            name="ck_sale_gross_profit_matches_totals",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_no", name="uq_sale_sale_no"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_sale_sold_at", "sale", ["sold_at"])

    op.create_table(
        "sale_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sale_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_no_snapshot", sa.String(length=20), nullable=False),
        sa.Column("product_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cost_subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_item_quantity_positive"),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_sale_item_unit_price_non_negative",
        ),
        sa.CheckConstraint("unit_cost >= 0", name="ck_sale_item_unit_cost_non_negative"),
        sa.CheckConstraint(
            "subtotal = unit_price * quantity",
            name="ck_sale_item_subtotal_matches",
        ),
        sa.CheckConstraint(
            "cost_subtotal = unit_cost * quantity",
            name="ck_sale_item_cost_subtotal_matches",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_sale_item_department_id_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.id"],
            name="fk_sale_item_product_id_product",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"],
            ["sale.id"],
            name="fk_sale_item_sale_id_sale",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_sale_item_department_id", "sale_item", ["department_id"])
    op.create_index("ix_sale_item_product_id", "sale_item", ["product_id"])
    op.create_index("ix_sale_item_sale_id", "sale_item", ["sale_id"])


def downgrade() -> None:
    """按外键依赖逆序删除第一版业务表。"""

    op.drop_index("ix_sale_item_sale_id", table_name="sale_item")
    op.drop_index("ix_sale_item_product_id", table_name="sale_item")
    op.drop_index("ix_sale_item_department_id", table_name="sale_item")
    op.drop_table("sale_item")
    op.drop_index("ix_sale_sold_at", table_name="sale")
    op.drop_table("sale")
    op.drop_index("ix_product_department_id", table_name="product")
    op.drop_index("ix_product_category_id", table_name="product")
    op.drop_table("product")
    op.drop_index("ix_category_department_id", table_name="category")
    op.drop_table("category")
    op.drop_index("ix_employee_department_id", table_name="employee")
    op.drop_table("employee")
    op.drop_table("department")
