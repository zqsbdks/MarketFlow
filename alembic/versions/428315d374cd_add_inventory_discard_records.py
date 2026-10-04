"""add inventory discard records

Revision ID: 428315d374cd
Revises: 20261002_0029
Create Date: 2026-10-04 15:24:56.835249

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "428315d374cd"
down_revision: str | Sequence[str] | None = "20261002_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_discard",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="废弃单主键"),
        sa.Column(
            "request_key", sa.String(length=64), nullable=False, comment="门店内幂等请求编号"
        ),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="商品ID"),
        sa.Column("product_no", sa.String(length=30), nullable=False, comment="商品编号快照"),
        sa.Column("product_name", sa.String(length=100), nullable=False, comment="商品名称快照"),
        sa.Column("department_id", sa.BigInteger(), nullable=False, comment="所属部门ID"),
        sa.Column("department_name", sa.String(length=100), nullable=False, comment="部门名称快照"),
        sa.Column(
            "employee_id", sa.BigInteger(), nullable=True, comment="操作员工ID；自动任务为空"
        ),
        sa.Column(
            "employee_name", sa.String(length=100), nullable=True, comment="操作员工姓名快照"
        ),
        sa.Column("reason_code", sa.String(length=20), nullable=False, comment="废弃原因编码"),
        sa.Column("note", sa.String(length=255), nullable=True, comment="补充说明"),
        sa.Column(
            "requested_batch_id", sa.BigInteger(), nullable=True, comment="指定批次ID；自动分配为空"
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, comment="废弃总数量"),
        sa.Column(
            "total_cost",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            comment="按批次进货成本计算的损耗金额",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="日本时间处理时间"),
        sa.Column("store_id", sa.BigInteger(), nullable=False, comment="所属门店ID"),
        sa.CheckConstraint(
            "reason_code IN ('expired', 'damaged', 'spoiled', 'contaminated', 'other')",
            name="ck_discard_reason",
        ),
        sa.CheckConstraint("quantity > 0 AND total_cost >= 0", name="ck_discard_amount"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["requested_batch_id"], ["inventory_batch.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "request_key", name="uq_discard_store_request"),
        comment="商品废弃单",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        op.f("ix_inventory_discard_created_at"), "inventory_discard", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_inventory_discard_department_id"),
        "inventory_discard",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_discard_product_id"), "inventory_discard", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_inventory_discard_store_id"), "inventory_discard", ["store_id"], unique=False
    )
    op.create_table(
        "inventory_discard_item",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="废弃明细主键"
        ),
        sa.Column("discard_id", sa.BigInteger(), nullable=False, comment="所属废弃单ID"),
        sa.Column("batch_id", sa.BigInteger(), nullable=False, comment="库存批次ID"),
        sa.Column("batch_no", sa.String(length=30), nullable=False, comment="库存批次号快照"),
        sa.Column("expiration_date", sa.Date(), nullable=True, comment="批次到期日期快照"),
        sa.Column("quantity", sa.Integer(), nullable=False, comment="本批次废弃数量"),
        sa.Column(
            "unit_cost",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment="批次进货单价快照",
        ),
        sa.Column(
            "total_cost",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            comment="本批次损耗金额",
        ),
        sa.Column("before_quantity", sa.Integer(), nullable=False, comment="扣减前剩余数量"),
        sa.Column("after_quantity", sa.Integer(), nullable=False, comment="扣减后剩余数量"),
        sa.Column("store_id", sa.BigInteger(), nullable=False, comment="所属门店ID"),
        sa.CheckConstraint(
            "quantity > 0 AND unit_cost >= 0 AND total_cost >= 0", name="ck_discard_item_amount"
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["inventory_batch.id"]),
        sa.ForeignKeyConstraint(["discard_id"], ["inventory_discard.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discard_id", "batch_id", name="uq_discard_batch"),
        comment="废弃批次明细",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        op.f("ix_inventory_discard_item_discard_id"),
        "inventory_discard_item",
        ["discard_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_discard_item_store_id"),
        "inventory_discard_item",
        ["store_id"],
        unique=False,
    )
    backfill_legacy_records(op.get_bind())


def backfill_legacy_records(connection) -> None:
    """旧流水只导入记录，不改库存；幂等键保证恢复或重试不重复导入。"""
    connection.execute(
        sa.text("""
        INSERT INTO inventory_discard
          (store_id, request_key, product_id, product_no, product_name,
           department_id, department_name, employee_id, employee_name,
           reason_code, note, requested_batch_id, quantity, total_cost, created_at)
        SELECT b.store_id, CONCAT('legacy:', a.id), p.id, p.product_no, p.name,
               p.department_id, d.name, a.employee_id, e.name, 'expired', a.reason, b.id,
               CAST(JSON_UNQUOTE(JSON_EXTRACT(a.after_data,'$.discarded_quantity')) AS UNSIGNED),
               i.unit_cost * CAST(JSON_UNQUOTE(
                   JSON_EXTRACT(a.after_data,'$.discarded_quantity')) AS UNSIGNED), a.created_at
        FROM operation_audit_log a
        JOIN inventory_batch b ON b.id=a.target_id
        JOIN product p ON p.id=b.product_id AND p.store_id=b.store_id
        JOIN purchase_item i ON i.id=b.purchase_item_id AND i.store_id=b.store_id
        JOIN department d ON d.id=p.department_id
        LEFT JOIN employee e ON e.id=a.employee_id
        WHERE a.module='inventory' AND a.target_type='inventory_batch'
          AND a.action='discard_expired'
          AND (a.store_id IS NULL OR a.store_id=b.store_id)
          AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
              a.after_data,'$.discarded_quantity')) AS UNSIGNED) > 0
          AND JSON_EXTRACT(a.after_data,'$.discard_id') IS NULL
          AND NOT EXISTS (SELECT 1 FROM inventory_discard r
                          WHERE r.store_id=b.store_id AND r.request_key=CONCAT('legacy:',a.id))
    """)
    )
    connection.execute(
        sa.text("""
        INSERT INTO inventory_discard_item
          (store_id, discard_id, batch_id, batch_no, expiration_date,
           quantity, unit_cost, total_cost, before_quantity, after_quantity)
        SELECT r.store_id, r.id, b.id, b.batch_no, b.expiration_date,
               r.quantity, i.unit_cost, r.total_cost, r.quantity, 0
        FROM inventory_discard r
        JOIN inventory_batch b ON b.id=r.requested_batch_id AND b.store_id=r.store_id
        JOIN purchase_item i ON i.id=b.purchase_item_id
        WHERE r.request_key LIKE 'legacy:%'
          AND NOT EXISTS (SELECT 1 FROM inventory_discard_item x WHERE x.discard_id=r.id)
    """)
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_discard_item_store_id"), table_name="inventory_discard_item")
    op.drop_index(op.f("ix_inventory_discard_item_discard_id"), table_name="inventory_discard_item")
    op.drop_table("inventory_discard_item")
    op.drop_index(op.f("ix_inventory_discard_store_id"), table_name="inventory_discard")
    op.drop_index(op.f("ix_inventory_discard_product_id"), table_name="inventory_discard")
    op.drop_index(op.f("ix_inventory_discard_department_id"), table_name="inventory_discard")
    op.drop_index(op.f("ix_inventory_discard_created_at"), table_name="inventory_discard")
    op.drop_table("inventory_discard")
