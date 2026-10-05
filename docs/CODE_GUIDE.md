# 代码阅读与业务流程指南

建议结合接口文档和隔离测试阅读，不从文件名猜测真实权限。
文件中文别名保存在folder-alias.json，仅改变编辑器用途提示，不影响Python导入、路由或Git文件名。

## 后端调用链

`app/main.py`创建应用 → `core/lifespan.py`初始化缓存与任务 → `routers/`绑定HTTP接口 →
`dependencies/auth.py`识别当前员工 → `core/store_policy.py`配置门店范围 →
`services/`执行权限与业务规则 → `crud/`及ORM进行数据库访问 → `schemas/`组装响应。

会话由请求依赖创建并关闭。读取通常不提交；写入服务或调用方显式提交。
异常由会话依赖回滚，不能在已提交数据库后把缓存失败当作业务写入失败。
门店读取范围与员工所属门店分开保存，查看其他店铺不代表可以修改它。

## 自动订货

1. `services/replenishment.py`读取最近28个完整日期的同星期销量预测。
2. `calculate_replenishment`实时读取商品、批次、待到货单和人工计划。
3. `simulate_replenishment`按日期移除过期库存、加入到货、扣除预计销量并计算补货。
4. `services/purchase_planning.py`把结果与上周销量、已有到货、人工/自动标记组合为前端表格。
5. `services/purchase_plan_submission.py`保存人工计划、保底设置、确认审计；行锁后再次检查截止时间。
6. `core/purchase_scheduler.py`每小时刷新自动量，截止后合并自动量与人工覆盖并生成订单。

`purchase_plan.quantities`仅保存人工覆盖，包含0；`automatic_quantities`单独保存系统快照。
合并时人工值优先。恢复自动用quantity=null移除覆盖，而不是写入0。
后台生成订单保留原截止时间和稳定幂等ID，避免重试重复生成。
最终订货量不能缓存，因为库存、待到货和人工设置会改变。

`quantity_confirmation.py`只针对人工输入：返回异常原因或已签名确认结果。
首次异常检查返回saved=false，不写入数量；确认凭据有效10分钟并绑定具体操作。
加减键跳过重复数字和多输入0的误按提醒，明显超量仍检查。
系统自动量只在前端超过近期销量参考5倍且至少50件时标橘红色，到时正常提交。

## 销售、库存与废弃

销售入口在`services/sales.py`、`crud/sales.py`；实际扣减对应库存批次，成交价格、折扣和成本
保留快照。先检查库存并获取锁，再记录销售与库存流水，不能仅扣Product.stock_quantity。

废弃入口在`services/inventory_discards.py`：先校验员工与本店/部门，再读取可处理批次。
`allocate`按指定批次或最早到期顺序分配，`preview_discard`只预览，真正提交必须再次加锁并检查。
`record_discard`在同一事务写损耗单、明细、批次扣减和流水；调用方决定提交。
过期自动处理复用库存与审计规则，不假冒人工员工身份。
`services/discard_analysis.py`使用实际批次成本，按废弃日期统计；损耗不自动扣入销售毛利润。

## 报表与缓存

`services/reports.py`每次校验账号、日期和部门，`crud/reports.py`聚合查询。
全店金额按销售单汇总，商品数量按明细汇总，避免关联明细重复累计订单金额。
部门报表仅累计该部门明细，不能把整单金额全部算入一个部门。

`core/cache.py`维护HTTP查询缓存和business_cache装饰器。
缓存键不包含数据库会话对象；包含数据库、函数、查询参数与必要门店范围。
预测按业务日期分键，历史报表仅缓存结束日期早于今天的查询；金额恢复为Decimal。
缓存失败回退查询，数据库查询失败不缓存。历史导入后需清理对应命名空间或等待过期。

## AI和联络事项

AI入口在`services/ai_chat.py`，持久历史在`services/ai_memory.py`。
客户端不负责证明历史可信，服务端按员工和门店验证会话归属。
AI只读工具继承权限，写工具先返回待确认操作；确认时再次校验业务数据。
历史摘要是参考数据，历史金额需要重新查询。defer_commit让工具内部提交延后到整轮会话成功。

联络事项见`services/contact_notices.py`和`core/contact_notice_scheduler.py`。
确认名单按发布范围生成；员工只看自己的确认状态，发布者及管理者按权限查看名单。
部署注意：独立scheduler_worker目前只运行进货/库存任务；联络事项关闭也会在查询时补处理。

## 前端

`frontend/src/api/`统一HTTP调用，`types/api.ts`维护类型，`i18n.ts`负责三种界面语言。
`PurchasePlanner.vue`维护三个不同状态：已保存数量、编辑草稿、人工确认弹窗。
草稿必须独立保留，不能被每秒截止时钟重绘或其他格子的保存刷新覆盖。
按输入来源区分键盘/粘贴与加减键，失去焦点或回车后保存，不按每个输入字符提交。
UI数据检查不能代替后端权限与校验。

## 数据与测试工具

| 工具 | 用途 |
| --- | --- |
| scripts/setup.py | 初始化本地环境，已有.env不覆盖 |
| scripts/bootstrap_manager.py | 显式创建初始店长，不在启动时自动生成 |
| scripts/seed_japanese_demo.py | 首店日文演示数据，读取脚本保护条件后再执行 |
| scripts/seed_multi_store.py | 补齐门店与账号 |
| scripts/seed_store_scale_demo.py | 为其他门店生成近半年不同规模的模拟业务数据 |
| scripts/complete_demo_employee_profiles.py | 补齐模拟员工资料 |
| scripts/normalize_employee_numbers.py | 演示员工编号统一为E加5位数字 |
| scripts/verify_store_scale_demo.py | 库存平衡、跨店关联和金额验收 |
| tests/store_fixtures.py | 隔离数据库与门店样本，避免普通测试访问真实演示库 |

历史迁移、历史验收报告中的旧编号属于当时快照，不应批量替换历史记录。
修改代码后运行对应测试；事务/并发结论还应参考可选MySQL测试，SQLite不能覆盖全部锁行为。
