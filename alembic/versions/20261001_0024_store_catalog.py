"""每店独立的商品目录匹配和折扣名称。"""
import sqlalchemy as sa
from alembic import op

revision = "20261001_0024"
down_revision = "20261001_0023"
branch_labels = depends_on = None

def upgrade():
    connection = op.get_bind()
    # 原目录一对一索引改成普通索引，外键仍需要该索引。
    indexes = sa.inspect(connection).get_indexes("product")
    if not any(index["name"] == "ix_product_catalog_lookup" for index in indexes):
        op.create_index("ix_product_catalog_lookup", "product", ["supplier_product_id"])
    for index in indexes:
        if index.get("unique") and index["column_names"] == ["supplier_product_id"]:
            op.drop_index(index["name"], table_name="product")
    if not any(index["name"] == "uq_store_catalog_product" for index in sa.inspect(connection).get_indexes("product")):
        op.create_unique_constraint("uq_store_catalog_product", "product", ["store_id", "supplier_product_id"])
    indexes = sa.inspect(connection).get_indexes("discount_rule")
    if any(index["name"] == "uq_discount_rule_name" and index["column_names"] == ["name"] for index in indexes):
        op.drop_index("uq_discount_rule_name", table_name="discount_rule")
        op.create_unique_constraint("uq_discount_rule_name", "discount_rule", ["store_id", "name"])

def downgrade():
    raise RuntimeError("多个门店可以使用同一目录，不能安全还原为一对一")
