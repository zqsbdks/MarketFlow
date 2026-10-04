"""只读验证废弃单、批次明细、库存和损耗金额。"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from app.core.database import async_engine

CHECKS = {
    "record_totals": """
      SELECT COUNT(*) FROM inventory_discard r LEFT JOIN (
        SELECT discard_id, SUM(quantity) qty, SUM(total_cost) cost
        FROM inventory_discard_item GROUP BY discard_id
      ) i ON i.discard_id=r.id
      WHERE i.discard_id IS NULL OR r.quantity<>i.qty OR r.total_cost<>i.cost
    """,
    "item_amounts_and_store": """
      SELECT COUNT(*) FROM inventory_discard_item x
      JOIN inventory_discard r ON r.id=x.discard_id
      JOIN inventory_batch b ON b.id=x.batch_id
      JOIN purchase_item p ON p.id=b.purchase_item_id
      WHERE x.store_id<>r.store_id OR x.store_id<>b.store_id
        OR b.product_id<>r.product_id OR x.quantity<=0
        OR x.before_quantity-x.after_quantity<>x.quantity
        OR x.after_quantity<0 OR x.unit_cost<>p.unit_cost
        OR x.total_cost<>x.quantity*x.unit_cost
    """,
    "product_stock": """
      SELECT COUNT(*) FROM product p LEFT JOIN (
        SELECT product_id, SUM(remaining_quantity) qty
        FROM inventory_batch GROUP BY product_id
      ) b ON b.product_id=p.id WHERE p.stock_quantity<>COALESCE(b.qty,0)
    """,
    "expired_stock_remaining": """
      SELECT COUNT(*) FROM inventory_batch
      WHERE expiration_date<DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','+09:00'))
        AND remaining_quantity>0
    """,
    "expired_discard_date": """
      SELECT COUNT(*) FROM inventory_discard r
      JOIN inventory_discard_item x ON x.discard_id=r.id
      WHERE r.reason_code='expired' AND
        (x.expiration_date IS NULL OR DATE(r.created_at)<=x.expiration_date)
    """,
}


async def main():
    try:
        async with async_engine.connect() as connection:
            checks = {
                name: int((await connection.execute(text(sql))).scalar_one())
                for name, sql in CHECKS.items()
            }
            counts = dict(
                (
                    await connection.execute(
                        text("""
              SELECT COUNT(*) records, COALESCE(SUM(quantity),0) quantity,
                     COALESCE(SUM(total_cost),0) total_cost,
                     SUM(request_key LIKE 'legacy:%') imported_history,
                     SUM(employee_id IS NULL) automatic_records
              FROM inventory_discard
            """)
                    )
                )
                .mappings()
                .one()
            )
            report = {"checks": checks, "counts": counts}
            output = Path("docs/verification/inventory-discard-summary.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, default=str))
            if any(checks.values()):
                raise RuntimeError("Disposal verification found inconsistent records")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
