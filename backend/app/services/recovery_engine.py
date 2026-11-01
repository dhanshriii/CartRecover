
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import (
    Cart,
    Consent,
    Order,
    SendAttempt,
)


# Keep these values aligned with backend/generator/generate.py
ABANDONMENT_MINUTES = 180
MAX_SENDS_24H = 1
MAX_SENDS_7D = 2

SUPPORTED_CHANNELS = {"EMAIL", "SMS"}


def _get_active_consent(
    db: Session,
    customer_id: str,
    channel: str,
    evaluated_at: datetime,
):
    """
    Return the latest consent record effective at evaluated_at.

    A customer is opted in only when the latest effective record
    has status GRANTED.
    """

    consent = (
        db.query(Consent)
        .filter(
            Consent.customer_id == customer_id,
            Consent.channel == channel,
            Consent.effective_from <= evaluated_at,
            (
                (Consent.effective_to.is_(None))
                | (Consent.effective_to > evaluated_at)
            ),
        )
        .order_by(
            Consent.effective_from.desc(),
            Consent.consent_id.desc(),
        )
        .first()
    )

    if consent and consent.status == "GRANTED":
        return consent

    return None


def _get_recent_sent_count(
    db: Session,
    customer_id: str,
    evaluated_at: datetime,
    window: timedelta,
) -> int:
    """
    Count successful sends across ALL channels within a time window.

    Only SENT attempts count toward frequency caps.
    """

    cutoff = evaluated_at - window

    return (
        db.query(SendAttempt)
        .filter(
            SendAttempt.customer_id == customer_id,
            SendAttempt.status == "SENT",
            SendAttempt.attempted_at.isnot(None),
            SendAttempt.attempted_at >= cutoff,
            SendAttempt.attempted_at <= evaluated_at,
        )
        .count()
    )


def evaluate_recovery(
    db: Session,
    cart: Cart,
    channel: str,
    evaluated_at: datetime,
    abandonment_threshold_minutes: int = ABANDONMENT_MINUTES,
    max_sends_24h: int = MAX_SENDS_24H,
    max_sends_7d: int = MAX_SENDS_7D,
) -> dict:
    """
    Evaluate whether a cart is eligible for recovery.

    Checks:
    1. Supported communication channel.
    2. Cart lifecycle status.
    3. Abandonment threshold.
    4. Completed purchase.
    5. Active channel consent.
    6. Rolling 24-hour frequency cap.
    7. Rolling 7-day frequency cap.

    This function does not send messages or modify database records.
    It returns an auditable decision with reasons.
    """

    channel = channel.upper()

    if channel not in SUPPORTED_CHANNELS:
        raise ValueError(
            f"Unsupported channel: {channel}. "
            "Allowed channels are EMAIL and SMS."
        )

    if abandonment_threshold_minutes <= 0:
        raise ValueError("Abandonment threshold must be positive.")

    if max_sends_24h < 0 or max_sends_7d < 0:
        raise ValueError("Frequency caps cannot be negative.")

    reasons = []

    # 1. Cart lifecycle status
    if cart.status in {"PURCHASED", "RECOVERED"}:
        reasons.append("CART_NOT_RECOVERABLE")

    # 2. Abandonment threshold
    abandonment_time = cart.last_activity_at + timedelta(
        minutes=abandonment_threshold_minutes
    )

    if evaluated_at < abandonment_time:
        reasons.append("ABANDONMENT_THRESHOLD_NOT_REACHED")

    # 3. Check whether a completed order already exists.
    completed_order = (
        db.query(Order)
        .filter(
            Order.cart_id == cart.cart_id,
            Order.status == "COMPLETED",
            Order.ordered_at <= evaluated_at,
        )
        .first()
    )

    if completed_order:
        reasons.append("CART_ALREADY_PURCHASED")

    # 4. Check the latest effective consent for this channel.
    active_consent = _get_active_consent(
        db=db,
        customer_id=cart.customer_id,
        channel=channel,
        evaluated_at=evaluated_at,
    )

    if active_consent is None:
        reasons.append("NO_ACTIVE_CONSENT")

    # 5. Check rolling frequency caps across email and SMS.
    sent_last_24h = _get_recent_sent_count(
        db=db,
        customer_id=cart.customer_id,
        evaluated_at=evaluated_at,
        window=timedelta(hours=24),
    )

    sent_last_7d = _get_recent_sent_count(
        db=db,
        customer_id=cart.customer_id,
        evaluated_at=evaluated_at,
        window=timedelta(days=7),
    )

    if sent_last_24h >= max_sends_24h:
        reasons.append("FREQUENCY_CAP_24H")

    elif sent_last_7d >= max_sends_7d:
        reasons.append("FREQUENCY_CAP_7D")

    eligible = len(reasons) == 0

    return {
        "cart_id": cart.cart_id,
        "customer_id": cart.customer_id,
        "channel": channel,
        "decision": "ELIGIBLE" if eligible else "SUPPRESSED",
        "eligible": eligible,
        "reasons": reasons if reasons else ["ELIGIBLE"],
        "evaluated_at": evaluated_at.isoformat(),
        "abandonment_time": abandonment_time.isoformat(),
        "abandonment_threshold_minutes": abandonment_threshold_minutes,
        "active_consent_id": (
            active_consent.consent_id if active_consent else None
        ),
        "sent_last_24h": sent_last_24h,
        "sent_last_7d": sent_last_7d,
        "frequency_caps": {
            "max_24h": max_sends_24h,
            "max_7d": max_sends_7d,
        },
    }
