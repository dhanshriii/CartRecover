
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import (
    Attribution,
    Campaign,
    Cart,
    Customer,
    MessageEvent,
    MessageTemplate,
    Order,
    SendAttempt,
)
from app.services.attribution_service import attribute_order


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_base_records(db, order_status="COMPLETED"):
    customer = Customer(
        customer_id="CUS-000001",
        first_name="Test",
        last_name="Customer",
        email="test@example.com",
        phone="9876543210",
        created_at=datetime(2026, 10, 1, 10, 0),
    )

    cart = Cart(
        cart_id="CART-2026-000001",
        customer_id=customer.customer_id,
        session_id=None,
        created_at=datetime(2026, 10, 20, 10, 0),
        updated_at=datetime(2026, 10, 20, 10, 0),
        last_activity_at=datetime(2026, 10, 20, 10, 0),
        status="PURCHASED",
        total_cents=50000,
    )

    order = Order(
        order_id="ORD-2026-000001",
        customer_id=customer.customer_id,
        cart_id=cart.cart_id,
        ordered_at=datetime(2026, 10, 25, 12, 0),
        subtotal_cents=55000,
        discount_cents=5000,
        total_cents=50000,
        status=order_status,
    )

    db.add_all([customer, cart, order])
    db.commit()

    return customer, cart, order


def create_sent_message(
    db,
    customer,
    cart,
    campaign_id,
    send_id,
    click_at=None,
    window_days=7,
    send_status="SENT",
):
    campaign = Campaign(
        campaign_id=campaign_id,
        campaign_name=f"Campaign {campaign_id}",
        channel="EMAIL",
        variant="REMINDER_24H",
        status="ACTIVE",
        scheduled_at=datetime(2026, 10, 20, 10, 0),
        attribution_window_days=window_days,
    )

    template = MessageTemplate(
        template_id=f"TPL-{campaign_id}",
        campaign_id=campaign_id,
        channel="EMAIL",
        subject="Complete your purchase",
        body="Your cart is waiting.",
        variant="REMINDER_24H",
        is_active=True,
    )

    send = SendAttempt(
        send_id=send_id,
        customer_id=customer.customer_id,
        cart_id=cart.cart_id,
        campaign_id=campaign_id,
        template_id=template.template_id,
        channel="EMAIL",
        scheduled_at=datetime(2026, 10, 20, 10, 0),
        attempted_at=(
            datetime(2026, 10, 20, 10, 1)
            if send_status == "SENT"
            else None
        ),
        status=send_status,
            suppression_reason=(
                "TEST_SUPPRESSION"
                if send_status == "SUPPRESSED"
                else None
            ),
    )

    db.add_all([campaign, template, send])
    db.commit()

    if click_at is not None:
        event = MessageEvent(
            message_event_id=f"EVT-{send_id}",
            send_id=send_id,
            event_type="CLICKED",
            event_at=click_at,
        )
        db.add(event)
        db.commit()

    return send


def test_valid_click_creates_attribution(db):
    customer, cart, order = create_base_records(db)

    click_at = order.ordered_at - timedelta(hours=2)

    send = create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
        click_at=click_at,
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-001",
    )

    assert result["status"] == "ATTRIBUTED"
    assert result["send_id"] == send.send_id
    assert result["attribution_id"] == "ATTR-001"
    assert result["attributed_revenue_cents"] == 50000
    assert result["is_primary"] is True

    saved = db.query(Attribution).filter_by(
        attribution_id="ATTR-001"
    ).first()

    assert saved is not None
    assert saved.order_id == order.order_id
    assert saved.send_id == send.send_id


def test_latest_click_wins(db):
    customer, cart, order = create_base_records(db)

    earlier_click = order.ordered_at - timedelta(days=2)
    later_click = order.ordered_at - timedelta(hours=1)

    create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
        click_at=earlier_click,
    )

    create_sent_message(
        db,
        customer,
        cart,
        "CMP-002",
        "SEND-002",
        click_at=later_click,
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-002",
    )

    assert result["status"] == "ATTRIBUTED"
    assert result["send_id"] == "SEND-002"
    assert result["campaign_id"] == "CMP-002"


def test_order_without_click_is_not_attributed(db):
    customer, cart, order = create_base_records(db)

    create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-003",
    )

    assert result["status"] == "NOT_ATTRIBUTED"
    assert result["reason"] == "NO_ELIGIBLE_CLICKED_MESSAGE"

    assert db.query(Attribution).count() == 0


def test_click_outside_attribution_window_is_rejected(db):
    customer, cart, order = create_base_records(db)

    old_click = order.ordered_at - timedelta(days=8)

    create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
        click_at=old_click,
        window_days=7,
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-004",
    )

    assert result["status"] == "NOT_ATTRIBUTED"
    assert result["reason"] == "NO_ELIGIBLE_CLICKED_MESSAGE"


@pytest.mark.parametrize("send_status", ["SCHEDULED", "FAILED", "SUPPRESSED"])
def test_non_sent_message_cannot_receive_attribution(db, send_status):
    customer, cart, order = create_base_records(db)

    create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
        click_at=order.ordered_at - timedelta(hours=1),
        send_status=send_status,
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-005",
    )

    assert result["status"] == "NOT_ATTRIBUTED"
    assert result["reason"] == "NO_ELIGIBLE_CLICKED_MESSAGE"


def test_existing_primary_attribution_is_not_duplicated(db):
    customer, cart, order = create_base_records(db)

    send = create_sent_message(
        db,
        customer,
        cart,
        "CMP-001",
        "SEND-001",
        click_at=order.ordered_at - timedelta(hours=1),
    )

    existing = Attribution(
        attribution_id="ATTR-EXISTING",
        order_id=order.order_id,
        send_id=send.send_id,
        attributed_at=order.ordered_at,
        attributed_revenue_cents=order.total_cents,
        attribution_window_days=7,
        is_primary=True,
        decision_reason="Existing attribution",
    )

    db.add(existing)
    db.commit()

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-NEW",
    )

    assert result["status"] == "ALREADY_ATTRIBUTED"
    assert result["attribution_id"] == "ATTR-EXISTING"

    assert db.query(Attribution).filter_by(
        order_id=order.order_id
    ).count() == 1


def test_non_completed_order_is_not_attributed(db):
    customer, cart, order = create_base_records(
        db,
        order_status="PENDING",
    )

    result = attribute_order(
        db,
        order.order_id,
        "ATTR-006",
    )

    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == "ORDER_NOT_COMPLETED"


def test_missing_order_returns_not_found(db):
    result = attribute_order(
        db,
        "ORD-DOES-NOT-EXIST",
        "ATTR-007",
    )

    assert result["status"] == "NOT_FOUND"
    assert result["reason"] == "ORDER_NOT_FOUND"


def test_blank_attribution_id_raises_error(db):
    _, _, order = create_base_records(db)

    with pytest.raises(ValueError, match="attribution_id is required"):
        attribute_order(
            db,
            order.order_id,
            "   ",
        )
