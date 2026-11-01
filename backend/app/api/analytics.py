
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    Customer,
    Cart,
    SendAttempt,
    Order,
    Attribution,
    MessageEvent,
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def safe_percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


@router.get("/overview")
def get_analytics_overview(db: Session = Depends(get_db)):

    # Customer metrics
    total_customers = (
        db.query(func.count(Customer.customer_id)).scalar() or 0
    )

    # Cart metrics
    total_carts = (
        db.query(func.count(Cart.cart_id)).scalar() or 0
    )

    abandoned_carts = (
        db.query(func.count(Cart.cart_id))
        .filter(Cart.status == "ABANDONED")
        .scalar() or 0
    )

    recovered_carts = (
        db.query(func.count(Cart.cart_id))
        .filter(Cart.status == "RECOVERED")
        .scalar() or 0
    )

    purchased_carts = (
        db.query(func.count(Cart.cart_id))
        .filter(Cart.status == "PURCHASED")
        .scalar() or 0
    )

    # Messaging metrics
    total_send_attempts = (
        db.query(func.count(SendAttempt.send_id)).scalar() or 0
    )

    sent_messages = (
        db.query(func.count(SendAttempt.send_id))
        .filter(SendAttempt.status == "SENT")
        .scalar() or 0
    )

    scheduled_messages = (
        db.query(func.count(SendAttempt.send_id))
        .filter(SendAttempt.status == "SCHEDULED")
        .scalar() or 0
    )

    suppressed_messages = (
        db.query(func.count(SendAttempt.send_id))
        .filter(SendAttempt.status == "SUPPRESSED")
        .scalar() or 0
    )

    failed_messages = (
        db.query(func.count(SendAttempt.send_id))
        .filter(SendAttempt.status == "FAILED")
        .scalar() or 0
    )

    # Suppression reason breakdown
    suppression_rows = (
        db.query(
            SendAttempt.suppression_reason,
            func.count(SendAttempt.send_id)
        )
        .filter(SendAttempt.status == "SUPPRESSED")
        .group_by(SendAttempt.suppression_reason)
        .all()
    )

    suppression_reasons = {
        reason or "UNSPECIFIED": count
        for reason, count in suppression_rows
    }

    # Order metrics
    completed_orders = (
        db.query(func.count(Order.order_id))
        .filter(Order.status == "COMPLETED")
        .scalar() or 0
    )

    # Attribution metrics
    attributed_orders = (
        db.query(func.count(func.distinct(Attribution.order_id)))
        .filter(Attribution.is_primary.is_(True))
        .scalar() or 0
    )

    attributed_revenue = (
        db.query(func.sum(Attribution.attributed_revenue_cents))
        .filter(Attribution.is_primary.is_(True))
        .scalar() or 0
    )

    # Engagement metrics
    delivered_events = (
        db.query(func.count(MessageEvent.message_event_id))
        .filter(MessageEvent.event_type == "DELIVERED")
        .scalar() or 0
    )

    opened_events = (
        db.query(func.count(MessageEvent.message_event_id))
        .filter(MessageEvent.event_type == "OPENED")
        .scalar() or 0
    )

    clicked_events = (
        db.query(func.count(MessageEvent.message_event_id))
        .filter(MessageEvent.event_type == "CLICKED")
        .scalar() or 0
    )

    # Business metrics
    abandoned_cohort = abandoned_carts + recovered_carts

    return {
        "customers": {
            "total": total_customers
        },
        "carts": {
            "total": total_carts,
            "currently_abandoned": abandoned_carts,
            "recovered": recovered_carts,
            "purchased": purchased_carts,
            "recovery_rate_percent": safe_percentage(
                recovered_carts, abandoned_cohort
            )
        },
        "messaging": {
            "total_attempts": total_send_attempts,
            "sent": sent_messages,
            "scheduled": scheduled_messages,
            "suppressed": suppressed_messages,
            "failed": failed_messages,
            "suppression_rate_percent": safe_percentage(
                suppressed_messages, total_send_attempts
            ),
            "suppression_reasons": suppression_reasons,
            "delivery_events": delivered_events,
            "open_events": opened_events,
            "click_events": clicked_events
        },
        "orders": {
            "completed": completed_orders,
            "attributed_orders": attributed_orders,
            "attributed_order_rate_percent": safe_percentage(
                attributed_orders, completed_orders
            ),
            "attributed_revenue_paise": int(attributed_revenue)
        },
        "measurement_notes": [
            "Attributed revenue is not necessarily incremental revenue.",
            "Recovery rate is a snapshot ratio, not a cohort-based historical recovery rate.",
            "Engagement metrics count events, not unique customers or messages.",
            "Revenue is stored in paise despite legacy column names ending in _cents.",
            "Suppression reasons are grouped from actual suppressed send attempts."
        ]
    }
