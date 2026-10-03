"""只读检查演示数据的库存、金额、日期及档案一致性。"""

import asyncio

from sqlalchemy import text

from app.core.business_time import business_now
from app.core.database import async_engine

CHECKS = {
    "expired on hand": "SELECT COUNT(*) FROM inventory_batch "
    "WHERE expiration_date<DATE(:now) AND remaining_quantity>0",
    "future sales": "SELECT COUNT(*) FROM sale WHERE sold_at>:now",
    "future purchase orders": "SELECT COUNT(*) FROM purchase WHERE ordered_at>:now",
    "sales outside batch availability": "SELECT COUNT(*) FROM sale_item i "
    "JOIN sale s ON s.id=i.sale_id JOIN inventory_batch b ON b.id=i.inventory_batch_id "
    "WHERE s.sold_at<b.arrived_at OR DATE(s.sold_at)>b.expiration_date",
    "product stock mismatch": "SELECT COUNT(*) FROM product p JOIN "
    "(SELECT product_id,SUM(remaining_quantity) qty FROM inventory_batch GROUP BY product_id) b "
    "ON b.product_id=p.id WHERE p.stock_quantity<>b.qty",
    "batch balance mismatch": "SELECT COUNT(*) FROM inventory_batch b LEFT JOIN "
    "(SELECT inventory_batch_id,SUM(quantity) sold FROM sale_item "
    "GROUP BY inventory_batch_id) s ON s.inventory_batch_id=b.id LEFT JOIN "
    "(SELECT target_id,SUM(JSON_EXTRACT(after_data,'$.discarded_quantity')) waste "
    "FROM operation_audit_log WHERE action='discard_expired' GROUP BY target_id) w "
    "ON w.target_id=b.id WHERE b.initial_quantity<> "
    "COALESCE(s.sold,0)+COALESCE(w.waste,0)+b.remaining_quantity",
    "purchase subtotal mismatch": "SELECT COUNT(*) FROM purchase_item "
    "WHERE subtotal<>quantity*unit_cost",
    "purchase total mismatch": "SELECT COUNT(*) FROM purchase p JOIN "
    "(SELECT purchase_id,SUM(subtotal) amount FROM purchase_item GROUP BY purchase_id) i "
    "ON i.purchase_id=p.id WHERE p.total_amount<>i.amount",
    "sale total mismatch": "SELECT COUNT(*) FROM sale s JOIN "
    "(SELECT sale_id,SUM(subtotal) amount,SUM(cost_subtotal) cost FROM sale_item "
    "GROUP BY sale_id) i ON i.sale_id=s.id "
    "WHERE s.total_amount<>i.amount OR s.total_cost<>i.cost",
    "incomplete employee profile": "SELECT COUNT(*) FROM employee e LEFT JOIN employee_detail d "
    "ON d.employee_id=e.id WHERE d.employee_id IS NULL OR d.gender='未填写' "
    "OR d.birth_date IS NULL OR d.phone IS NULL OR d.address IS NULL",
    "employee age or employment dates": "SELECT COUNT(*) FROM employee_detail "
    "WHERE birth_date+INTERVAL 18 YEAR>hire_date OR hire_date>DATE(:now) "
    "OR separation_date<hire_date",
    "notice confirmation before reading": "SELECT COUNT(*) FROM contact_notice_recipient "
    "WHERE confirmed_at IS NOT NULL AND (read_at IS NULL OR confirmed_at<read_at)",
    "future actual notice events": "SELECT COUNT(*) FROM contact_notice_recipient "
    "WHERE read_at>:now OR confirmed_at>:now",
    "notice events after closing": "SELECT COUNT(*) FROM contact_notice_recipient r "
    "JOIN contact_notice n ON n.id=r.notice_id WHERE n.closed_at IS NOT NULL "
    "AND (r.read_at>n.closed_at OR r.confirmed_at>n.closed_at)",
    "notice all confirmed mismatch": "SELECT COUNT(*) FROM contact_notice n "
    "WHERE n.close_reason='all_confirmed' AND EXISTS "
    "(SELECT 1 FROM contact_notice_recipient r WHERE r.notice_id=n.id "
    "AND r.confirmed_at IS NULL)",
}


async def check():
    errors = 0
    now = business_now()
    async with async_engine.connect() as c:
        for name, query in CHECKS.items():
            count = int((await c.execute(text(query), {"now": now})).scalar() or 0)
            errors += count
            print(f"{name}: {count}")
        result = (
            await c.execute(text("SELECT SUM(gross_profit)/SUM(total_amount) margin FROM sale"))
        ).scalar()
        print(f"Simulated gross margin: {float(result or 0):.2%}")
    if errors:
        raise RuntimeError(f"Demo checks failed: {errors} inconsistent records")
    print("All demo data checks passed.")


async def main():
    try:
        await check()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
