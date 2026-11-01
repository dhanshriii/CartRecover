
import pytest
from sqlalchemy import inspect, text

from app.database import Base, engine, create_tables
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
    MessageEvent,
)


EXPECTED_TABLES = {
    "customers",
    "consents",
    "sessions",
    "carts",
    "cart_lines",
    "campaigns",
    "message_templates",
    "send_attempts",
    "orders",
    "attributions",
    "cart_events",
    "message_events",
}


def test_all_expected_models_are_registered():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_create_tables():
    create_tables()

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(actual_tables)


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()

    assert result == 1


def test_foreign_keys_are_enabled():
    with engine.connect() as connection:
        result = connection.execute(
            text("PRAGMA foreign_keys")
        ).scalar()

    assert result == 1
