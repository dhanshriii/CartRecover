
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Project root
BASE_DIR = Path(__file__).resolve().parents[2]

# Database location
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'cartrecover.db'}"

# SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Enable SQLite foreign-key enforcement
@event.listens_for(engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Base model
class Base(DeclarativeBase):
    pass


# Database sessions
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from app.models.entities import (
        Customer,
        Consent,
        CustomerSession,
        Cart,
        CartLine,
        Campaign,
        MessageTemplate,
        SendAttempt,
        Order,
        Attribution,
        CartEvent,
        MessageEvent
    )

    Base.metadata.create_all(bind=engine)


