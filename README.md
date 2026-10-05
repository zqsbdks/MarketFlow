# MarketFlow 门店经营管理系统

面向日本超市业务的多门店演示项目，采用 **FastAPI + MySQL + Vue 3 + TypeScript**。
支持进货、批次库存、销售、折扣、废弃损耗、经营报表、员工管理和AI辅助查询。
这是个人学习与求职展示项目，数据为模拟数据，不代表真实门店经营结果。

维护日期：2026-10-05。发布版本见[CHANGELOG](CHANGELOG.md)，历史进度见
[项目状态](docs/PROJECT_STATUS.md)。本文说明当前行为，历史验收结果不等于线上运行保证。

## 功能

| 模块 | 当前行为 |
| --- | --- |
| 门店与总部 | 员工与所选门店决定读取范围；跨店业务只读，总部管理门店、员工并查看汇总 |
| 商品与供应商 | 商品分类、供应目录、价格、临期及低库存预警 |
| 订货计划 | 未来7天自动建议、人工覆盖、保底库存、结束编辑后保存 |
| 自动进货 | 每天日本时间12:00锁定两天后的计划并创建进货单；到货日签收生成批次 |
| 库存 | 批次剩余库存、保质期、临期状态及变更流水 |
| 销售与折扣 | 价格预览、折扣结账、批次扣减、成交价格与成本快照 |
| 商品废弃 | 人工废弃及过期自动废弃，保留原因、数量、批次成本和操作人 |
| 经营分析 | 销售、趋势、部门占比，可选损耗金额、数量及占营业额比例 |
| 员工与联络事项 | 员工资料、账号状态、通知范围、接收名单及确认状态 |
| AI辅助 | 按员工加密存储Key、会话历史与摘要，写操作须人工确认并继承业务权限 |

### 自动订货规则

最近28个完整日期，同星期几销量合计除以4并向上取整预测需求。
系统逐日模拟批次、保质期、待到货单及更早的计划，计算：

`建议量 = max(0, 当日预测销量 + 保底库存 - 当日预计可用库存)`

保底库存是预计销售后希望保留的余量，默认0，并非最低订货量。
人工修改优先，填写0表示不订；“恢复自动建议”删除人工覆盖。
例如10月5日12:00自动提交10月7日到货的计划；截止前可改，之后锁定，没有手动提交按钮。

键盘输入疑似重复按键、多输入0或明显超量时需确认。加减键可连续经过11、22，
结束编辑后保存，明显超量仍检查。自动建议至少50件，且超过预测日销量和上周同日销量
中较大值的5倍时标为橘红色：**仅提醒，不要求确认，不影响到时提交**。

低库存预警入口：**商品查询 → 商品详情 → 修改资料 → 低库存预警阈值**，
它与保底库存独立。废弃入口：**库存批次 → 商品废弃**。

## 目录和阅读顺序

```text
app/core/          配置、数据库、安全、缓存、门店隔离与调度
app/models/        SQLAlchemy模型与约束
app/schemas/       Pydantic输入校验及输出类型
app/crud/          数据库查询和写入
app/services/      权限、业务规则、事务编排
app/routers/       HTTP接口和依赖注入
app/dependencies/  当前员工、数据库会话
app/ai/            AI工具及服务商适配
app/main.py        应用工厂与ASGI入口
frontend/          Vue页面、API调用、类型、国际化与组件测试
alembic/versions/  数据库增量迁移
scripts/           初始化、数据生成、补齐与验收工具
tests/             隔离测试及可选MySQL测试
docs/              配置、阅读指南及历史验收
folder-alias.json  编辑器中文用途别名，不改变真实文件名
```

详见[代码阅读指南](docs/CODE_GUIDE.md)。新增ORM模型在app/models/__init__.py注册，
新增路由在app/routers/__init__.py挂载。

## 本地启动

需要Python 3.11+、Node.js 22+及已创建的独立MySQL数据库。Redis可选。
在项目根目录执行：

```powershell
python scripts/setup.py
# 修改生成的.env，填写本机数据库连接。已有.env不会覆盖。
.\.venv\Scripts\Activate.ps1
python -m scripts.check_database
python -m alembic upgrade head
# 首次创建店长按COMMANDS.md操作；已有数据库不用重建演示数据。
python -m uvicorn app.main:app --reload
```

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

