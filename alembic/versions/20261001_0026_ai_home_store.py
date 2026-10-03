"""会话创建时的员工门店归属快照。"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_0026"
down_revision = "20261001_0025"
branch_labels = depends_on = None


def upgrade():
    if "home_store_id" not in [
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("ai_conversation")
    ]:
        op.add_column(
            "ai_conversation",
            sa.Column(
                "home_store_id", sa.BigInteger(), nullable=True, comment="会话创建时员工归属门店"
            ),
        )
        op.create_foreign_key(
            "fk_ai_conversation_home_store", "ai_conversation", "store", ["home_store_id"], ["id"]
        )


def downgrade():
    op.drop_constraint("fk_ai_conversation_home_store", "ai_conversation", type_="foreignkey")
    op.drop_column("ai_conversation", "home_store_id")
