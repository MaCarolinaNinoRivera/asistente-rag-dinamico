from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Una sesión por petición. Si la petición falla antes de confirmar, al cerrarse se deshace todo."""
    async with AsyncSessionLocal() as session:
        yield session
