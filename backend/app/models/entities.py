from datetime import datetime

from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text,
    CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Consent(Base):
    __tablename__ = "consents"

    consent_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'SMS')"),
        CheckConstraint("status IN ('GRANTED', 'WITHDRAWN')"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from"
        ),
        Index(
            "ix_consent_customer_channel",
            "customer_id", "channel", "effective_from"
        ),
    )


class CustomerSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at"),
    )


class Cart(Base):
    __tablename__ = "carts"

    cart_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.session_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    total_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ABANDONED', 'PURCHASED', 'RECOVERED')"
        ),
        CheckConstraint("total_cents >= 0"),
        CheckConstraint("updated_at >= created_at"),
        CheckConstraint("last_activity_at >= created_at"),
        Index("ix_cart_customer", "customer_id"),
        Index("ix_cart_status_activity", "status", "last_activity_at"),
    )


class CartLine(Base):
    __tablename__ = "cart_lines"

    cart_line_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.cart_id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(String(30), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("unit_price_cents >= 0"),
        CheckConstraint("line_total_cents >= 0"),
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    campaign_name: Mapped[str] = mapped_column(String(150), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    variant: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attribution_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7
    )

    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'SMS')"),
        CheckConstraint(
            "status IN ('DRAFT', 'SCHEDULED', 'ACTIVE', 'COMPLETED')"
        ),
        CheckConstraint("attribution_window_days > 0"),
    )


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    template_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )


class SendAttempt(Base):
    __tablename__ = "send_attempts"

    send_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.cart_id"), nullable=False
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("message_templates.template_id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    suppression_reason: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'SMS')"),
        CheckConstraint(
            "status IN ('SCHEDULED', 'SENT', 'SUPPRESSED', 'FAILED')"
        ),
        CheckConstraint(
            "(status = 'SUPPRESSED' AND suppression_reason IS NOT NULL) "
            "OR status != 'SUPPRESSED'"
        ),
    )


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    cart_id: Mapped[str | None] = mapped_column(
        ForeignKey("carts.cart_id")
    )
    ordered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("subtotal_cents >= 0"),
        CheckConstraint("discount_cents >= 0"),
        CheckConstraint("total_cents >= 0"),
        CheckConstraint("total_cents = subtotal_cents - discount_cents"),
    )


class Attribution(Base):
    __tablename__ = "attributions"

    attribution_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id"), nullable=False
    )
    send_id: Mapped[str] = mapped_column(
        ForeignKey("send_attempts.send_id"), nullable=False
    )
    attributed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attributed_revenue_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    attribution_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "send_id"),
        CheckConstraint("attributed_revenue_cents >= 0"),
        CheckConstraint("attribution_window_days > 0"),
    )


class CartEvent(Base):
    __tablename__ = "cart_events"

    event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.cart_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_cart_event_cart_time", "cart_id", "event_at"),
    )


class MessageEvent(Base):
    __tablename__ = "message_events"

    message_event_id: Mapped[str] = mapped_column(
        String(30), primary_key=True
    )
    send_id: Mapped[str] = mapped_column(
        ForeignKey("send_attempts.send_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('DELIVERED', 'BOUNCED', 'OPENED', 'CLICKED')"
        ),
        Index("ix_message_event_send_time", "send_id", "event_at"),
    )