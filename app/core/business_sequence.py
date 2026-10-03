"""并发安全的业务编号分配工具。"""

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Insert

from app.models.business_sequence import BusinessSequence


async def next_business_sequence(sequence_key: str, db: AsyncSession) -> int:
    """原子分配下一个流水号；同一计数器的并发请求会按行锁依次执行。"""

    dialect_name = db.bind.dialect.name if db.bind is not None else "mysql"
    values = {"sequence_key": sequence_key, "current_value": 0}
    create_statement: Insert
    if dialect_name == "sqlite":
        create_statement = sqlite_insert(BusinessSequence).values(**values).on_conflict_do_nothing()
    else:
        create_statement = mysql_insert(BusinessSequence).values(**values).prefix_with("IGNORE")
    await db.execute(create_statement)

    counter = await db.scalar(
        select(BusinessSequence)
        .where(BusinessSequence.sequence_key == sequence_key)
        .with_for_update()
    )
    if counter is None:
        raise RuntimeError("业务编号计数器创建失败")
    counter.current_value += 1
    await db.flush()
    return counter.current_value


__all__ = ["next_business_sequence"]
