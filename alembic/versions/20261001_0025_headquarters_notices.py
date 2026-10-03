"""总部联络指定接收门店。"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_0025"
down_revision = "20261001_0024"
branch_labels = depends_on = None


def upgrade():
    if "target_store_ids" not in [
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("contact_notice")
    ]:
        op.add_column(
            "contact_notice",
            sa.Column(
                "target_store_ids",
                sa.JSON(),
                nullable=True,
                comment="总部指定接收门店；空列表表示全部",
            ),
        )


def downgrade():
    op.drop_column("contact_notice", "target_store_ids")
