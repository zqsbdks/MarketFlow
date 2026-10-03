"""校准日语演示数据；只处理演示单据，重建模拟库存流水并补齐档案。"""

import asyncio
import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from app.core.business_time import business_now
from app.core.database import async_engine

MARKER = "realistic_demo_v3"


async def normalize():
    now = business_now().replace(microsecond=0)
    today = now.date()
    yesterday = today - timedelta(days=1)
    async with async_engine.begin() as c:
        signature = (
            await c.execute(
                text(
                    "SELECT CONCAT(COALESCE(MAX(id),0),':',COUNT(*)) FROM sale "
                    "WHERE source='demo_seed'"
                )
            )
        ).scalar()
        done = (
            await c.execute(
                text(
                    "SELECT after_data FROM operation_audit_log WHERE action=:marker "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"marker": MARKER},
            )
        ).scalar()
        if done and json.loads(done).get("signature") == signature:
            print("Demo already normalized; unchanged.")
            return
        pos = (await c.execute(text("SELECT COUNT(*) FROM sale WHERE source='pos'"))).scalar()
        manual = (
            await c.execute(
                text(
                    "SELECT COUNT(*) FROM operation_audit_log WHERE module='inventory' "
                    "AND action='update_quantity'"
                )
            )
        ).scalar()
        if pos or manual:
            raise RuntimeError("Real sales or manual inventory changes exist; repair stopped.")

        # 改正生成脚本在当天营业前预先写入整天销售的时间错误。
        await c.execute(
            text(
                "UPDATE inventory_batch b JOIN purchase_item i ON i.id=b.purchase_item_id "
                "JOIN purchase p ON p.id=i.purchase_id "
                "SET b.arrived_at=DATE_SUB(b.arrived_at,INTERVAL 1 DAY), "
                "b.production_date=DATE_SUB(b.production_date,INTERVAL 1 DAY), "
                "b.expiration_date=DATE_SUB(b.expiration_date,INTERVAL 1 DAY) "
                "WHERE b.arrived_at>:now AND (p.purchase_no LIKE 'PO%' "
                "OR p.purchase_no LIKE 'HPO%')"
            ),
            {"now": now},
        )
        await c.execute(
            text(
                "UPDATE purchase_item i JOIN inventory_batch b ON b.purchase_item_id=i.id "
                "SET i.production_date=b.production_date,i.expiration_date=b.expiration_date"
            )
        )
        await c.execute(
            text(
                "UPDATE purchase SET arrived_at=DATE_SUB(arrived_at,INTERVAL 1 DAY), "
                "expected_arrival_at=DATE_SUB(expected_arrival_at,INTERVAL 1 DAY), "
                "ordered_at=DATE_SUB(ordered_at,INTERVAL 1 DAY) "
                "WHERE status='arrived' AND arrived_at>:now "
                "AND (purchase_no LIKE 'PO%' OR purchase_no LIKE 'HPO%')"
            ),
            {"now": now},
        )
        await c.execute(
            text(
                "UPDATE sale SET sold_at=DATE_SUB(sold_at,INTERVAL 1 DAY), "
                "created_at=DATE_SUB(created_at,INTERVAL 1 DAY) "
                "WHERE sold_at>:now AND source='demo_seed'"
            ),
            {"now": now},
        )
        await c.execute(
            text(
                "UPDATE sale s JOIN (SELECT i.sale_id,MAX(b.arrived_at) latest "
                "FROM sale_item i JOIN inventory_batch b ON b.id=i.inventory_batch_id "
                "GROUP BY i.sale_id) x ON x.sale_id=s.id "
                "SET s.sold_at=x.latest+INTERVAL 15 MINUTE, "
                "s.created_at=x.latest+INTERVAL 15 MINUTE "
                "WHERE s.source='demo_seed' AND s.sold_at<x.latest"
            )
        )
        await c.execute(
            text(
                "UPDATE sale_item i JOIN sale s ON s.id=i.sale_id "
                "JOIN discount_rule r ON r.id=i.discount_rule_id "
                "SET "
                "i.unit_price=i.original_unit_price,i.subtotal=i.original_unit_price*i.quantity, "
                "i.discount_amount=0,i.discount_rule_id=NULL,i.discount_rule_name_snapshot=NULL, "
                "i.discount_type_snapshot=NULL,i.discount_value_snapshot=NULL "
                "WHERE s.source='demo_seed' AND r.schedule_type IN ('daily','weekly') "
                "AND (TIME(s.sold_at)<r.daily_start_time OR TIME(s.sold_at)>r.daily_end_time)"
            )
        )
        await c.execute(
            text(
                "UPDATE purchase SET ordered_at=:ordered, "
                "expected_arrival_at=:ordered+INTERVAL 2 DAY, created_at=:ordered "
                "WHERE ordered_at>:now AND status='pending' "
                "AND (purchase_no LIKE 'PO%' OR purchase_no LIKE 'HPO%')"
            ),
            {"ordered": datetime.combine(yesterday, time(19)), "now": now},
        )

        # 食品零售样本采用整数日元，分部门设置模拟成本率，绝非行业统计值。
        await c.execute(
            text(
                "UPDATE product p JOIN department d ON d.id=p.department_id "
                "SET p.purchase_price=ROUND(p.sale_price*CASE d.code "
                "WHEN 'PRODUCE' THEN 0.70 WHEN 'MEAT' THEN 0.74 "
                "WHEN 'SEAFOOD' THEN 0.72 ELSE 0.65 END,0)"
            )
        )
        await c.execute(
            text(
                "UPDATE supplier_product s JOIN product p ON p.supplier_product_id=s.id "
                "SET s.unit_cost=p.purchase_price"
            )
        )
        await c.execute(
            text(
                "UPDATE purchase_item i JOIN purchase pur ON pur.id=i.purchase_id "
                "JOIN product p ON p.id=i.product_id "
                "SET i.unit_cost=ROUND(p.purchase_price*(0.98+MOD(i.id,5)*0.01),0), "
                "i.subtotal=ROUND(p.purchase_price*(0.98+MOD(i.id,5)*0.01),0)*i.quantity "
                "WHERE pur.purchase_no LIKE 'PO%' OR pur.purchase_no LIKE 'HPO%'"
            )
        )
        await c.execute(
            text(
                "UPDATE sale_item i JOIN sale s ON s.id=i.sale_id "
                "JOIN inventory_batch b ON b.id=i.inventory_batch_id "
                "JOIN purchase_item pi ON pi.id=b.purchase_item_id "
                "SET i.unit_cost=pi.unit_cost,i.cost_subtotal=pi.unit_cost*i.quantity, "
                "i.unit_price=FLOOR(i.unit_price),i.subtotal=FLOOR(i.unit_price)*i.quantity, "
                "i.discount_amount=(i.original_unit_price-FLOOR(i.unit_price))*i.quantity "
                "WHERE s.source='demo_seed'"
            )
        )

        sold = dict(
            (
                await c.execute(
                    text(
                        "SELECT inventory_batch_id,SUM(quantity) FROM sale_item "
                        "GROUP BY inventory_batch_id"
                    )
                )
            ).all()
        )
        demand = dict(
            (
                await c.execute(
                    text(
                        "SELECT i.product_id,SUM(i.quantity)/28 FROM sale_item i "
                        "JOIN sale s ON s.id=i.sale_id WHERE s.sold_at>=:start "
                        "AND s.sold_at<:end GROUP BY i.product_id"
                    ),
                    {
                        "start": datetime.combine(today - timedelta(days=28), time.min),
                        "end": datetime.combine(today, time.min),
                    },
                )
            ).all()
        )
        rows = (
            await c.execute(
                text(
                    "SELECT b.id,b.product_id,b.purchase_item_id,b.initial_quantity, "
                    "b.remaining_quantity,b.expiration_date,b.arrived_at,b.batch_no, "
                    "d.code,p.expiry_warning_days,b.store_id FROM inventory_batch b "
                    "JOIN product p ON p.id=b.product_id JOIN department d ON "
                    "d.id=p.department_id "
                    "JOIN purchase_item i ON i.id=b.purchase_item_id "
                    "JOIN purchase pur ON pur.id=i.purchase_id "
                    "WHERE pur.purchase_no LIKE 'PO%' OR pur.purchase_no LIKE 'HPO%' "
                    "ORDER BY b.expiration_date DESC,b.id DESC"
                )
            )
        ).all()
        on_hand = defaultdict(int)
        changes, item_changes, quantities, waste_logs = [], [], {}, []
        waste_total = 0
        for row in rows:
            bid, pid, item_id, _, remaining, expires, arrived, batch_no, dept, warning, sid = row
            sold_quantity = int(sold.get(bid, 0))
            expired = expires is not None and expires < today
            waste = max(1, round(sold_quantity * 0.025)) if expired else 0
            coverage = {"PRODUCE": 2.5, "MEAT": 1.5, "SEAFOOD": 1.0, "DELI": 1.0}[dept]
            target = max(4, math.ceil(float(demand.get(pid, 2)) * coverage))
            keep = 0 if expired else min(remaining, max(0, target - on_hand[pid]))
            on_hand[pid] += keep
            initial = max(1, sold_quantity + keep + waste)
            # 无销量的历史批次是一次最小损耗，当前零需求批次保留一件以闭合账本。
            if not expired and initial > sold_quantity + keep:
                keep += 1
            status = (
                "sold_out"
                if keep == 0
                else (
                    "near_expiry"
                    if expires and expires <= today + timedelta(days=warning or 0)
                    else "available"
                )
            )
            changes.append({"id": bid, "initial": initial, "remaining": keep, "status": status})
            item_changes.append({"id": item_id, "quantity": initial})
            quantities[bid] = initial
            if waste:
                waste_total += waste
                discarded_at = datetime.combine(expires + timedelta(days=1), time(7, 30))
                waste_logs.append(
                    {
                        "sid": sid,
                        "bid": bid,
                        "created": discarded_at,
                        "before": json.dumps({"remaining_quantity": waste, "status": "expired"}),
                        "after": json.dumps(
                            {
                                "remaining_quantity": 0,
                                "status": "sold_out",
                                "discarded_quantity": waste,
                            }
                        ),
                    }
                )
        await c.execute(
            text(
                "UPDATE inventory_batch SET "
                "initial_quantity=:initial,remaining_quantity=:remaining, "
                "status=:status WHERE id=:id"
            ),
            changes,
        )
        await c.execute(
            text(
                "UPDATE purchase_item SET "
                "quantity=:quantity,subtotal=unit_cost*:quantity WHERE id=:id"
            ),
            item_changes,
        )
        await c.execute(
            text(
                "UPDATE purchase p JOIN (SELECT purchase_id,SUM(subtotal) amount "
                "FROM purchase_item "
                "GROUP BY purchase_id) i ON i.purchase_id=p.id SET p.total_amount=i.amount"
            )
        )
        await c.execute(
            text(
                "UPDATE sale s JOIN (SELECT "
                "sale_id,SUM(original_unit_price*quantity) original, "
                "SUM(subtotal) amount,SUM(cost_subtotal) cost FROM sale_item "
                "GROUP BY sale_id) i "
                "ON i.sale_id=s.id SET "
                "s.original_total_amount=i.original,s.total_amount=i.amount, "
                "s.discount_amount=i.original-i.amount,s.total_cost=i.cost, "
                "s.gross_profit=i.amount-i.cost WHERE s.source='demo_seed'"
            )
        )
        await c.execute(
            text(
                "UPDATE product p JOIN (SELECT product_id,SUM(remaining_quantity) qty "
                "FROM inventory_batch GROUP BY product_id) b ON b.product_id=p.id "
                "SET p.stock_quantity=b.qty"
            )
        )

        # 从完整模拟账本重建库存流水，保留其他业务审计及全部单据。
        await c.execute(
            text(
                "DELETE l FROM operation_audit_log l JOIN inventory_batch b ON "
                "b.id=l.target_id "
                "JOIN purchase_item i ON i.id=b.purchase_item_id "
                "JOIN purchase p ON p.id=i.purchase_id WHERE l.module='inventory' "
                "AND l.target_type='inventory_batch' AND l.action IN "
                "('create_batch','sale_deduction','discard_expired') "
                "AND (p.purchase_no LIKE 'PO%' OR p.purchase_no LIKE 'HPO%')"
            )
        )
        logs = []
        for row in rows:
            bid, pid, item_id, _, _, expires, arrived, batch_no, _, _, sid = row
            logs.append(
                {
                    "sid": sid,
                    "bid": bid,
                    "action": "create_batch",
                    "created": arrived,
                    "before": None,
                    "after": json.dumps(
                        {
                            "remaining_quantity": quantities[bid],
                            "status": "available",
                            "batch_no": batch_no,
                            "product_id": pid,
                            "purchase_item_id": item_id,
                        }
                    ),
                    "reason": "デモ補正：需要に基づく入荷検収",
                }
            )
        deductions = (
            await c.execute(
                text(
                    "SELECT "
                    "i.id,i.inventory_batch_id,i.quantity,i.sale_id,s.sold_at,b.store_id "
                    "FROM sale_item i JOIN sale s ON s.id=i.sale_id "
                    "JOIN inventory_batch b ON b.id=i.inventory_batch_id "
                    "WHERE s.source='demo_seed' ORDER BY s.sold_at,s.id,i.id"
                )
            )
        ).all()
        for iid, bid, quantity, sale_id, sold_at, sid in deductions:
            if bid not in quantities:
                continue
            before = quantities[bid]
            quantities[bid] -= quantity
            if quantities[bid] < 0:
                raise RuntimeError("Negative inventory during replay")
            logs.append(
                {
                    "sid": sid,
                    "bid": bid,
                    "action": "sale_deduction",
                    "created": sold_at,
                    "before": json.dumps({"remaining_quantity": before}),
                    "after": json.dumps(
                        {
                            "remaining_quantity": quantities[bid],
                            "deducted_quantity": quantity,
                            "sale_id": sale_id,
                            "sale_item_id": iid,
                        }
                    ),
                    "reason": "デモ補正：POS販売による在庫減少",
                }
            )
        for log in waste_logs:
            log.update(action="discard_expired", reason="デモ：販売期限経過・朝の売場点検で廃棄")
            logs.append(log)
        insert = text(
            "INSERT INTO operation_audit_log "
            "(store_id,module,action,target_type,target_id,before_data,after_data,reason, "
            "created_at) "
            "VALUES(:sid,'inventory',:action,'inventory_batch',:bid,:before,:after,:reason,:created)"
        )
        for offset in range(0, len(logs), 1000):
            await c.execute(insert, logs[offset : offset + 1000])

        await c.execute(
            text(
                "UPDATE operation_audit_log l JOIN sale s ON s.id=l.target_id "
                "SET l.created_at=s.sold_at,l.after_data=JSON_SET(l.after_data, "
                "'$.total_amount',CAST(s.total_amount AS CHAR), "
                "'$.discount_amount',CAST(s.discount_amount AS CHAR)) "
                "WHERE l.module='sale' AND l.target_type='sale' AND s.source='demo_seed'"
            )
        )
        await c.execute(
            text(
                "UPDATE operation_audit_log l JOIN purchase p ON p.id=l.target_id "
                "SET l.created_at=IF(l.action='auto_receive',p.arrived_at,p.ordered_at), "
                "l.after_data=JSON_SET(l.after_data,'$.total_amount',CAST(p.total_amount AS CHAR)) "
                "WHERE l.module='purchase' AND l.target_type='purchase' "
                "AND (p.purchase_no LIKE 'PO%' OR p.purchase_no LIKE 'HPO%')"
            )
        )

        await c.execute(
            text(
                "UPDATE employee_detail d JOIN employee e ON e.id=d.employee_id "
                "SET d.gender=IF(MOD(CAST(SUBSTRING(e.employee_no,4) AS "
                "UNSIGNED),2)=0,'男','女') WHERE e.employee_no LIKE 'EMP%'"
            )
        )
        # 联络事项的正文不能声称全员已确认，却仍有未确认人员。
        await c.execute(
            text(
                "UPDATE contact_notice SET content=REPLACE(content, "
                "'全員の確認が完了したため、この連絡は終了しています。', "
                "'値札の更新後は売場の表示とレジ登録価格を照合してください。'), "
                "priority=IF(title LIKE '%冷蔵設備%', 'normal', priority) "
                "WHERE content LIKE '%半年分の運営シミュレーション%'"
            )
        )
        await c.execute(
            text(
                "UPDATE contact_notice_recipient r JOIN contact_notice n ON n.id=r.notice_id "
                "SET r.confirmed_at=NULL,r.read_at=IF(r.read_at>n.closed_at,NULL,r.read_at) "
                "WHERE n.status='withdrawn' "
                "AND n.content LIKE '%半年分の運営シミュレーション%'"
            )
        )
        await c.execute(
            text(
                "UPDATE contact_notice n JOIN (SELECT notice_id,COUNT(*) total, "
                "COUNT(confirmed_at) confirmed,MAX(confirmed_at) last_confirmed "
                "FROM contact_notice_recipient GROUP BY notice_id) r ON r.notice_id=n.id "
                "SET n.close_reason=IF(r.total=r.confirmed,'all_confirmed','deadline'), "
                "n.closed_at=IF(r.total=r.confirmed,r.last_confirmed,n.deadline_at), "
                "n.updated_at=IF(r.total=r.confirmed,r.last_confirmed,n.deadline_at) "
                "WHERE n.status='closed' "
                "AND n.content LIKE '%半年分の運営シミュレーション%'"
            )
        )
        employees = (await c.execute(text("SELECT id,name,role FROM employee ORDER BY id"))).all()
        for index, (eid, name, role) in enumerate(employees):
            birth = date(1980 + index % 16, 1 + index % 12, 8 + index % 15)
            hire = date(2016 + index % 7, 1 + index % 12, 1)
            await c.execute(
                text(
                    "UPDATE employee_detail SET gender=IF(gender='未填写',:gender,gender), "
                    "birth_date=COALESCE(birth_date,:birth), "
                    "hire_date=LEAST(hire_date,:hire),phone=COALESCE(phone,:phone), "
                    "address=COALESCE(address,:address) WHERE employee_id=:id"
                ),
                {
                    "id": eid,
                    "gender": "男" if index % 2 == 0 else "女",
                    "birth": birth,
                    "hire": hire,
                    "phone": f"090-0000-{index + 1001:04d}",
                    "address": f"東京都杉並区高円寺北2-0-{index + 1} デモ住宅（架空）",
                },
            )
            if name in ("初始店长", "本部管理者"):
                await c.execute(
                    text("UPDATE employee SET name=:name WHERE id=:id"),
                    {"id": eid, "name": "佐藤 健一" if role == "店长" else "山本 直子"},
                )
        await c.execute(
            text(
                "UPDATE store SET "
                "address=COALESCE(address,'東京都杉並区高円寺北2-0-1（デモ店舗）'), "
                "phone=COALESCE(phone,'03-0000-1001') WHERE store_no='DP0001'"
            )
        )
        # 在职人员不伪造离职日期或原因；档案建档时间不晚于模拟经营开始。
        await c.execute(
            text(
                "UPDATE employee_detail SET created_at=LEAST(created_at,hire_date), "
                "updated_at=:now WHERE employee_id IN (SELECT id FROM employee)"
            ),
            {"now": now},
        )
        await c.execute(
            text(
                "INSERT INTO "
                "operation_audit_log(store_id,module,action,target_type,target_id, "
                "after_data,reason,created_at) VALUES(1,'demo_seed',:marker,'store',1,:data, "
                "'架空データの整合性と在庫回転を校正',:now)"
            ),
            {
                "marker": MARKER,
                "now": now,
                "data": json.dumps(
                    {"signature": signature, "discarded": waste_total, "batch_count": len(rows)}
                ),
            },
        )
        print(
            f"Normalized {len(rows)} batches; historical waste: {waste_total}; "
            f"employee profiles: {len(employees)}"
        )


async def main():
    try:
        await normalize()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
