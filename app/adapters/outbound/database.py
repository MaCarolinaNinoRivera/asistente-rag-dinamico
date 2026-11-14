from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.utils.logger import logger

from urllib.parse import urlsplit

url = urlsplit(settings.DATABASE_URL)

logger.info(
    "🔌 [DEBUG DATABASE] scheme=%r | user=%r | host=%r | port=%r | "
    "database=%r | password_presente=%s",
    url.scheme,
    url.username,
    url.hostname,
    url.port,
    url.path,
    bool(url.password),
)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": "require"}
)

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Una sesión por petición. Si la petición falla antes de confirmar, al cerrarse se deshace todo."""
    async with AsyncSessionLocal() as session:
        yield session
