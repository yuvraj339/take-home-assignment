"""Database engine, sessions, and schema initialization."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    # Import models so SQLAlchemy registers their tables before create_all.
    from app.models import task, tenant  # noqa: F401
    from app.models.outbox import OutboxEvent  # noqa: F401
    from app.models.processed_message import ProcessedMessage  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
