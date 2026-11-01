
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import (
    Campaign,
    Customer,
    MessageTemplate,
    SendAttempt,
    Cart,
)
from app.services.recovery_engine import evaluate_recovery


QUIET_START = 21
QUIET_END = 8


def is_quiet_hour(value: datetime) -> bool:
    """Return True between 9 PM and 8 AM."""

    return value.hour >= QUIET_START or value.hour < QUIET_END


def next_allowed_time(value: datetime) -> datetime:
    """Move a scheduled message to the next allowed sending time."""

    if value.hour >= QUIET_START:
        return (value + timedelta(days=1)).replace(
            hour=QUIET_END,
            minute=0,
            second=0,
            microsecond=0,
        )

    if value.hour < QUIET_END:
        return value.replace(
            hour=QUIET_END,
            minute=0,
            second=0,
            microsecond=0,
        )

    return value


def get_active_campaign(
    db: Session,
    channel: str,
    evaluated_at: datetime,
):
    """Select the earliest eligible active campaign for a channel."""

    return (
        db.query(Campaign)
        .filter(
            Campaign.channel == channel,
            Campaign.status == "ACTIVE",
            Campaign.scheduled_at <= evaluated_at,
        )
        .order_by(Campaign.scheduled_at.asc(), Campaign.campaign_id.asc())
        .first()
    )


def get_active_template(
    db: Session,
    campaign: Campaign,
):
    """Find an active template matching the campaign's channel and variant."""

    return (
        db.query(MessageTemplate)
        .filter(
            MessageTemplate.campaign_id == campaign.campaign_id,
            MessageTemplate.channel == campaign.channel,
            MessageTemplate.variant == campaign.variant,
            MessageTemplate.is_active.is_(True),
        )
        .order_by(MessageTemplate.template_id.asc())
        .first()
    )


def schedule_recovery(
    db: Session,
    cart: Cart,
    channel: str,
    evaluated_at: datetime,
    send_id: str,
) -> dict:
    """
    Re-evaluate recovery eligibility and create an auditable send attempt.

    This function schedules messages. It does NOT dispatch email or SMS.
    Actual delivery requires a messaging-provider integration.
    """

    channel = channel.upper()

    if not send_id or not send_id.strip():
        raise ValueError("send_id is required.")

    customer = db.query(Customer).filter(
        Customer.customer_id == cart.customer_id
    ).first()

    if customer is None:
        raise ValueError("Cart customer does not exist.")

    campaign = get_active_campaign(
        db=db,
        channel=channel,
        evaluated_at=evaluated_at,
    )

    if campaign is None:
        raise ValueError(
            f"No active {channel} campaign is available."
        )

    template = get_active_template(db, campaign)

    if template is None:
        raise ValueError(
            f"No active template exists for campaign {campaign.campaign_id}."
        )

    # Recheck eligibility immediately before creating the attempt.
    decision = evaluate_recovery(
        db=db,
        cart=cart,
        channel=channel,
        evaluated_at=evaluated_at,
    )

    # Check that the customer has a usable destination.
    contact_available = (
        bool(customer.email)
        if channel == "EMAIL"
        else bool(customer.phone)
    )

    reasons = list(decision["reasons"])

    if not contact_available:
        reasons.append("MISSING_CONTACT_DETAIL")

    eligible = decision["eligible"] and contact_available

    if not eligible:
        attempt = SendAttempt(
            send_id=send_id,
            customer_id=cart.customer_id,
            cart_id=cart.cart_id,
            campaign_id=campaign.campaign_id,
            template_id=template.template_id,
            channel=channel,
            scheduled_at=evaluated_at,
            attempted_at=evaluated_at,
            status="SUPPRESSED",
            suppression_reason=";".join(reasons),
        )

        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        return {
            "send_id": attempt.send_id,
            "cart_id": cart.cart_id,
            "campaign_id": campaign.campaign_id,
            "template_id": template.template_id,
            "channel": channel,
            "status": "SUPPRESSED",
            "scheduled_at": attempt.scheduled_at.isoformat(),
            "suppression_reason": reasons,
            "message": "Recovery attempt suppressed.",
        }

    scheduled_at = max(evaluated_at, campaign.scheduled_at)

    # Respect quiet hours.
    if is_quiet_hour(scheduled_at):
        scheduled_at = next_allowed_time(scheduled_at)

    attempt = SendAttempt(
        send_id=send_id,
        customer_id=cart.customer_id,
        cart_id=cart.cart_id,
        campaign_id=campaign.campaign_id,
        template_id=template.template_id,
        channel=channel,
        scheduled_at=scheduled_at,
        attempted_at=None,
        status="SCHEDULED",
        suppression_reason=None,
    )

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return {
        "send_id": attempt.send_id,
        "cart_id": cart.cart_id,
        "campaign_id": campaign.campaign_id,
        "template_id": template.template_id,
        "channel": channel,
        "status": "SCHEDULED",
        "scheduled_at": scheduled_at.isoformat(),
        "suppression_reason": None,
        "message": (
            "Recovery message scheduled. "
            "No external message has been dispatched."
        ),
    }
