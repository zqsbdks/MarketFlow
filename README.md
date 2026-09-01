# FastAPI 通用异步项目骨架

这是一个可直接复制的新项目基础结构，包含 FastAPI、Pydantic Settings、
SQLAlchemy 2.x 异步 MySQL 会话、Alembic 异步迁移、可选 Redis 缓存、JWT、密码哈希、
CORS 和统一异常响应。

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

模板不携带固定的空迁移。请为每个新项目使用一个空的专用数据库，添加并导入 ORM
模型后，先生成该项目自己的第一份迁移，再执行升级：

```powershell
# 第一次也使用这条命令；迁移说明可以写中文
python -m alembic revision --autogenerate -m "create initial tables"

# 检查生成文件无误后再应用
python -m alembic upgrade head

# 回退一个版本
python -m alembic downgrade -1
```

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

日志默认输出到控制台。设置 `APP_LOG_FILE="logs/app.log"` 后，会同时启用
10 MB 轮转文件日志并保留最近 5 份。

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
