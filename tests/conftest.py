"""pytest 进程级测试环境配置。

该文件会在收集测试模块前加载，因此可以在应用 Settings 首次实例化之前覆盖环境
变量，保证单元测试不会意外依赖本地 Redis 或生产密钥。
"""

import os

# Redis 在单元测试中关闭；数据库 Engine 虽然会构造，但只有集成测试才实际连接。
os.environ.setdefault("APP_REDIS_URL", "")
# 降低测试输出噪声，同时保留警告和错误日志。
os.environ.setdefault("APP_LOG_LEVEL", "WARNING")
# 使用足够长且固定的测试密钥，使 JWT 测试可重复并避免读取本地真实密钥。
os.environ.setdefault(
    "APP_SECRET_KEY",
    "unit-test-secret-key-that-is-longer-than-thirty-two-bytes",
)
