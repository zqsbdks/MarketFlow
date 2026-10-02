"""新增联络事项和员工确认记录表。"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_0022"
down_revision = "20261001_0021"
branch_labels = None
depends_on = None


def upgrade():
    """建立主表及接收名单，不更改现有业务数据。"""
    # 固定迁移字段，后续修改 ORM 不会改变旧迁移的行为。
    connection = op.get_bind()
    if not sa.inspect(connection).has_table("contact_notice"):
        op.create_table(
            "contact_notice",
            sa.Column(
                "id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="联络事项ID"
            ),
            sa.Column("title", sa.String(100), nullable=False, comment="标题"),
            sa.Column("content", sa.Text(), nullable=False, comment="正文"),
            sa.Column("priority", sa.String(20), nullable=False, comment="优先级"),
            sa.Column("target_type", sa.String(20), nullable=False, comment="接收范围"),
            sa.Column(
                "department_id",
                sa.BigInteger(),
                sa.ForeignKey("department.id"),
                nullable=True,
                comment="接收部门ID",
            ),
            sa.Column(
                "publisher_id",
                sa.BigInteger(),
                sa.ForeignKey("employee.id"),
                nullable=False,
                comment="发布员工ID",
            ),
            sa.Column("starts_at", sa.DateTime(), nullable=False, comment="开始时间"),
            sa.Column("deadline_at", sa.DateTime(), nullable=True, comment="确认截止时间"),
            sa.Column(
                "close_on_all_confirmed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
                comment="全员确认自动关闭",
            ),
            sa.Column("status", sa.String(20), nullable=False, comment="事项状态"),
            sa.Column("closed_at", sa.DateTime(), nullable=True, comment="关闭时间"),
            sa.Column("close_reason", sa.String(30), nullable=True, comment="关闭原因"),
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
                comment="版本号",
            ),
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
                "target_type IN ('all', 'department', 'personal')", name="ck_notice_target"
            ),
            sa.CheckConstraint(
                "status IN ('draft', 'published', 'closed', 'withdrawn')", name="ck_notice_status"
            ),
            sa.CheckConstraint(
                "priority IN ('normal', 'important', 'urgent')", name="ck_notice_priority"
            ),
            mysql_charset="utf8mb4",
            comment="联络事项表",
        )
        op.create_index("ix_contact_notice_publisher_id", "contact_notice", ["publisher_id"])
        op.create_index("ix_contact_notice_status", "contact_notice", ["status"])
    if not sa.inspect(connection).has_table("contact_notice_recipient"):
        op.create_table(
            "contact_notice_recipient",
            sa.Column(
                "id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="接收记录ID"
            ),
            sa.Column(
                "notice_id",
                sa.BigInteger(),
                sa.ForeignKey("contact_notice.id", ondelete="CASCADE"),
                nullable=False,
                comment="联络事项ID",
            ),
            sa.Column(
                "employee_id",
                sa.BigInteger(),
                sa.ForeignKey("employee.id"),
                nullable=False,
                comment="接收员工ID",
            ),
            sa.Column("read_at", sa.DateTime(), nullable=True, comment="首次查看时间"),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True, comment="确认时间"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
                comment="创建时间",
            ),
            sa.UniqueConstraint("notice_id", "employee_id", name="uq_notice_recipient"),
            mysql_charset="utf8mb4",
            comment="联络事项员工确认表",
        )
        op.create_index(
            "ix_contact_notice_recipient_notice_id", "contact_notice_recipient", ["notice_id"]
        )
        op.create_index(
            "ix_contact_notice_recipient_employee_id", "contact_notice_recipient", ["employee_id"]
        )


def downgrade():
    """先删除接收记录，再删除事项。"""
    op.drop_table("contact_notice_recipient")
    op.drop_table("contact_notice")
