import sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "cartrecover.db"


def main():
    if not DB.exists():
        raise SystemExit(f"Database not found: {DB}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    tables = [
        "customers", "consents", "sessions", "carts", "cart_lines",
        "campaigns", "message_templates", "send_attempts", "orders",
        "attributions", "cart_events", "message_events",
    ]

    print("DATABASE:", DB)
    print("\n1. ROW COUNTS")
    for table in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:20s} {count:>10,}")

    print("\n2. FOREIGN KEY CHECK")
    fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
    print("Foreign-key violations:", len(fk_errors))
    for row in fk_errors[:10]:
        print(dict(row))

    print("\n3. PRIMARY KEY / UNIQUE CHECKS")
    duplicate_email = con.execute("""
        SELECT email, COUNT(*) n FROM customers
        GROUP BY email HAVING n > 1
    """).fetchall()
    duplicate_send = con.execute("""
        SELECT send_id, COUNT(*) n FROM send_attempts
        GROUP BY send_id HAVING n > 1
    """).fetchall()
    print("Duplicate customer emails:", len(duplicate_email))
    print("Duplicate send IDs:", len(duplicate_send))

    print("\n4. CART TOTAL RECONCILIATION")
    total_mismatches = con.execute("""
        SELECT c.cart_id, c.total_cents, COALESCE(SUM(cl.line_total_cents), 0) line_sum
        FROM carts c LEFT JOIN cart_lines cl ON cl.cart_id = c.cart_id
        GROUP BY c.cart_id
        HAVING c.total_cents != COALESCE(SUM(cl.line_total_cents), 0)
    """).fetchall()
    print("Mismatches (one injected anomaly expected):", len(total_mismatches))
    for row in total_mismatches[:5]:
        print(dict(row))

    print("\n5. CART / SESSION CUSTOMER CONSISTENCY")
    relationship_errors = con.execute("""
        SELECT COUNT(*) FROM carts c
        JOIN sessions s ON s.session_id = c.session_id
        WHERE c.customer_id != s.customer_id
    """).fetchone()[0]
    print("Customer/session mismatches:", relationship_errors)

    print("\n6. CART / ORDER LIFECYCLE")
    lifecycle_errors = con.execute("""
        SELECT COUNT(*) FROM carts c
        JOIN orders o ON o.cart_id = c.cart_id
        WHERE c.status = 'ABANDONED' AND o.status = 'COMPLETED'
    """).fetchone()[0]
    print("Abandoned carts with completed orders (one injected anomaly expected):",
          lifecycle_errors)

    print("\n7. CONSENT AT SEND TIME")
    consent_errors = con.execute("""
        SELECT COUNT(*)
        FROM send_attempts s
        WHERE s.status = 'SENT'
          AND NOT EXISTS (
              SELECT 1 FROM consents c
              WHERE c.customer_id = s.customer_id
                AND c.channel = s.channel
                AND c.status = 'GRANTED'
                AND c.effective_from <= s.attempted_at
                AND (c.effective_to IS NULL OR s.attempted_at < c.effective_to)
          )
    """).fetchone()[0]
    print("Sent without effective grant (one injected anomaly expected):",
          consent_errors)

    print("\n8. CAMPAIGN / TEMPLATE CONSISTENCY")
    template_errors = con.execute("""
        SELECT COUNT(*)
        FROM send_attempts s
        JOIN campaigns c ON c.campaign_id = s.campaign_id
        JOIN message_templates t ON t.template_id = s.template_id
        WHERE s.channel != c.channel OR s.channel != t.channel
           OR t.campaign_id != s.campaign_id
    """).fetchone()[0]
    print("Campaign/template mismatches:", template_errors)

    print("\n9. ATTRIBUTION VALIDITY")
    attribution_errors = con.execute("""
        SELECT COUNT(*)
        FROM attributions a
        JOIN orders o ON o.order_id = a.order_id
        JOIN send_attempts s ON s.send_id = a.send_id
        WHERE s.status != 'SENT'
           OR s.customer_id != o.customer_id
           OR s.cart_id != o.cart_id
           OR s.attempted_at > o.ordered_at
           OR julianday(o.ordered_at) - julianday(s.attempted_at)
                > a.attribution_window_days
    """).fetchone()[0]
    print("Invalid attribution rows (one injected duplicate may be valid by time):",
          attribution_errors)

    print("\n10. MULTIPLE ATTRIBUTIONS")
    multi = con.execute("""
        SELECT order_id, COUNT(*) n FROM attributions
        GROUP BY order_id HAVING n > 1
    """).fetchall()
    print("Orders with multiple attributions (one injected anomaly expected):",
          len(multi))
    for row in multi[:5]:
        print(dict(row))

    print("\n11. FREQUENCY CAP REVIEW")
    sent_rows = con.execute("""
        SELECT customer_id, attempted_at
        FROM send_attempts
        WHERE status = 'SENT' AND attempted_at IS NOT NULL
        ORDER BY customer_id, attempted_at
    """).fetchall()
    by_customer = defaultdict(list)
    for row in sent_rows:
        by_customer[row["customer_id"]].append(row["attempted_at"])

    cap_violations = 0
    for customer_id, times in by_customer.items():
        parsed = [sqlite3.TimestampFromTicks(0) if False else t for t in times]
        # SQLite stores ISO datetime strings; lexicographic order is chronological.
        for i, current in enumerate(parsed):
            window_count = sum(
                1 for previous in parsed[:i]
                if 0 <= (
                    __import__("datetime").datetime.fromisoformat(current)
                    - __import__("datetime").datetime.fromisoformat(previous)
                ).total_seconds() < 7 * 86400
            )
            if window_count >= 2:
                cap_violations += 1
                break
    print("Customers exceeding 2 sends in a rolling 7-day window:",
          cap_violations)

    con.close()

    print("\nValidation script completed.")
    print("Expected deliberate findings: 1 cart-total mismatch,")
    print("1 cart/order lifecycle mismatch, 1 consent violation,")
    print("and 1 order with multiple attributions.")
    print("Investigate any additional findings before treating the data as clean.")


if __name__ == "__main__":
    main()
