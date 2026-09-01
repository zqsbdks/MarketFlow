"""对 .env 中配置的数据库执行只读连通性检查。"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import async_engine


async def check_database() -> None:
    """连接目标数据库并同时验证服务器和当前数据库名称。"""

    url = make_url(settings.database_url)
    if url.username == "username" or url.database in {None, "dbname"}:
        raise RuntimeError(".env 仍是示例数据库配置，请先填写 APP_DATABASE_URL")
    if not (url.username or "").isascii() or not (url.password or "").isascii():
        raise RuntimeError(
            "MySQL 用户名或密码包含当前驱动无法编码的字符，请改用 ASCII 字符；"
            "若包含 @、:、/、# 等符号，还需在数据库 URL 中进行百分号编码"
        )

    async with async_engine.connect() as connection:
        result = await connection.execute(text("SELECT DATABASE()"))
        database_name = result.scalar_one()
    await async_engine.dispose()
    print(f"[OK] MySQL 连接成功，当前数据库：{database_name}")


if __name__ == "__main__":
    try:
        asyncio.run(check_database())
    except Exception as exc:
        print(f"[ERROR] 数据库连接失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
