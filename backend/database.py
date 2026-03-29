from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

engine = create_async_engine(settings.postgres_dsn, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in [
            "ALTER TABLE questions ADD COLUMN IF NOT EXISTS section TEXT",
            "ALTER TABLE questions ADD COLUMN IF NOT EXISTS answer_cell VARCHAR(32)",
        ]:
            await conn.execute(text(stmt))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
