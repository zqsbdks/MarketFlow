"""store encrypted employee AI provider keys

Revision ID: 20261001_0020
Revises: 20261001_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0020"
down_revision: str | Sequence[str] | None = "20261001_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建员工专属的加密 AI 密钥表。"""

    op.create_table(
        "ai_provider_credential",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="密钥记录ID"),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="所属员工ID"),
        sa.Column("provider", sa.String(20), nullable=False, comment="模型供应商"),
        sa.Column("encrypted_key", sa.String(2048), nullable=False, comment="加密后的API密钥"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "provider", name="uq_ai_provider_credential_owner"),
        mysql_charset="utf8mb4",
        comment="员工AI模型密钥表",
    )
    op.create_index(
        "ix_ai_provider_credential_employee_id", "ai_provider_credential", ["employee_id"]
    )


def downgrade() -> None:
    """删除密钥表及其全部密文；回退前请确认数据保留要求。"""

    op.drop_index("ix_ai_provider_credential_employee_id", table_name="ai_provider_credential")
    op.drop_table("ai_provider_credential")
