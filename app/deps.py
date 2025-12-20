# File: /backend/app/deps.py
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_request_status_enum_checked = False


def _ensure_request_status_enum(db: Session) -> None:
    """Ensure the request_status enum has all values used by the application."""
    global _request_status_enum_checked
    if _request_status_enum_checked:
        return
    db.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'request_status') THEN
                    CREATE TYPE request_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');
                ELSIF NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'request_status'
                      AND e.enumlabel = 'CANCELLED'
                ) THEN
                    ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'CANCELLED';
                END IF;
            END$$;
            """
        )
    )
    db.commit()
    _request_status_enum_checked = True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        _ensure_request_status_enum(db)
        yield db
    finally:
        db.close()
