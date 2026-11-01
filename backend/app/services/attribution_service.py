
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.entities import (
    Attribution,
    Campaign,
    MessageEvent,
    Order,
    SendAttempt,
)


def attribute_order(
    db: Session,
    order_id: str,
    attribution_id: str,
) -> dict:
    """
    Attribute a completed order to the most recent eligible clicked
    recovery message.

    Rules:
    - Only SENT messages qualify.
    - Customer and cart must match.
    - CLICKED event must occur before the order.
    - Order must be within the campaign attribution window.
    - Latest click wins.
    - Only one primary attribution is created per order.

    This function does not modify the order or send records.
    """

    if not attribution_id or not attribution_id.strip():
        raise ValueError("attribution_id is required.")

    order = (
        db.query(Order)
        .filter(Order.order_id == order_id)
        .first()
    )

    if order is None:
        return {
            "status": "NOT_FOUND",
            "order_id": order_id,
            "reason": "ORDER_NOT_FOUND",
        }

    if order.status != "COMPLETED":
        return {
            "status": "NOT_ELIGIBLE",
            "order_id": order_id,
            "reason": "ORDER_NOT_COMPLETED",
        }

    # Prevent a second primary attribution for this order.
    existing_primary = (
        db.query(Attribution)
        .filter(
            Attribution.order_id == order_id,
            Attribution.is_primary.is_(True),
        )
        .first()
    )

    if existing_primary:
        return {
            "status": "ALREADY_ATTRIBUTED",
            "order_id": order_id,
            "attribution_id": existing_primary.attribution_id,
            "send_id": existing_primary.send_id,
            "reason": "PRIMARY_ATTRIBUTION_ALREADY_EXISTS",
        }

    if order.cart_id is None:
        return {
            "status": "NOT_ATTRIBUTED",
            "order_id": order_id,
            "reason": "ORDER_HAS_NO_CART",
        }

    # Find sent messages for the same customer and cart.
    sends = (
        db.query(SendAttempt, Campaign)
        .join(
            Campaign,
            SendAttempt.campaign_id == Campaign.campaign_id,
        )
        .filter(
            SendAttempt.customer_id == order.customer_id,
            SendAttempt.cart_id == order.cart_id,
            SendAttempt.status == "SENT",
        )
        .all()
    )

    candidates = []

    for send, campaign in sends:

        window_start = order.ordered_at - timedelta(
            days=campaign.attribution_window_days
        )

        clicks = (
            db.query(MessageEvent)
            .filter(
                MessageEvent.send_id == send.send_id,
                MessageEvent.event_type == "CLICKED",
                MessageEvent.event_at >= window_start,
                MessageEvent.event_at <= order.ordered_at,
            )
            .all()
        )

        for click in clicks:
            candidates.append(
                (
                    click.event_at,
                    send.send_id,
                    send,
                    campaign,
                )
            )

    if not candidates:
        return {
            "status": "NOT_ATTRIBUTED",
            "order_id": order_id,
            "reason": "NO_ELIGIBLE_CLICKED_MESSAGE",
        }

    # Latest click wins. Send ID provides deterministic tie-breaking.
    candidates.sort(
        key=lambda item: (-item[0].timestamp(), item[1])
    )

    click_at, send_id, selected_send, selected_campaign = (
        candidates[0]
    )

    # Prevent duplicate attribution for the same order and send.
    existing_pair = (
        db.query(Attribution)
        .filter(
            Attribution.order_id == order_id,
            Attribution.send_id == send_id,
        )
        .first()
    )

    if existing_pair:
        return {
            "status": "ALREADY_ATTRIBUTED",
            "order_id": order_id,
            "attribution_id": existing_pair.attribution_id,
            "send_id": send_id,
            "reason": "ORDER_SEND_ATTRIBUTION_ALREADY_EXISTS",
        }

    attribution = Attribution(
        attribution_id=attribution_id,
        order_id=order_id,
        send_id=send_id,
        attributed_at=order.ordered_at,
        attributed_revenue_cents=order.total_cents,
        attribution_window_days=(
            selected_campaign.attribution_window_days
        ),
        is_primary=True,
        decision_reason=(
            f"LAST_CLICK: clicked at {click_at.isoformat()}; "
            f"order within "
            f"{selected_campaign.attribution_window_days}-day window"
        ),
    )

    db.add(attribution)
    db.commit()
    db.refresh(attribution)

    return {
        "status": "ATTRIBUTED",
        "order_id": order_id,
        "attribution_id": attribution.attribution_id,
        "send_id": attribution.send_id,
        "campaign_id": selected_campaign.campaign_id,
        "attributed_revenue_cents": (
            attribution.attributed_revenue_cents
        ),
        "attribution_window_days": (
            attribution.attribution_window_days
        ),
        "is_primary": attribution.is_primary,
        "click_at": click_at.isoformat(),
        "decision_reason": attribution.decision_reason,
    }
