"""
YottaFlex abandoned-cart recovery synthetic data generator.

Run from repository root:
  python backend/generator/generate.py --reset --scale 0.1
  python backend/generator/generate.py --reset
  python backend/generator/generate.py --reset --seed 20261022

Uses the project's SQLAlchemy models and database.py.
Money is stored in integer paise (legacy column names end in _cents).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Base, engine, SessionLocal
from app.models.entities import (
    Customer, Consent, CustomerSession, Cart, CartLine, Campaign,
    MessageTemplate, SendAttempt, Order, Attribution, CartEvent,
    MessageEvent
)


SEED_DEFAULT = 20261022
NOW_DEFAULT = datetime(2026, 10, 30, 12, 0, 0)

HISTORY_DAYS = 90
ABANDONMENT_MINUTES = 180
ATTRIBUTION_DAYS = 7

MAX_SENDS_24H = 1
MAX_SENDS_7D = 2

QUIET_START = 21
QUIET_END = 8

PRODUCTS = [
    ("PRD-001", "Wireless Earbuds", 249900, 0.22),
    ("PRD-002", "Mechanical Keyboard", 459900, 0.13),
    ("PRD-003", "USB-C Hub", 189900, 0.16),
    ("PRD-004", "Smart Watch", 699900, 0.09),
    ("PRD-005", "Laptop Stand", 129900, 0.12),
    ("PRD-006", "Power Bank", 219900, 0.11),
    ("PRD-007", "Bluetooth Speaker", 329900, 0.08),
    ("PRD-008", "Webcam", 279900, 0.09),
]

FIRST_NAMES = [
    "Aarav", "Isha", "Kabir", "Anaya", "Vivaan", "Diya",
    "Arjun", "Meera", "Rohan", "Aditi", "Neel", "Sara",
    "Reyansh", "Kiara", "Ishaan", "Tara"
]

LAST_NAMES = [
    "Shah", "Patil", "Kulkarni", "Deshmukh", "Mehta",
    "Joshi", "Rao", "Pawar", "Sharma", "Khan", "Iyer",
    "Nair", "Gupta", "More"
]

SOURCES = [
    "WEB", "MOBILE_APP", "MOBILE_WEB", "PAID_SEARCH", "ORGANIC"
]

DEVICES = [
    "ANDROID", "IOS", "WINDOWS_CHROME", "MAC_SAFARI", "TABLET"
]


def iso(dt):
    return dt.isoformat(sep=" ")


def active_consent(consents, customer_id, channel, at):
    """Return consent state at a particular timestamp."""
    rows = consents.get((customer_id, channel), [])

    active = False

    for row in sorted(rows, key=lambda x: x["effective_from"]):
        if (
            row["effective_from"] <= at
            and (
                row["effective_to"] is None
                or at < row["effective_to"]
            )
        ):
            active = row["status"] == "GRANTED"

    return active


def is_quiet_hour(dt):
    return dt.hour >= QUIET_START or dt.hour < QUIET_END


def next_allowed_time(dt):
    if dt.hour >= QUIET_START:
        return (
            dt + timedelta(days=1)
        ).replace(
            hour=QUIET_END,
            minute=0,
            second=0,
            microsecond=0
        )

    if dt.hour < QUIET_END:
        return dt.replace(
            hour=QUIET_END,
            minute=0,
            second=0,
            microsecond=0
        )

    return dt


def choose_attributions(
    orders,
    sends,
    message_events,
    window_days=ATTRIBUTION_DAYS
):
    """
    Deterministic last-click attribution.

    Rules:
    - Only SENT messages are eligible.
    - Customer and cart must match.
    - A CLICKED event must exist before the order.
    - Order must occur within the attribution window.
    - Latest click wins.
    - One primary attribution per order.
    """

    clicks = defaultdict(list)

    sent_by_id = {
        s["send_id"]: s
        for s in sends
        if s["status"] == "SENT"
    }

    for event in message_events:
        if (
            event["event_type"] == "CLICKED"
            and event["send_id"] in sent_by_id
        ):
            clicks[event["send_id"]].append(event["event_at"])

    result = []

    for order in orders:
        candidates = []

        for send_id, send in sent_by_id.items():

            if send["customer_id"] != order["customer_id"]:
                continue

            if send["cart_id"] != order["cart_id"]:
                continue

            for click_at in clicks.get(send_id, []):

                delta = order["ordered_at"] - click_at

                if (
                    timedelta(0)
                    <= delta
                    <= timedelta(days=window_days)
                ):
                    candidates.append((click_at, send_id))

        if candidates:

            click_at, send_id = sorted(
                candidates,
                key=lambda x: (-x[0].timestamp(), x[1])
            )[0]

            result.append({
                "order_id": order["order_id"],
                "send_id": send_id,
                "attributed_at": order["ordered_at"],
                "attributed_revenue_cents": order["total_cents"],
                "attribution_window_days": window_days,
                "is_primary": True,
                "decision_reason": (
                    f"LAST_CLICK: clicked at {iso(click_at)}; "
                    f"order within {window_days}-day window"
                )
            })

    return result


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables"
    )

    parser.add_argument(
        "--scale",
        type=float,
        default=1.0
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=SEED_DEFAULT
    )

    parser.add_argument(
        "--now",
        default=iso(NOW_DEFAULT)
    )

    args = parser.parse_args()

    if args.scale <= 0:
        raise SystemExit("--scale must be greater than zero")

    rng = random.Random(args.seed)

    now = datetime.fromisoformat(args.now)
    start = now - timedelta(days=HISTORY_DAYS)

    customers_n = max(100, int(30000 * args.scale))
    carts_n = max(100, int(50000 * args.scale))

    target_abandoned = int(20000 * args.scale)
    target_sends = int(10000 * args.scale)

    target_abandoned = min(target_abandoned, carts_n)

    if args.reset:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    customers = []
    consent_rows = []
    sessions = []
    carts = []
    lines = []

    cart_events = []
    campaigns = []
    templates = []
    send_rows = []
    message_events = []

    orders = []
    attribution_rows = []
    ground_truth = []

    consent_index = defaultdict(list)
    sessions_by_customer = defaultdict(list)

    cart_line_counter = 0
    cart_event_counter = 0
    message_event_counter = 0
    consent_counter = 0
    session_counter = 0
    send_counter = 0
    order_counter = 0

    # ---------------------------------------------------------
    # 1. CUSTOMERS AND CONSENT HISTORY
    # ---------------------------------------------------------

    for i in range(1, customers_n + 1):

        cid = f"CUS-{i:06d}"

        created = start - timedelta(
            days=rng.randint(0, 30)
        )

        customers.append({
            "customer_id": cid,
            "first_name": rng.choice(FIRST_NAMES),
            "last_name": rng.choice(LAST_NAMES),
            "email": f"customer{i:06d}@example.test",
            "phone": f"+1555{i:07d}",
            "created_at": created
        })

        for channel in ("EMAIL", "SMS"):

            grant_at = created + timedelta(
                minutes=rng.randint(0, 180)
            )

            if grant_at > now:
                grant_at = now - timedelta(minutes=1)

            consent_counter += 1

            withdraw = rng.random() < (
                0.14 if channel == "EMAIL" else 0.20
            )

            withdraw_at = None

            if withdraw:

                withdraw_at = min(
                    now - timedelta(hours=1),
                    grant_at + timedelta(
                        days=rng.randint(3, 60)
                    )
                )

                if withdraw_at <= grant_at:
                    withdraw = False
                    withdraw_at = None

            grant_row = {
                "consent_id": f"CON-{consent_counter:08d}",
                "customer_id": cid,
                "channel": channel,
                "status": "GRANTED",
                "effective_from": grant_at,
                "effective_to": withdraw_at,
                "source": "CHECKOUT_OPT_IN"
            }

            consent_rows.append(grant_row)
            consent_index[(cid, channel)].append(grant_row)

            if withdraw:

                consent_counter += 1

                withdrawal_row = {
                    "consent_id": f"CON-{consent_counter:08d}",
                    "customer_id": cid,
                    "channel": channel,
                    "status": "WITHDRAWN",
                    "effective_from": withdraw_at,
                    "effective_to": None,
                    "source": "PREFERENCE_CENTER"
                }

                consent_rows.append(withdrawal_row)
                consent_index[(cid, channel)].append(
                    withdrawal_row
                )

                if (
                    rng.random() < 0.18
                    and withdraw_at < now - timedelta(days=2)
                ):

                    regrant_at = withdraw_at + timedelta(
                        days=rng.randint(1, 15)
                    )

                    withdrawal_row["effective_to"] = regrant_at

                    consent_counter += 1

                    regrant_row = {
                        "consent_id": f"CON-{consent_counter:08d}",
                        "customer_id": cid,
                        "channel": channel,
                        "status": "GRANTED",
                        "effective_from": regrant_at,
                        "effective_to": None,
                        "source": "PREFERENCE_CENTER"
                    }

                    consent_rows.append(regrant_row)
                    consent_index[(cid, channel)].append(
                        regrant_row
                    )

    # ---------------------------------------------------------
    # 2. SESSIONS, CARTS AND CART LINES
    # ---------------------------------------------------------

    for i in range(1, carts_n + 1):

        # Cluster a subset of customers to create realistic
        # frequency-cap conflicts.
        if (
            i <= min(2500, target_abandoned)
            and customers_n >= 250
        ):

            cohort_customer = ((i - 1) // 10) + 1
            cid = f"CUS-{cohort_customer:06d}"

            cohort_day = ((i - 1) // 250) % 8

            created = start + timedelta(
                days=cohort_day,
                minutes=rng.randint(0, 360)
            )

        else:
            cid = f"CUS-{rng.randint(1, customers_n):06d}"

            if i <= target_abandoned:
                created = start + timedelta(
                    minutes=rng.randint(
                        0,
                        HISTORY_DAYS * 24 * 60 - 360
                    )
                )
            else:
                created = now - timedelta(
                    minutes=rng.randint(10, 150)
                )

        if i <= target_abandoned:
            activity = created + timedelta(
                minutes=rng.randint(5, 90)
            )
        else:
            activity = min(
                now,
                created + timedelta(
                    minutes=rng.randint(1, 15)
                )
            )

        session_counter += 1

        session_start = created - timedelta(
            minutes=rng.randint(0, 20)
        )

        session_duration = timedelta(
            minutes=rng.randint(30, 130)
        )

        session_end = max(
            activity,
            min(now, session_start + session_duration)
        )

        sid = f"SES-{session_counter:08d}"

        if (
            i <= min(2500, target_abandoned)
            and customers_n >= 250
        ):
            device = DEVICES[
                ((i - 1) % 10) % len(DEVICES)
            ]
        else:
            device = rng.choice(DEVICES)

        session = {
            "session_id": sid,
            "customer_id": cid,
            "device_id": device,
            "started_at": session_start,
            "ended_at": session_end,
            "source": rng.choice(SOURCES)
        }

        sessions.append(session)
        sessions_by_customer[cid].append(session)

        cart_id = f"CART-{now.year}-{i:06d}"

        cart = {
            "cart_id": cart_id,
            "customer_id": cid,
            "session_id": sid,
            "created_at": created,
            "updated_at": activity,
            "last_activity_at": activity,
            "status": "ACTIVE",
            "total_cents": 0
        }

        # Product lines.
        n_products = rng.choices(
            [1, 2, 3, 4],
            weights=[0.48, 0.30, 0.16, 0.06]
        )[0]

        cart_total = 0

        for j in range(n_products):

            product = rng.choices(
                PRODUCTS,
                weights=[p[3] for p in PRODUCTS]
            )[0]

            qty_initial = rng.choices(
                [1, 2, 3],
                weights=[0.78, 0.18, 0.04]
            )[0]

            unit = product[2]
            qty_final = qty_initial

            if rng.random() < 0.17:

                qty_final += 1

                update_at = min(
                    now,
                    activity + timedelta(
                        minutes=rng.randint(1, 15)
                    )
                )

                activity = max(activity, update_at)
                session["ended_at"] = max(
                    session["ended_at"], activity
                )

                cart_event_counter += 1

                cart_events.append({
                    "event_id": f"CE-{cart_event_counter:09d}",
                    "cart_id": cart_id,
                    "event_type": "QUANTITY_UPDATED",
                    "event_at": update_at,
                    "details": json.dumps({
                        "product_id": product[0],
                        "old_quantity": qty_initial,
                        "new_quantity": qty_final,
                        "unit_price_cents": unit
                    })
                })

            line_total = qty_final * unit
            cart_total += line_total

            cart_line_counter += 1

            lines.append({
                "cart_line_id": f"CL-{cart_line_counter:09d}",
                "cart_id": cart_id,
                "product_id": product[0],
                "product_name": product[1],
                "quantity": qty_final,
                "unit_price_cents": unit,
                "line_total_cents": line_total
            })

        cart["updated_at"] = activity
        cart["last_activity_at"] = activity
        cart["total_cents"] = cart_total

        carts.append(cart)

        cart_event_counter += 1

        cart_events.append({
            "event_id": f"CE-{cart_event_counter:09d}",
            "cart_id": cart_id,
            "event_type": "CART_CREATED",
            "event_at": created,
            "details": json.dumps({
                "session_id": sid,
                "source": session["source"]
            })
        })

    # ---------------------------------------------------------
    # 3. CART LIFECYCLE
    # ---------------------------------------------------------

    abandoned = []

    for cart in carts:

        abandonment_at = (
            cart["last_activity_at"]
            + timedelta(minutes=ABANDONMENT_MINUTES)
        )

        if (
            abandonment_at <= now
            and len(abandoned) < target_abandoned
        ):

            cart["status"] = "ABANDONED"
            abandoned.append(cart)

            cart_event_counter += 1

            cart_events.append({
                "event_id": f"CE-{cart_event_counter:09d}",
                "cart_id": cart["cart_id"],
                "event_type": "ABANDONED",
                "event_at": abandonment_at,
                "details": json.dumps({
                    "threshold_minutes": ABANDONMENT_MINUTES,
                    "last_activity_at": iso(
                        cart["last_activity_at"]
                    )
                })
            })

    # ---------------------------------------------------------
    # 4. CAMPAIGNS AND MESSAGE TEMPLATES
    # ---------------------------------------------------------

    campaign_specs = [
        ("CMP-EMAIL-1H", "EMAIL", "REMINDER_1H", 60),
        ("CMP-EMAIL-24H", "EMAIL", "REMINDER_24H", 1440),
        ("CMP-SMS-24H", "SMS", "REMINDER_24H", 1440),
        ("CMP-SMS-72H", "SMS", "REMINDER_72H", 4320),
        ("CMP-EMAIL-DISCOUNT", "EMAIL", "DISCOUNT_72H", 4320)
    ]

    campaign_configs = []

    for campaign_id, channel, variant, delay in campaign_specs:

        campaign = {
            "campaign_id": campaign_id,
            "campaign_name": variant.replace("_", " ").title(),
            "channel": channel,
            "variant": variant,
            "status": "ACTIVE",
            "scheduled_at": start,
            "attribution_window_days": ATTRIBUTION_DAYS
        }

        campaigns.append(campaign)

        campaign_configs.append({
            "campaign": campaign,
            "delay_minutes": delay
        })

    # Template IDs follow the required cart-specific convention.
    
    template_by_cart_campaign = {}
    template_sequence = defaultdict(int)

    # ---------------------------------------------------------
    # 5. BUILD SEND CANDIDATES
    # ---------------------------------------------------------

    candidates = []

    for cart in abandoned:

        customer_id = cart["customer_id"]

        for config in campaign_configs:

            campaign = config["campaign"]
            variant = campaign["variant"]

            scheduled_at = (
                cart["last_activity_at"]
                + timedelta(minutes=ABANDONMENT_MINUTES)
                + timedelta(minutes=config["delay_minutes"])
            )

            if is_quiet_hour(scheduled_at):
                scheduled_at = next_allowed_time(scheduled_at)

            if scheduled_at > now:
                continue

            attempted_at = scheduled_at + timedelta(
                minutes=rng.randint(1, 20)
            )

            # Delivery attempts must also respect quiet hours, not just schedules.
            if is_quiet_hour(attempted_at):
                attempted_at = next_allowed_time(attempted_at)
                scheduled_at = attempted_at

            if attempted_at > now:
                continue

            candidates.append({
                "cart": cart,
                "customer_id": customer_id,
                "campaign": campaign,
                "variant": variant,
                "channel": campaign["channel"],
                "scheduled_at": scheduled_at,
                "attempted_at": attempted_at
            })

    candidates.sort(
        key=lambda x: (
            x["attempted_at"],
            x["customer_id"],
            x["cart"]["cart_id"],
            x["campaign"]["campaign_id"]
        )
    )

    # ---------------------------------------------------------
    # 6. SEND ATTEMPTS, CONSENT AND FREQUENCY CAPS
    # ---------------------------------------------------------

    sent_history = defaultdict(list)
    send_counter = 0

    for candidate in candidates:

        if len(send_rows) >= target_sends:
            break

        customer_id = candidate["customer_id"]
        channel = candidate["channel"]
        scheduled_at = candidate["scheduled_at"]
        attempted_at = candidate["attempted_at"]

        

        suppression_reason = None
        status = "SENT"

        if not active_consent(
            consent_index,
            customer_id,
            channel,
            attempted_at
        ):
            status = "SUPPRESSED"
            suppression_reason = "NO_ACTIVE_CONSENT"

        history = sent_history[customer_id]

        if status == "SENT":

            last_24h = [
                x for x in history
                if timedelta(0) <= attempted_at - x
                < timedelta(hours=24)
            ]

            last_7d = [
                x for x in history
                if timedelta(0) <= attempted_at - x
                < timedelta(days=7)
            ]

            if len(last_24h) >= MAX_SENDS_24H:
                status = "SUPPRESSED"
                suppression_reason = "FREQUENCY_CAP_24H"

            elif len(last_7d) >= MAX_SENDS_7D:
                status = "SUPPRESSED"
                suppression_reason = "FREQUENCY_CAP_7D"

        if status == "SENT":
            sent_history[customer_id].append(attempted_at)

        cart_id = candidate["cart"]["cart_id"]
        variant = candidate["variant"]
        campaign = candidate["campaign"]

        template_key = (cart_id, campaign["campaign_id"])

        if template_key not in template_by_cart_campaign:
            template_sequence[cart_id] += 1

            template_id = (
                f"MSG-{cart_id}-{template_sequence[cart_id]:02d}"
            )

            template = {
                "template_id": template_id,
                "campaign_id": campaign["campaign_id"],
                "channel": channel,
                "subject": (
                    "Your cart is waiting"
                    if channel == "EMAIL"
                    else None
                ),
                "body": (
                    "You left items in your cart. "
                    "Return to complete your purchase."
                ),
                "variant": variant,
                "is_active": True
            }

            templates.append(template)
            template_by_cart_campaign[template_key] = template

        template_id = template_by_cart_campaign[template_key]["template_id"]

        send_counter += 1

        send_id = f"SEND-{now.year}-{send_counter:06d}"

        send = {
            "send_id": send_id,
            "customer_id": customer_id,
            "cart_id": cart_id,
            "campaign_id": campaign["campaign_id"],
            "template_id": template_id,
            "channel": channel,
            "scheduled_at": scheduled_at,
            "attempted_at": attempted_at,
            "status": status,
            "suppression_reason": suppression_reason
        }

        send_rows.append(send)

        if status != "SENT":
            continue

        # Delivery outcome.
        message_event_counter += 1

        delivered_at = attempted_at + timedelta(
            minutes=rng.randint(1, 5)
        )

        if rng.random() < 0.04:

            message_events.append({
                "message_event_id": (
                    f"ME-{message_event_counter:09d}"
                ),
                "send_id": send_id,
                "event_type": "BOUNCED",
                "event_at": delivered_at
            })

            continue

        message_events.append({
            "message_event_id": (
                f"ME-{message_event_counter:09d}"
            ),
            "send_id": send_id,
            "event_type": "DELIVERED",
            "event_at": delivered_at
        })

        if rng.random() >= 0.45:
            continue

        opened_at = delivered_at + timedelta(
            minutes=rng.randint(2, 180)
        )

        if opened_at > now:
            continue

        message_event_counter += 1

        message_events.append({
            "message_event_id": (
                f"ME-{message_event_counter:09d}"
            ),
            "send_id": send_id,
            "event_type": "OPENED",
            "event_at": opened_at
        })

        if rng.random() >= 0.45:
            continue

        clicked_at = opened_at + timedelta(
            minutes=rng.randint(1, 90)
        )

        if clicked_at > now:
            continue

        message_event_counter += 1

        message_events.append({
            "message_event_id": (
                f"ME-{message_event_counter:09d}"
            ),
            "send_id": send_id,
            "event_type": "CLICKED",
            "event_at": clicked_at
        })

    # ---------------------------------------------------------
    # 7. ORDERS
    # ---------------------------------------------------------

    sent_with_clicks = defaultdict(list)

    for event in message_events:
        if event["event_type"] == "CLICKED":
            sent_with_clicks[event["send_id"]].append(
                event["event_at"]
            )

    sends_by_cart = defaultdict(list)

    for send in send_rows:
        if send["status"] == "SENT":
            sends_by_cart[send["cart_id"]].append(send)

    ordered_cart_ids = set()

    # Campaign-assisted conversions: order after a click.
    for send in send_rows:

        if send["status"] != "SENT":
            continue

        click_times = sent_with_clicks.get(
            send["send_id"], []
        )

        if not click_times:
            continue

        if rng.random() >= 0.12:
            continue

        click_at = min(click_times)

        ordered_at = click_at + timedelta(
            hours=rng.randint(1, 48)
        )

        if ordered_at > now:
            continue

        cart = next(
            c for c in carts
            if c["cart_id"] == send["cart_id"]
        )

        if cart["cart_id"] in ordered_cart_ids:
            continue

        order_counter += 1

        discount = (
            int(cart["total_cents"] * 0.10)
            if send["campaign_id"] == "CMP-EMAIL-DISCOUNT"
            else 0
        )

        order = {
            "order_id": f"ORD-{now.year}-{order_counter:06d}",
            "customer_id": cart["customer_id"],
            "cart_id": cart["cart_id"],
            "ordered_at": ordered_at,
            "subtotal_cents": cart["total_cents"],
            "discount_cents": discount,
            "total_cents": cart["total_cents"] - discount,
            "status": "COMPLETED"
        }

        orders.append(order)
        ordered_cart_ids.add(cart["cart_id"])

        cart["status"] = "RECOVERED"

        cart_event_counter += 1

        cart_events.append({
            "event_id": f"CE-{cart_event_counter:09d}",
            "cart_id": cart["cart_id"],
            "event_type": "RECOVERED",
            "event_at": ordered_at,
            "details": json.dumps({
                "order_id": order["order_id"],
                "source": "CAMPAIGN"
            })
        })

    # Organic purchases on non-abandoned carts.
    for cart in carts:

        if cart["cart_id"] in ordered_cart_ids:
            continue

        if cart["status"] != "ACTIVE":
            continue

        if rng.random() >= 0.13:
            continue

        ordered_at = cart["last_activity_at"] + timedelta(
            minutes=rng.randint(5, 120)
        )

        if ordered_at > now:
            continue

        order_counter += 1

        order = {
            "order_id": f"ORD-{now.year}-{order_counter:06d}",
            "customer_id": cart["customer_id"],
            "cart_id": cart["cart_id"],
            "ordered_at": ordered_at,
            "subtotal_cents": cart["total_cents"],
            "discount_cents": 0,
            "total_cents": cart["total_cents"],
            "status": "COMPLETED"
        }

        orders.append(order)
        ordered_cart_ids.add(cart["cart_id"])

        cart["status"] = "PURCHASED"

        cart_event_counter += 1

        cart_events.append({
            "event_id": f"CE-{cart_event_counter:09d}",
            "cart_id": cart["cart_id"],
            "event_type": "PURCHASED",
            "event_at": ordered_at,
            "details": json.dumps({
                "order_id": order["order_id"],
                "source": "ORGANIC"
            })
        })

    # Late purchases outside the attribution window.
    late_candidates = [
        cart for cart in abandoned
        if cart["cart_id"] not in ordered_cart_ids
    ]

    for cart in late_candidates[:max(1, int(500 * args.scale))]:

        ordered_at = (
            cart["last_activity_at"]
            + timedelta(days=9)
        )

        if ordered_at > now:
            continue

        order_counter += 1

        order = {
            "order_id": f"ORD-{now.year}-{order_counter:06d}",
            "customer_id": cart["customer_id"],
            "cart_id": cart["cart_id"],
            "ordered_at": ordered_at,
            "subtotal_cents": cart["total_cents"],
            "discount_cents": 0,
            "total_cents": cart["total_cents"],
            "status": "COMPLETED"
        }

        orders.append(order)
        ordered_cart_ids.add(cart["cart_id"])

        cart["status"] = "PURCHASED"

        cart_event_counter += 1

        cart_events.append({
            "event_id": f"CE-{cart_event_counter:09d}",
            "cart_id": cart["cart_id"],
            "event_type": "PURCHASED",
            "event_at": ordered_at,
            "details": json.dumps({
                "order_id": order["order_id"],
                "source": "LATE_ORGANIC"
            })
        })

    # ---------------------------------------------------------
    # 8. ATTRIBUTION
    # ---------------------------------------------------------

    attribution_candidates = choose_attributions(
        orders,
        send_rows,
        message_events
    )

    for i, row in enumerate(attribution_candidates, 1):
        row["attribution_id"] = f"ATT-{i:09d}"
        attribution_rows.append(row)

    # ---------------------------------------------------------
    # 9. INJECT FOUR LABELLED ANOMALIES
    # ---------------------------------------------------------

    # Anomaly 1: message sent after consent withdrawal.
    sent_with_consent = max(
        (s for s in send_rows if s["status"] == "SENT"),
        key=lambda s: s["attempted_at"],
        default=None
    )

    if sent_with_consent:

        ckey = (
            sent_with_consent["customer_id"],
            sent_with_consent["channel"]
        )

        withdraw_at = (
            sent_with_consent["attempted_at"]
            - timedelta(minutes=1)
        )

        for grant in consent_index[ckey]:

            if (
                grant["status"] == "GRANTED"
                and grant["effective_from"] <= withdraw_at
                and (
                    grant["effective_to"] is None
                    or withdraw_at < grant["effective_to"]
                )
            ):
                grant["effective_to"] = withdraw_at

        consent_counter += 1

        injected_withdrawal = {
            "consent_id": f"CON-{consent_counter:08d}",
            "customer_id": sent_with_consent["customer_id"],
            "channel": sent_with_consent["channel"],
            "status": "WITHDRAWN",
            "effective_from": withdraw_at,
            "effective_to": None,
            "source": "ANOMALY_INJECTION"
        }

        consent_rows.append(injected_withdrawal)
        consent_index[ckey].append(injected_withdrawal)

        ground_truth.append({
            "issue_id": "ISS-0001",
            "issue_type": "MESSAGE_AFTER_OPT_OUT",
            "entity_type": "SEND_ATTEMPT",
            "entity_id": sent_with_consent["send_id"],
            "expected_detection": (
                "SENT without active consent at attempted_at"
            )
        })

    # Anomaly 2: purchased cart incorrectly labelled abandoned.
    purchased = next(
        (
            c for c in carts
            if c["status"] in ("PURCHASED", "RECOVERED")
        ),
        None
    )

    if purchased:

        purchased["status"] = "ABANDONED"

        ground_truth.append({
            "issue_id": "ISS-0002",
            "issue_type": "ABANDONED_AFTER_PURCHASE",
            "entity_type": "CART",
            "entity_id": purchased["cart_id"],
            "expected_detection": (
                "Cart status conflicts with completed order"
            )
        })

    # Anomaly 3: stale cart total after quantity update.
    updated_cart_ids = {
        event["cart_id"]
        for event in cart_events
        if event["event_type"] == "QUANTITY_UPDATED"
    }

    stale_cart = next(
        (
            c for c in carts
            if c["cart_id"] in updated_cart_ids
        ),
        None
    )

    if stale_cart:

        stale_cart["total_cents"] += 10000

        ground_truth.append({
            "issue_id": "ISS-0003",
            "issue_type": "STALE_CART_TOTAL",
            "entity_type": "CART",
            "entity_id": stale_cart["cart_id"],
            "expected_detection": (
                "Stored cart total differs from sum of cart lines "
                "after quantity update"
            )
        })

    # Anomaly 4: two campaigns receive primary credit for the same order.
    # Build this fixture on an existing abandoned cart, so base entity counts
    # remain exact. Search for a customer/time gap that respects consent,
    # quiet hours, and both frequency caps.

    email_campaigns = [c for c in campaigns if c["channel"] == "EMAIL"]
    if len(email_campaigns) < 2:
        raise RuntimeError("Anomaly 4 requires at least two EMAIL campaigns.")

    existing_order_cart_ids = {o["cart_id"] for o in orders if o["cart_id"]}
    sent_by_customer = defaultdict(list)
    for send in send_rows:
        if send["status"] == "SENT" and send["attempted_at"] is not None:
            sent_by_customer[send["customer_id"]].append(send["attempted_at"])

    anomaly_fixture = None
    # Search existing carts in deterministic order. Midday daily candidates
    # avoid quiet hours and give a full 25-hour interval between touches.
    for candidate_cart in abandoned:
        if candidate_cart["cart_id"] in existing_order_cart_ids:
            continue

        cid = candidate_cart["customer_id"]
        first_possible = max(
            candidate_cart["last_activity_at"] + timedelta(minutes=ABANDONMENT_MINUTES),
            start + timedelta(days=8)
        )
        first_day = first_possible.replace(hour=12, minute=0, second=0, microsecond=0)
        if first_day < first_possible:
            first_day += timedelta(days=1)

        day = first_day
        while day + timedelta(hours=25, minutes=30) <= now:
            first_at = day
            second_at = first_at + timedelta(hours=25)
            order_at = second_at + timedelta(minutes=30)

            if is_quiet_hour(first_at) or is_quiet_hour(second_at):
                day += timedelta(days=1)
                continue

            if not active_consent(consent_index, cid, "EMAIL", first_at):
                day += timedelta(days=1)
                continue
            if not active_consent(consent_index, cid, "EMAIL", second_at):
                day += timedelta(days=1)
                continue

            # Existing sends in the preceding 7 days plus the first fixture
            # send must never exceed 2; 25h spacing keeps the 24h cap clear.
            prior_first = [
                t for t in sent_by_customer[cid]
                if timedelta(0) <= first_at - t < timedelta(days=7)
            ]
            prior_second = [
                t for t in sent_by_customer[cid]
                if timedelta(0) <= second_at - t < timedelta(days=7)
            ]
            prior_second_24h = [
                t for t in sent_by_customer[cid]
                if timedelta(0) <= second_at - t < timedelta(hours=24)
            ]

            if (
                len(prior_first) < MAX_SENDS_7D
                and len(prior_second) + 1 < MAX_SENDS_7D
                and len(prior_second_24h) == 0
            ):
                anomaly_fixture = (candidate_cart, first_at, second_at, order_at)
                break

            day += timedelta(days=1)

        if anomaly_fixture:
            break

    if anomaly_fixture is None:
        raise RuntimeError(
            "Could not construct the double-attribution fixture from existing "
            "abandoned carts while preserving consent and frequency-cap rules."
        )

    anomaly_cart, first_send_at, second_send_at, anomaly_order_at = anomaly_fixture
    anomaly_customer_id = anomaly_cart["customer_id"]
    anomaly_cart_id = anomaly_cart["cart_id"]

    anomaly_sends = []
    for campaign, attempted_at in zip(email_campaigns[:2], [first_send_at, second_send_at]):
        template_key = (anomaly_cart_id, campaign["campaign_id"])
        if template_key in template_by_cart_campaign:
            template_id = template_by_cart_campaign[template_key]["template_id"]
        else:
            template_sequence[anomaly_cart_id] += 1
            template_id = f"MSG-{anomaly_cart_id}-{template_sequence[anomaly_cart_id]:02d}"
            template = {
                "template_id": template_id,
                "campaign_id": campaign["campaign_id"],
                "channel": "EMAIL",
                "subject": "Your cart is waiting",
                "body": "Return to complete your purchase.",
                "variant": campaign["variant"],
                "is_active": True
            }
            templates.append(template)
            template_by_cart_campaign[template_key] = template

        send_counter += 1
        anomaly_send_id = f"SEND-{now.year}-{send_counter:06d}"
        anomaly_send = {
            "send_id": anomaly_send_id,
            "customer_id": anomaly_customer_id,
            "cart_id": anomaly_cart_id,
            "campaign_id": campaign["campaign_id"],
            "template_id": template_id,
            "channel": "EMAIL",
            "scheduled_at": attempted_at,
            "attempted_at": attempted_at,
            "status": "SENT",
            "suppression_reason": None
        }
        send_rows.append(anomaly_send)
        anomaly_sends.append(anomaly_send)

        for event_type, offset in (("DELIVERED", 1), ("CLICKED", 5)):
            message_event_counter += 1
            message_events.append({
                "message_event_id": f"ME-{message_event_counter:09d}",
                "send_id": anomaly_send_id,
                "event_type": event_type,
                "event_at": attempted_at + timedelta(minutes=offset)
            })

    # One completed order after both clicks, on the same existing cart.
    order_counter += 1
    anomaly_order = {
        "order_id": f"ORD-{now.year}-{order_counter:06d}",
        "customer_id": anomaly_customer_id,
        "cart_id": anomaly_cart_id,
        "ordered_at": anomaly_order_at,
        "subtotal_cents": anomaly_cart["total_cents"],
        "discount_cents": 0,
        "total_cents": anomaly_cart["total_cents"],
        "status": "COMPLETED"
    }
    orders.append(anomaly_order)
    anomaly_cart["status"] = "RECOVERED"

    cart_event_counter += 1
    cart_events.append({
        "event_id": f"CE-{cart_event_counter:09d}",
        "cart_id": anomaly_cart_id,
        "event_type": "RECOVERED",
        "event_at": anomaly_order_at,
        "details": json.dumps({
            "order_id": anomaly_order["order_id"],
            "source": "ANOMALY_4_TEST_FIXTURE"
        })
    })

    for anomaly_send in anomaly_sends:
        attribution_rows.append({
            "attribution_id": f"ATT-{len(attribution_rows) + 1:09d}",
            "order_id": anomaly_order["order_id"],
            "send_id": anomaly_send["send_id"],
            "attributed_at": anomaly_order_at,
            "attributed_revenue_cents": anomaly_order["total_cents"],
            "attribution_window_days": ATTRIBUTION_DAYS,
            "is_primary": True,
            "decision_reason": (
                "ANOMALY_INJECTION: duplicate primary credit across campaigns"
            )
        })

    ground_truth.append({
        "issue_id": "ISS-0004",
        "issue_type": "DOUBLE_ATTRIBUTION",
        "entity_type": "ORDER",
        "entity_id": anomaly_order["order_id"],
        "expected_detection": "More than one primary attribution for an order"
    })

    # ---------------------------------------------------------
    # 10. STRUCTURAL VALIDATION
    # ---------------------------------------------------------

    if len(carts) != carts_n:
        raise RuntimeError(
            f"Expected {carts_n} carts, generated {len(carts)}"
        )

    if len(abandoned) < target_abandoned:
        raise RuntimeError(
            f"Expected at least {target_abandoned} abandoned carts, "
            f"generated {len(abandoned)}"
        )

    if len(send_rows) < target_sends:
        raise RuntimeError(
            f"Expected at least {target_sends} send attempts, "
            f"generated {len(send_rows)}"
        )

    if len(ground_truth) != 4:
        raise RuntimeError(f"Expected exactly 4 labelled anomalies, generated {len(ground_truth)}")

    if len({row["send_id"] for row in send_rows}) != len(send_rows):
        raise RuntimeError("Duplicate send_id generated")

    if len({row["template_id"] for row in templates}) != len(templates):
        raise RuntimeError("Duplicate template_id generated")

    for cart in carts:

        if cart["updated_at"] < cart["created_at"]:
            raise RuntimeError(
                f"Invalid updated_at: {cart['cart_id']}"
            )

        if cart["last_activity_at"] < cart["created_at"]:
            raise RuntimeError(
                f"Invalid last_activity_at: {cart['cart_id']}"
            )

    # ---------------------------------------------------------
    # 11. PERSIST DATA IN FOREIGN-KEY ORDER
    # ---------------------------------------------------------

    session = SessionLocal()

    try:

        def add_many(model, rows):
            if rows:
                session.bulk_insert_mappings(model, rows)

        add_many(Customer, customers)
        add_many(Consent, consent_rows)
        add_many(CustomerSession, sessions)
        add_many(Cart, carts)
        add_many(CartLine, lines)
        add_many(Campaign, campaigns)
        add_many(MessageTemplate, templates)
        add_many(SendAttempt, send_rows)
        add_many(Order, orders)
        add_many(Attribution, attribution_rows)
        add_many(CartEvent, cart_events)
        add_many(MessageEvent, message_events)

        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()

    # ---------------------------------------------------------
    # 12. EXPORT CSV AND JSON
    # ---------------------------------------------------------

    out = ROOT / "data"

    exports = out / "exports"
    truth_dir = out / "ground_truth"

    exports.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    table_data = {
        "customers": customers,
        "consents": consent_rows,
        "sessions": sessions,
        "carts": carts,
        "cart_lines": lines,
        "campaigns": campaigns,
        "message_templates": templates,
        "send_attempts": send_rows,
        "orders": orders,
        "attributions": attribution_rows,
        "cart_events": cart_events,
        "message_events": message_events
    }

    def serial(value):
        if isinstance(value, datetime):
            return iso(value)
        return value

    for name, rows in table_data.items():

        if not rows:
            continue

        with (
            exports / f"{name}.csv"
        ).open(
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=list(rows[0].keys())
            )

            writer.writeheader()

            writer.writerows([
                {
                    key: serial(value)
                    for key, value in row.items()
                }
                for row in rows
            ])

        with (
            exports / f"{name}.json"
        ).open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                [
                    {
                        key: serial(value)
                        for key, value in row.items()
                    }
                    for row in rows
                ],
                file,
                indent=2
            )

    with (
        truth_dir / "ground_truth.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "issue_id",
                "issue_type",
                "entity_type",
                "entity_id",
                "expected_detection"
            ]
        )

        writer.writeheader()
        writer.writerows(ground_truth)

    with (
        truth_dir / "ground_truth.json"
    ).open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(ground_truth, file, indent=2)

    # ---------------------------------------------------------
    # 13. GENERATION SUMMARY
    # ---------------------------------------------------------

    counts = {
        name: len(rows)
        for name, rows in table_data.items()
    }

    summary = {
        "seed": args.seed,
        "scale": args.scale,
        "reference_time": iso(now),
        "history_days": HISTORY_DAYS,
        "abandonment_threshold_minutes": ABANDONMENT_MINUTES,
        "attribution_window_days": ATTRIBUTION_DAYS,
        "currency": "INR",
        "money_storage": (
            "integer paise; legacy column names use _cents"
        ),
        "counts": counts,
        "carts_reaching_abandonment": sum(
            event["event_type"] == "ABANDONED"
            for event in cart_events
        ),
        "currently_abandoned_carts": sum(
            cart["status"] == "ABANDONED"
            for cart in carts
        ),
        "frequency_cap_suppressions": sum(
            (row["suppression_reason"] or "").startswith(
                "FREQUENCY_CAP"
            )
            for row in send_rows
        ),
        "multi_device_customers": sum(
            1
            for customer_sessions in sessions_by_customer.values()
            if len({
                item["device_id"]
                for item in customer_sessions
            }) > 1
        ),
        "ground_truth_issue_count": len(ground_truth),
        "notes": [
            "Baseline outcomes are generated before anomaly injection.",
            "Cart status is derived from event time and order state.",
            "Attribution uses last-click within a 7-day window."
        ]
    }

    (
        out / "generation_summary.json"
    ).write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()