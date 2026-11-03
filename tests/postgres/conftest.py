from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_URL = os.environ.get(
    "STRAWBERRY_ALCHEMY_PG_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/strawberry_alchemy",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "postgres: requires a live Postgres (CI service or local)")


@pytest.fixture(scope="session")
def pg_url() -> str:
    return POSTGRES_URL


@pytest.fixture
async def pg_engine(pg_url: str) -> AsyncEngine:
    # asyncpg `timeout` is connect timeout (seconds); keeps CI from hanging forever.
    engine = create_async_engine(pg_url, pool_pre_ping=True, connect_args={"timeout": 10})
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Postgres unavailable at {pg_url}: {exc}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
