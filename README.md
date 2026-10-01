# MarketFlow 门店经营管理系统

FastAPI + MySQL 后端与 Vue 3 前端组成的门店经营系统，支持进货、库存批次、
销售、折扣、报表和需要人工确认的 AI 辅助操作。

## 快速开始

克隆后，在 VS Code 中按 `Ctrl+Shift+P`，依次选择 `Tasks: Run Task` 和
`Setup: 克隆后初始化项目`。该跨平台任务会创建 `.env`、`.venv`、随机密钥，安装
全部依赖，并尝试检查 MySQL 连接。数据库尚未配置时只会显示提示，不影响依赖安装。
完成后修改 `.env` 中的项目名称与 MySQL 连接，再运行 `Database: 检查连接`。

Windows 启动服务：

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

不使用 VS Code 任务时，可以直接运行：

```powershell
python scripts/setup.py
```

macOS/Linux 使用同一脚本：`python3 scripts/setup.py`，启动服务前执行
`source .venv/bin/activate`。

详细的手动命令见 [COMMANDS.md](COMMANDS.md)。

打开 `http://127.0.0.1:8000/docs`。`/health/live` 只检查进程是否存活，
`/health/ready` 会实际检查数据库和已启用的 Redis；原 `/health` 地址继续保留。

常用开发、测试、迁移和依赖管理命令统一收录在
[COMMANDS.md](COMMANDS.md)。

变量、函数、类和文件的命名规则及常用英文词表见 [NAMING.md](NAMING.md)。

## 目录职责

```text
app/
├── core/          # 配置、数据库、安全、缓存、中间件、生命周期
├── models/        # SQLAlchemy ORM 模型
├── schemas/       # Pydantic 请求/响应模型
├── crud/          # 数据访问逻辑
├── dependencies/  # FastAPI Depends 依赖
├── routers/       # API 路由
└── main.py        # 应用工厂与 ASGI 入口
alembic/           # 数据库迁移脚本
tests/             # 单元测试和可选的集成测试
scripts/           # 可重复执行的项目自动化脚本
```

每增加一个 ORM 模型，都要在 `app/models/__init__.py` 中导入。这样 Alembic 的
`--autogenerate` 才能发现它。每增加一个业务路由，都在 `app/routers/__init__.py`
中挂载到 `api_router`。

为防止模板连接到已有数据库时误生成删表操作，Alembic 自动迁移只管理已经导入
`Base.metadata` 的表。需要删除表时应编写明确的迁移脚本并人工复核。

## 数据库迁移

Alembic 与应用共同读取 `.env` 中的 `APP_DATABASE_URL`，无需在 `alembic.ini`
中重复配置密码。

项目已有完整迁移历史。部署已有项目时只执行升级，不要重新生成“第一份迁移”：

```powershell
python -m alembic upgrade head

# 回退一个版本
python -m alembic downgrade -1
```

只有修改 ORM 结构、准备新版本时才使用 `revision --autogenerate`，且必须人工检查迁移。

项目默认使用 MySQL。将 `.env` 配置为异步 `aiomysql` 驱动 URL：

```dotenv
APP_DATABASE_URL="mysql+aiomysql://user:password@localhost:3306/dbname?charset=utf8mb4"
```

密码包含 `@`、`:`、`/`、`#` 等字符时，需要先进行 URL 编码。不要让不同项目共用
同一个数据库；已有数据库中的 `alembic_version` 可能属于另一条迁移历史。

## 配置约定

所有环境变量统一使用 `APP_` 前缀。`APP_ENVIRONMENT` 可设为 `development`、
`test` 或 `production`。生产模式会拒绝调试模式、SQL 回显、默认密钥和通配 CORS，
避免开发配置被误带到线上。Redis 默认关闭；只有设置
`APP_REDIS_URL` 后才会创建连接。生产环境应设置真实的 CORS 来源、关闭调试与
SQL 输出，并替换 `APP_SECRET_KEY`。

## 容器部署

1. 将 `.env.deploy.example` 复制为 `.env`，设置强 MySQL 密码、随机 `APP_SECRET_KEY`、
   独立的 `APP_AI_KEY_ENCRYPTION_KEY`、真实域名和 CORS 来源。数据库 URL 的密码须
   与 `MYSQL_PASSWORD` 一致。加密密钥丢失将使已保存的员工 AI Key 无法解密。
2. 在目标服务器执行 `docker compose build` 和 `docker compose up -d mysql redis`。
3. 待数据库健康后，执行 `docker compose run --rm backend python -m alembic upgrade head`。
4. 执行 `docker compose up -d backend scheduler frontend`，再检查
   `docker compose ps`、`docker compose logs backend scheduler` 和 `/health/ready`。

`frontend` 默认映射宿主机 8080 端口。生产环境必须通过 HTTPS 入口访问；
生产 Cookie 带 `Secure` 标记，直接以 HTTP 访问将无法保持登录。仅开放 HTTPS
入口和必要的 SSH 端口，勿将 MySQL、Redis 或后端 8000 端口直接暴露到公网。
浏览器登录保存在 HttpOnly Cookie 中，页面刷新后无需重新登录；AI API Key 经服务端
加密后按员工保存，首次配置后无需每次输入。升级前曾存于浏览器的旧 Key 不会自动
上传，需要员工重新配置一次。导航栏及登录页可切换日语、英语、中文和日夜模式；
默认日语、夜间模式，选择会在本浏览器中保留。服务端业务时间和页面默认查询时间
均按日本时间计算。
定时任务只在单独的 `scheduler` 容器运行，Web 容器通过
`APP_RUN_SCHEDULER=false` 禁用任务；不要同时启动第二个调度实例。
业务日期和定时任务按 `Asia/Tokyo` 计算；Compose 中 MySQL 也使用 UTC+09:00，
以使数据库自动生成的创建/更新时间与业务时间一致。
首次启动后按 [COMMANDS.md](COMMANDS.md) 创建初始店长账号。

升级时先备份 MySQL 数据卷，再拉取代码、重新构建镜像、执行 `alembic upgrade head`，
最后更新服务。不要使用 `docker compose down -v`，那会删除数据库卷。

日志默认输出到控制台。设置 `APP_LOG_FILE="logs/app.log"` 后，会同时启用
10 MB 轮转文件日志并保留最近 5 份。

## 并发与重复提交保护

- 销售扣库存、人工调整库存和进货签收使用数据库事务及行锁，避免超卖和重复签收。
- 商品资料与折扣规则响应包含 `version`；修改时前端回传 `expected_version`，旧版本提交返回 `409`。
- 销售单、进货单和供应商编号由 `business_sequence` 表在行锁内分配，并保留数据库唯一约束。
- 收银结账和创建进货单使用客户端 UUID 作为幂等请求 ID，网络重试不会重复创建或重复扣库存。
- 自动签收、批次状态刷新和库存一致性检查使用 Redis 分布式锁。即使误启动多个调度实例，
  同一项任务同一时间也只会由一个实例执行；生产环境仍建议只运行一个 `scheduler` 容器。

## 测试与代码质量

```powershell
python -m pytest
python -m ruff check .
python -m mypy app
```

默认测试不会连接真实数据库。需要运行 MySQL 集成测试时：

```powershell
$env:RUN_MYSQL_TESTS="1"
python -m pytest -m integration
```