前端通常为http://localhost:5173（以Vite输出为准），API文档为http://127.0.0.1:8000/docs。
默认Vite监听127.0.0.1:5173并代理/api到8000。更换端口或来源时同步核对CORS。
macOS/Linux使用python3 scripts/setup.py和source .venv/bin/activate。
VS Code也可运行“Setup: 克隆后初始化项目”任务。完整命令见[COMMANDS](COMMANDS.md)。
项目已有迁移历史，换电脑部署只执行upgrade head，不重新生成第一份迁移。

## 配置和依赖

[配置文档](docs/CONFIGURATION.md)解释.env.example、.env.deploy.example和前端变量。
真实.env、账号密码、AI Key及密钥不能提交Git。修改配置需重启服务；已有AI加密密钥勿随意更换。
登录主要使用HttpOnly Cookie；生产Cookie带Secure标记，必须通过HTTPS访问。
界面支持日文、英文、中文，业务日期统一Asia/Tokyo。

- requirements.txt：固定版本的生产直接依赖。
- requirements-dev.txt：生产依赖加固定版本的测试与质量工具。
- frontend/package-lock.json：前端安装快照，使用npm ci。
- python -m pip check：验证安装环境无依赖冲突。

## 后台任务和缓存

Windows本地以单Web进程设置APP_RUN_SCHEDULER=true；生产Web必须关闭调度，
由Compose独立scheduler执行。浏览器关闭不影响服务端任务，后端停机则无法准点执行。
独立调度器的信号处理面向Linux容器，Windows本地使用Web内嵌调度。

后台每小时刷新自动量；每天12:00提交截止计划并签收到货；00:05处理过期废弃及批次状态；
营业时间内每30分钟检查库存一致性。启动时补处理已到期任务。
目前独立scheduler_worker仅运行进货/库存任务；联络事项后台任务由启用调度的Web生命周期启动，
生产独立进程下联络事项仍在查询时补处理到期关闭。

Redis不可用或未配置时使用进程内查询缓存；无Redis时不同进程不共享缓存。
销量预测缓存24小时并按日本业务日期分键；历史销售报表缓存3分钟，当日报表实时。
库存、待到货量、人工计划和保底设置实时读取；权限校验不因缓存命中省略。
详见[缓存说明](docs/verification/BUSINESS_CACHE_REPORT.md)。

## 事务、权限和幂等

- X-Store-ID只选择读取范围，后端重新验证员工，不授权跨店写入。
- 销售、废弃、库存调整及签收采用事务和行锁，库存与审计记录一起写入。
- 商品、折扣修改使用expected_version，旧版本冲突返回409。
- 销售结账及废弃使用请求ID防止重复扣减。
- 每日计划具有门店/部门/到货日唯一约束，截止订单使用稳定请求ID、行锁和生成标记防重。
- 人工异常确认绑定员工、门店、商品、日期、数量，有效10分钟，并记录审计。

## 测试和质量

```powershell
python -m pip check
python -m ruff check .
python -m mypy app
python -m pytest
cd frontend
npm test
npm run build
```

普通测试使用替身或隔离SQLite并关闭调度。可选MySQL测试需RUN_MYSQL_TESTS=1；
部分读取现有演示库，部分创建临时测试库，运行前阅读对应测试，勿盲目对生产库执行。
CI包含后端质量、前端、容器和部分MySQL并发验证。历史结果在docs/verification，
精确测试数量随代码变化，以当前测试输出为准。

## 数据和部署

数据工具用途见[代码阅读指南](docs/CODE_GUIDE.md)。初始化时保存脚本输出的初始密码；
员工编号统一E加5位数字。各演示脚本有自己的去重和保护条件，不等于可以随意在生产库反复执行。
演示数据规模不代表已经验证的生产性能。

Docker部署在独立目录从.env.deploy.example创建.env，替换占位值并设置HTTPS域名：

```powershell
docker compose build
docker compose up -d mysql redis
docker compose run --rm backend python -m alembic upgrade head
docker compose up -d backend scheduler frontend
```

前端默认8080端口，由HTTPS入口转发。检查docker compose ps和/health/ready；
/health/live仅检查进程存活。升级前备份数据库，再升级迁移与容器；
不要使用会删除数据库卷的docker compose down -v。生产约束见[配置文档](docs/CONFIGURATION.md)。

## 项目边界与求职展示

项目可展示业务建模、权限、事务、并发、定时任务、缓存和自动化测试。
AI参与辅助开发，展示时应能解释关键流程与设计取舍；性能结论需实际测量。
自动订货是规则式预测，会受销量变化、废弃和到货延误影响，橘红标记不会阻止下单。

参考：[命名规范](NAMING.md)、[版本记录](CHANGELOG.md)、[代码阅读指南](docs/CODE_GUIDE.md)。
