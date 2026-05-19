"""Database initialization and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging

from config import settings
from .models import Base

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = settings.database_url

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Run Alembic database migrations."""
    try:
        from alembic.config import Config
        from alembic import command
        
        alembic_cfg = Config("migrations/alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed")
    except Exception as e:
        logger.warning(f"Could not run migrations: {e}. Using init_db instead.")
        init_db()


def dispose_engine() -> None:
    """Dispose of the database engine (for shutdown)."""
    engine.dispose()
    logger.info("Database engine disposed")
