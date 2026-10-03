"""门店归属、总部角色和持久AI会话；现有数据归到DP0001。"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_0023"
down_revision = "20261001_0022"
branch_labels = depends_on = None

SCOPED_TABLES = (
    "product",
    "purchase",
    "purchase_item",
    "sale",
    "sale_item",
    "inventory_batch",
    "discount_rule",
    "discount_rule_scope",
)


def timestamps():
    return [
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
    ]


def add_column(table, column):
    connection = op.get_bind()
    if column.name not in [item["name"] for item in sa.inspect(connection).get_columns(table)]:
        op.add_column(table, column)


def upgrade():
    connection = op.get_bind()
    if not sa.inspect(connection).has_table("store"):
        op.create_table(
            "store",
            sa.Column(
                "id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="门店ID"
            ),
            sa.Column("store_no", sa.String(20), nullable=False, comment="门店编号"),
            sa.Column("name", sa.String(100), nullable=False, comment="名称"),
            sa.Column("address", sa.String(255), comment="地址"),
            sa.Column("phone", sa.String(30), comment="联系电话"),
            sa.Column(
                "timezone",
                sa.String(50),
                nullable=False,
                server_default="Asia/Tokyo",
                comment="时区",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
                comment="是否启用",
            ),
            *timestamps(),
            sa.UniqueConstraint("store_no", name="uq_store_no"),
            mysql_charset="utf8mb4",
            comment="门店表",
        )
    connection.execute(
        sa.text(
            "INSERT IGNORE INTO store(id,store_no,name) "
            "VALUES(1,'DP0001','MarketFlow 本店（1号店）')"
        )
    )
    if not sa.inspect(connection).has_table("store_department"):
        op.create_table(
            "store_department",
            sa.Column(
                "store_id",
                sa.BigInteger(),
                sa.ForeignKey("store.id"),
                primary_key=True,
                comment="门店ID",
            ),
            sa.Column(
                "department_id",
                sa.BigInteger(),
                sa.ForeignKey("department.id"),
                primary_key=True,
                comment="统一部门ID",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
                comment="本店启用状态",
            ),
            *timestamps(),
            mysql_charset="utf8mb4",
            comment="门店部门启用配置表",
        )
    connection.execute(
        sa.text(
            "INSERT IGNORE INTO store_department(store_id,department_id,is_active) "
            "SELECT 1,id,is_active FROM department"
        )
    )
    for table in SCOPED_TABLES:
        add_column(
            table,
            sa.Column(
                "store_id",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("1"),
                comment="所属门店ID",
            ),
        )
    for table in (
        "employee",
        "operation_audit_log",
        "contact_notice",
        "contact_notice_recipient",
        "ai_pending_action",
    ):
        add_column(
            table, sa.Column("store_id", sa.BigInteger(), nullable=True, comment="所属或操作门店ID")
        )
        connection.execute(sa.text(f"UPDATE {table} SET store_id=1 WHERE store_id IS NULL"))
    for table in (
        *SCOPED_TABLES,
        "employee",
        "operation_audit_log",
        "contact_notice",
        "contact_notice_recipient",
        "ai_pending_action",
    ):
        inspector = sa.inspect(connection)
        if not any(
            fk["constrained_columns"] == ["store_id"] for fk in inspector.get_foreign_keys(table)
        ):
            op.create_foreign_key(f"fk_{table}_store", table, "store", ["store_id"], ["id"])
        if not any(
            index["column_names"] == ["store_id"]
            for index in sa.inspect(connection).get_indexes(table)
        ):
            op.create_index(f"ix_{table}_store_id", table, ["store_id"])
    checks = {item["name"] for item in sa.inspect(connection).get_check_constraints("employee")}
    for name in ("employee_role", "ck_employee_department_required"):
        if name in checks:
            op.drop_constraint(name, "employee", type_="check")
    op.create_check_constraint(
        "employee_role", "employee", "role IN ('总部','店长','正式员工','契约工')"
    )
    op.create_check_constraint(
        "ck_employee_department_required",
        "employee",
        "role IN ('总部','店长') OR department_id IS NOT NULL",
    )
    add_column(
        "contact_notice",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="store",
            comment="门店或总部来源",
        ),
    )
    if not sa.inspect(connection).has_table("ai_conversation"):
        op.create_table(
            "ai_conversation",
            sa.Column(
                "id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="会话ID"
            ),
            sa.Column(
                "employee_id",
                sa.BigInteger(),
                sa.ForeignKey("employee.id"),
                nullable=False,
                comment="所属账号",
            ),
            sa.Column("store_id", sa.BigInteger(), sa.ForeignKey("store.id"), comment="会话门店"),
            sa.Column("title", sa.String(100), nullable=False, comment="会话标题"),
            sa.Column("provider", sa.String(20), nullable=False, comment="模型供应商"),
            sa.Column("model", sa.String(100), comment="模型名称"),
            sa.Column("summary", sa.Text(), comment="历史摘要"),
            sa.Column("summary_through_id", sa.BigInteger(), comment="摘要覆盖消息ID"),
            *timestamps(),
            mysql_charset="utf8mb4",
            comment="员工AI会话表",
        )
        op.create_index("ix_ai_conversation_employee_id", "ai_conversation", ["employee_id"])
        op.create_index("ix_ai_conversation_store_id", "ai_conversation", ["store_id"])
    if not sa.inspect(connection).has_table("ai_message"):
        op.create_table(
            "ai_message",
            sa.Column(
                "id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="消息ID"
            ),
            sa.Column(
                "conversation_id",
                sa.BigInteger(),
                sa.ForeignKey("ai_conversation.id", ondelete="CASCADE"),
                nullable=False,
                comment="会话ID",
            ),
            sa.Column("role", sa.String(20), nullable=False, comment="发送方"),
            sa.Column("content", sa.Text(), nullable=False, comment="正文"),
            sa.Column("actions", sa.JSON(), comment="待确认操作"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
                comment="创建时间",
            ),
            mysql_charset="utf8mb4",
            comment="AI完整历史消息表",
        )
        op.create_index("ix_ai_message_conversation_id", "ai_message", ["conversation_id"])


def downgrade():
    raise RuntimeError("多店铺迁移含业务归属，降级需要先导出并人工处理数据")
