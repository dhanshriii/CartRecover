
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import (
    Customer,
    Consent,
    Cart,
    Campaign,
    MessageTemplate,
    SendAttempt,
)
from app.services.campaign_service import schedule_recovery


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
def campaign_data(db):
    now = datetime(2026, 10, 30, 12, 0, 0)

    customer = Customer(
        customer_id="CUS-CAM-001",
        first_name="Test",
        last_name="Customer",
        email="campaign@example.com",
        phone="9999999999",
        created_at=now - timedelta(days=30),
    )

    cart = Cart(
        cart_id="CART-CAM-001",
        customer_id=customer.customer_id,
        session_id=None,
        created_at=now - timedelta(hours=5),
        updated_at=now - timedelta(hours=4),
        last_activity_at=now - timedelta(hours=4),
        status="ABANDONED",
        total_cents=100000,
    )

    consent = Consent(
        consent_id="CON-CAM-001",
        customer_id=customer.customer_id,
        channel="EMAIL",
        status="GRANTED",
        effective_from=now - timedelta(days=10),
        effective_to=None,
        source="TEST",
    )

    campaign = Campaign(
        campaign_id="CMP-CAM-001",
        campaign_name="Test Recovery Campaign",
        channel="EMAIL",
        variant="REMINDER_24H",
        status="ACTIVE",
        scheduled_at=now - timedelta(days=1),
        attribution_window_days=7,
    )

    template = MessageTemplate(
        template_id="TPL-CAM-001",
        campaign_id=campaign.campaign_id,
        channel="EMAIL",
        subject="You left something behind",
        body="Complete your purchase.",
        variant="REMINDER_24H",
        is_active=True,
    )

    db.add_all([
        customer,
        cart,
        consent,
        campaign,
        template,
    ])

    db.commit()

    return now, customer, cart, campaign, template


def test_eligible_cart_is_scheduled(db, campaign_data):
    now, customer, cart, campaign, template = campaign_data

    result = schedule_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
        send_id="SEND-CAM-001",
    )

    assert result["status"] == "SCHEDULED"
    assert result["campaign_id"] == campaign.campaign_id

    attempt = db.query(SendAttempt).filter_by(
        send_id="SEND-CAM-001"
    ).first()

    assert attempt is not None
    assert attempt.status == "SCHEDULED"
    assert attempt.attempted_at is None


def test_withdrawn_consent_suppresses_campaign(db, campaign_data):
    now, customer, cart, campaign, template = campaign_data

    original_consent = db.query(Consent).filter_by(
        consent_id="CON-CAM-001"
    ).first()

    original_consent.effective_to = now - timedelta(minutes=30)

    withdrawal = Consent(
        consent_id="CON-CAM-002",
        customer_id=customer.customer_id,
        channel="EMAIL",
        status="WITHDRAWN",
        effective_from=now - timedelta(minutes=30),
        effective_to=None,
        source="TEST",
    )

    db.add(withdrawal)
    db.commit()

    result = schedule_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
        send_id="SEND-CAM-002",
    )

    assert result["status"] == "SUPPRESSED"
    assert "NO_ACTIVE_CONSENT" in result["suppression_reason"]

    attempt = db.query(SendAttempt).filter_by(
        send_id="SEND-CAM-002"
    ).first()

    assert attempt.status == "SUPPRESSED"


def test_frequency_cap_suppresses_campaign(db, campaign_data):
    now, customer, cart, campaign, template = campaign_data

    previous_send = SendAttempt(
        send_id="SEND-CAM-PREV",
        customer_id=customer.customer_id,
        cart_id=cart.cart_id,
        campaign_id=campaign.campaign_id,
        template_id=template.template_id,
        channel="EMAIL",
        scheduled_at=now - timedelta(hours=2),
        attempted_at=now - timedelta(hours=2),
        status="SENT",
        suppression_reason=None,
    )

    db.add(previous_send)
    db.commit()

    result = schedule_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=now,
        send_id="SEND-CAM-003",
    )

    assert result["status"] == "SUPPRESSED"
    assert "FREQUENCY_CAP_24H" in result["suppression_reason"]


def test_quiet_hours_reschedule_to_8am(db, campaign_data):
    now, customer, cart, campaign, template = campaign_data

    quiet_time = datetime(2026, 10, 30, 22, 30, 0)

    result = schedule_recovery(
        db=db,
        cart=cart,
        channel="EMAIL",
        evaluated_at=quiet_time,
        send_id="SEND-CAM-004",
    )

    assert result["status"] == "SCHEDULED"
    assert result["scheduled_at"] == "2026-10-31T08:00:00"

    attempt = db.query(SendAttempt).filter_by(
        send_id="SEND-CAM-004"
    ).first()

    assert attempt.scheduled_at == datetime(2026, 10, 31, 8, 0, 0)
