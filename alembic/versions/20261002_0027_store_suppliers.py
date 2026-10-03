"""门店独立供应商与报价；已创建的演示门店自动复制其来源目录。"""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20261002_0027"
down_revision = "20261001_0026"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ("supplier", "supplier_product"):
        op.add_column(
            table,
            sa.Column(
                "store_id",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("1"),
                comment="所属门店ID",
            ),
        )
        op.create_foreign_key(f"fk_{table}_store", table, "store", ["store_id"], ["id"])
        op.create_index(f"ix_{table}_store_id", table, ["store_id"])
    # 名称允许不同门店重复；编号仍全局唯一，方便扫码和审计追踪。
    indexes = sa.inspect(bind).get_indexes("supplier")
    for index in indexes:
        if index["name"] == "uq_supplier_name":
            op.drop_index(index["name"], table_name="supplier")
    op.create_unique_constraint("uq_supplier_name", "supplier", ["store_id", "name"])

    stores = bind.execute(sa.text("SELECT id FROM store WHERE id != 1 ORDER BY id")).scalars().all()
    for store_id in stores:
        catalogs = (
            bind.execute(
                sa.text(
                    "SELECT DISTINCT sp.id, sp.supplier_id, sp.category_id, sp.name, "
                    "sp.unit_cost, sp.shelf_life_days, sp.is_active FROM supplier_product sp "
                    "JOIN product p ON p.supplier_product_id=sp.id WHERE p.store_id=:store_id"
                ),
                {"store_id": store_id},
            )
            .mappings()
            .all()
        )
        supplier_map = {}
        catalog_map = {}
        for old in catalogs:
            old_supplier_id = old["supplier_id"]
            if old_supplier_id not in supplier_map:
                original = (
                    bind.execute(
                        sa.text(
                            "SELECT name,contact_name,phone,address,is_active "
                            "FROM supplier WHERE id=:id"
                        ),
                        {"id": old_supplier_id},
                    )
                    .mappings()
                    .one()
                )
                result = bind.execute(
                    sa.text(
                        "INSERT INTO supplier "
                        "(store_id,supplier_no,name,contact_name,phone,address,is_active) "
                        "VALUES(:store_id,:number,:name,:contact,:phone,:address,:active)"
                    ),
                    {
                        "store_id": store_id,
                        "number": "TMP" + uuid4().hex[:16],
                        "name": original["name"],
                        "contact": original["contact_name"],
                        "phone": original["phone"],
                        "address": original["address"],
                        "active": original["is_active"],
                    },
                )
                new_supplier_id = result.lastrowid
                bind.execute(
                    sa.text("UPDATE supplier SET supplier_no=:number WHERE id=:id"),
                    {"number": f"SUP{new_supplier_id:05d}", "id": new_supplier_id},
                )
                supplier_map[old_supplier_id] = new_supplier_id
            result = bind.execute(
                sa.text(
                    "INSERT INTO supplier_product "
                    "(store_id,supplier_id,category_id,name,unit_cost,shelf_life_days,is_active) "
                    "VALUES(:store_id,:supplier_id,:category_id,:name,:cost,:life,:active)"
                ),
                {
                    "store_id": store_id,
                    "supplier_id": supplier_map[old_supplier_id],
                    "category_id": old["category_id"],
                    "name": old["name"],
                    "cost": old["unit_cost"],
                    "life": old["shelf_life_days"],
                    "active": old["is_active"],
                },
            )
            catalog_map[old["id"]] = result.lastrowid
        for old_catalog, new_catalog in catalog_map.items():
            bind.execute(
                sa.text(
                    "UPDATE product SET supplier_product_id=:new "
                    "WHERE store_id=:store_id AND supplier_product_id=:old"
                ),
                {"new": new_catalog, "store_id": store_id, "old": old_catalog},
            )
            bind.execute(
                sa.text(
                    "UPDATE purchase_item SET supplier_product_id=:new "
                    "WHERE store_id=:store_id AND supplier_product_id=:old"
                ),
                {"new": new_catalog, "store_id": store_id, "old": old_catalog},
            )
        for old_supplier, new_supplier in supplier_map.items():
            bind.execute(
                sa.text(
                    "UPDATE purchase_item SET supplier_id=:new "
                    "WHERE store_id=:store_id AND supplier_id=:old"
                ),
                {"new": new_supplier, "store_id": store_id, "old": old_supplier},
            )


def downgrade():
    raise RuntimeError("各门店已有独立报价，不能无损合并回公共供应商目录")
