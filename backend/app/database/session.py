"""
Database session management.
Supports PostgreSQL (primary) and SQLite (dev fallback).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.config import settings
from app.database.models import Base

import os
from pathlib import Path

# Fix relative SQLite paths to always resolve to the backend directory
# regardless of where uvicorn is started from.
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///./"):
    db_name = db_url.replace("sqlite:///./", "")
    backend_dir = Path(__file__).resolve().parent.parent.parent
    db_url = f"sqlite:///{backend_dir / db_name}"

# Fix for Render: SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Create engine with appropriate settings per DB type
if db_url.startswith("sqlite"):
    from sqlalchemy.pool import NullPool
    from sqlalchemy import event

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        poolclass=NullPool,
        echo=settings.DEBUG,
    )
    # Enable non-blocking WAL mode and 30s busy timeout for high-concurrency SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
else:
    pool_size = getattr(settings, "DB_POOL_SIZE", 25)
    max_overflow = getattr(settings, "DB_MAX_OVERFLOW", 35)
    pool_timeout = getattr(settings, "DB_POOL_TIMEOUT", 20)
    pool_recycle = getattr(settings, "DB_POOL_RECYCLE", 1800)
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=settings.DEBUG,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


import time
import sqlalchemy

def create_tables():
    """Create all tables (use Alembic for production migrations)."""
    global engine, SessionLocal
    retries = 5
    for i in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            print("[OK] Database tables created successfully.")
            break
        except Exception as e:
            if i < retries - 1:
                print(f"[WARNING] Database not ready yet, retrying in 3 seconds... ({i+1}/{retries})")
                time.sleep(3)
            else:
                print(f"[WARNING] Primary database unavailable ({e}). Falling back to local SQLite to keep server operational.")
                try:
                    backend_dir = Path(__file__).resolve().parent.parent.parent
                    fallback_url = f"sqlite:///{backend_dir / 'giotag.db'}"
                    engine = create_engine(fallback_url, connect_args={"check_same_thread": False, "timeout": 30.0})
                    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                    Base.metadata.create_all(bind=engine)
                    print("[OK] Local SQLite fallback database initialized.")
                except Exception as ex:
                    print(f"[ERROR] SQLite fallback error: {ex}")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
