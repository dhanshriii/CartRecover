
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Customer, Consent, Cart, Order
from app.services.recovery_engine import evaluate_recovery


@pytest.fixture
def db():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(test_engine)

    TestingSession = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )

    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def recovery_data(db):
    now = datetime(2026, 10, 30, 12, 0, 0)

    customer = Customer(
        customer_id="CUS-TEST-001",
        first_name="Test",
        last_name="Customer",
        email="test@example.com",
        phone="9999999999",
        created_at=now - timedelta(days=30),
    )

    cart = Cart(
        cart_id="CART-TEST-001",
        customer_id=customer.customer_id,
        session_id=None,
        created_at=now - timedelta(hours=5),
        updated_at=now - timedelta(hours=4),
        last_activity_at=now - timedelta(hours=4),
        status="ABANDONED",
        total_cents=100000,
    )

    consent = Consent(
        consent_id="CON-TEST-001",
        customer_id=customer.customer_id,
        channel="EMAIL",
        status="GRANTED",
        effective_from=now - timedelta(days=10),
        effective_to=None,
        source="TEST",
    )

    db.add_all([customer, cart, consent])
    db.commit()

    return now, customer, cart


def test_eligible_cart_is_approved(db, recovery_data):
    now, customer, cart = recovery_data

    result = evaluate_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
    )

    assert result["eligible"] is True
    assert result["decision"] == "ELIGIBLE"
    assert result["reasons"] == ["ELIGIBLE"]


def test_missing_consent_suppresses_cart(db, recovery_data):
    now, customer, cart = recovery_data

    db.query(Consent).filter(
        Consent.customer_id == customer.customer_id
    ).delete()
    db.commit()

    result = evaluate_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
    )

    assert result["eligible"] is False
    assert "NO_ACTIVE_CONSENT" in result["reasons"]


def test_withdrawn_consent_suppresses_cart(db, recovery_data):
    now, customer, cart = recovery_data

    consent = db.query(Consent).filter(
        Consent.customer_id == customer.customer_id
    ).first()

    consent.effective_to = now - timedelta(minutes=30)

    withdrawal = Consent(
        consent_id="CON-TEST-002",
        customer_id=customer.customer_id,
        channel="EMAIL",
        status="WITHDRAWN",
        effective_from=now - timedelta(minutes=30),
        effective_to=None,
        source="TEST",
    )

    db.add(withdrawal)
    db.commit()

    result = evaluate_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
    )

    assert result["eligible"] is False
    assert "NO_ACTIVE_CONSENT" in result["reasons"]


def test_cart_below_abandonment_threshold_is_rejected(
    db, recovery_data
):
    now, customer, cart = recovery_data

    cart.last_activity_at = now - timedelta(minutes=60)
    db.commit()

    result = evaluate_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
    )

    assert result["eligible"] is False
    assert "ABANDONMENT_THRESHOLD_NOT_REACHED" in result["reasons"]


def test_completed_order_blocks_recovery(db, recovery_data):
    now, customer, cart = recovery_data

    order = Order(
        order_id="ORD-TEST-001",
        customer_id=customer.customer_id,
        cart_id=cart.cart_id,
        ordered_at=now - timedelta(minutes=30),
        subtotal_cents=100000,
        discount_cents=0,
        total_cents=100000,
        status="COMPLETED",
    )

    db.add(order)
    db.commit()

    result = evaluate_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
    )

    assert result["eligible"] is False
    assert "CART_ALREADY_PURCHASED" in result["reasons"]


def test_invalid_channel_raises_error(db, recovery_data):
    now, customer, cart = recovery_data

    with pytest.raises(ValueError):
        evaluate_recovery(
            db=db,
            cart=cart,
            channel="WHATSAPP",
            evaluated_at=now,
        )
