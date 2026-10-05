# 环境配置与依赖说明

维护日期：2026-10-05。字段来源为 `app/core/config.py`，不要把示例占位值当作真实配置。

## 文件选择

| 文件 | 用途 |
| --- | --- |
| `.env.example` | 本地开发模板，初始化脚本只在不存在真实.env时复制 |
| `.env` | 本机运行配置，Git忽略；修改值后重启服务 |
| `.env.deploy.example` | Linux Docker Compose部署模板，应在独立部署目录使用 |
| `frontend/.env.example` | 浏览器API相对路径；VITE_变量会公开，不能放密钥 |

Settings读取根目录.env（UTF-8）及APP_环境变量，进程环境变量优先。
Compose的MYSQL_变量与APP_PORT由容器配置消费，并非Settings字段。
配置对象在进程内缓存，保存.env不会让正在运行的服务自动重新加载配置。

## 后端变量

| 变量 | 作用及注意事项 |
| --- | --- |
| `APP_PROJECT_NAME` | OpenAPI显示名称 |
| `APP_ENVIRONMENT` | development、test、production；production额外执行安全校验 |
| `APP_DEBUG` | 开发调试标记，生产必须false |
| `APP_API_V1_PREFIX` | 默认/api/v1；变更时同时核对前端代理与API地址 |
| `APP_DATABASE_URL` | mysql+aiomysql://账号:密码@主机:端口/库名?charset=utf8mb4 |
| `APP_DATABASE_ECHO` | SQL回显，生产必须false |
| `APP_LOG_LEVEL` | INFO、WARNING等日志级别 |
| `APP_LOG_FILE` | 留空仅控制台；填写路径后启用10MB轮转及5个备份文件 |
| `APP_SECRET_KEY` | JWT及人工数量确认签名密钥，至少32字符；修改后旧凭据不能继续使用 |
| `APP_JWT_ALGORITHM` | HS256、HS384或HS512，与签名配置一致 |
| `APP_ACCESS_TOKEN_EXPIRE_MINUTES` | 登录令牌有效分钟数，示例为10080（7天） |
| `APP_INITIAL_MANAGER_PASSWORD` | bootstrap_manager脚本首次创建店长使用，不是每次登录读取的密码 |
| `APP_REDIS_URL` | 可选Redis地址；为空时进程内缓存，不提供跨进程共享 |
| `APP_REDIS_MAX_CONNECTIONS` | 每进程连接池上限，默认10 |
| `APP_REDIS_TIMEOUT` | Redis连接及读写超时秒数，默认5 |
| `APP_RUN_SCHEDULER` | 本地单Web进程可true；生产Web必须false，Compose独立scheduler运行任务 |
| `APP_AI_KEY_ENCRYPTION_KEY` | Fernet加密密钥，用于保存员工AI服务商Key，不能随意轮换 |
| `APP_CORS_ORIGINS` | JSON数组；本地填写localhost和127.0.0.1的前端来源，生产填写实际HTTPS域名 |

真实.env的已有数据库、密钥和密码应保留，不需要因文档更新而更换。
MySQL密码含@、冒号、斜杠等字符时，URL中的密码需百分号编码；MYSQL_PASSWORD仍填写原密码。

生成新部署的密钥（只在自己的终端执行并妥善保存）：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

AI加密密钥不是服务商API Key。服务商Key在前端AI设置中按员工录入。
加密密钥丢失后，旧服务商Key无法解密，需员工重新录入。

## Compose专用变量

- APP_PORT：前端宿主机端口，默认8080。
- MYSQL_DATABASE、MYSQL_USER、MYSQL_PASSWORD：容器首次初始化业务数据库及账号。
- MYSQL_ROOT_PASSWORD：MySQL管理员密码，不用于普通业务连接。
- APP_DATABASE_URL的主机为mysql，APP_REDIS_URL主机为redis，这是Compose服务名。
- 持久化卷已存在时，修改MYSQL_PASSWORD并不会自动更改库内用户密码。
- 业务日期统一Asia/Tokyo；Compose MySQL指定+09:00，本地MySQL需自行核对会话/服务器时区。

生产模式拒绝默认签名密钥、调试、SQL回显、通配CORS、Web内嵌调度，以及无效AI加密密钥。
生产Cookie使用Secure，因此需要HTTPS。缓存故障回退数据库不等于依赖健康检查成功：
如果配置了Redis但不可用，/health/ready仍会报告Redis异常。

## 前端变量

`VITE_API_BASE_URL=/api/v1`：开发由Vite代理到127.0.0.1:8000，生产由Nginx代理。
默认Vite只监听127.0.0.1:5173。需要其他设备访问时，应明确配置监听地址及对应CORS来源。
修改VITE_变量后需重启开发服务；生产需重新构建前端。

## 依赖管理

生产安装requirements.txt，开发安装requirements-dev.txt；后者使用-r包含前者。
直接依赖已固定当前验证版本；并非全部传递依赖锁文件，完整环境快照可运行
`python scripts/freeze_requirements.py`生成。不要直接用pip freeze覆盖手工维护的分组清单。
当前测试客户端依赖httpx2，与现有FastAPI/Starlette组合一致，不能仅因旧教程使用httpx而替换。
前端使用npm ci读取package-lock.json，不以删除锁文件方式解决安装问题。

只修改用途注释无需重装依赖；版本有变化时才安装并运行pip check、测试与构建。
