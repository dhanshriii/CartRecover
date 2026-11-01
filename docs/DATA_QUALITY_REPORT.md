# CartRecover — Data Quality and Validation Report

## 1. Executive Summary

This report documents the data quality validation performed on the CartRecover synthetic dataset.

The validation process checks referential integrity, uniqueness, cart monetary consistency, lifecycle consistency, consent compliance, campaign/template compatibility, attribution validity, and communication frequency limits.

The dataset contains four deliberately injected anomalies. All four were detected by the validation script, with no additional unexpected findings.

**Overall result:** All expected validation scenarios were detected. The dataset is suitable for demonstrating validation and exception-detection capabilities, but it must not be described as completely clean.

## 2. Dataset Overview

The generated dataset contains 12 entities.

| Entity | Record count |
|---|---:|
| Customers | 30,000 |
| Consents | 71,834 |
| Sessions | 50,000 |
| Carts | 50,000 |
| Cart lines | 90,193 |
| Campaigns | 5 |
| Message templates | 10,000 |
| Send attempts | 10,003 |
| Orders | 2,662 |
| Attributions | 46 |
| Cart events | 88,027 |
| Message events | 2,806 |
| **Total records** | **432,555** |

The dataset is generated synthetically using a deterministic seed to support repeatable testing.

## 3. Validation Results

| Validation | Findings | Expected result | Status |
|---|---:|---|---|
| Foreign-key integrity | 0 violations | 0 | PASS |
| Duplicate customer emails | 0 | 0 | PASS |
| Duplicate send IDs | 0 | 0 | PASS |
| Cart total reconciliation | 1 mismatch | 1 injected anomaly | EXPECTED |
| Cart/session consistency | 0 mismatches | 0 | PASS |
| Cart/order lifecycle | 1 mismatch | 1 injected anomaly | EXPECTED |
| Consent at send time | 1 violation | 1 injected anomaly | EXPECTED |
| Campaign/template consistency | 0 mismatches | 0 | PASS |
| Attribution validity | 0 invalid rows | 0 | PASS |
| Multiple primary attribution review | 1 affected order | 1 injected anomaly | EXPECTED |
| Seven-day frequency cap | 0 violations | 0 | PASS |

All four expected anomaly categories were detected. No additional unexpected findings were reported by the validation script.

## 4. Detected Anomalies

### 4.1 Cart Total Reconciliation

**Affected record:** `CART-2026-000004`

- Stored cart total: 1,709,500 paise.
- Sum of cart line totals: 1,699,500 paise.
- Difference: 10,000 paise (₹100).

**Risk:** Incorrect cart values can affect recovery prioritization, customer messaging, and revenue reporting.

**Recommended handling:** Flag the cart for reconciliation against its cart-line records. Do not silently overwrite the stored amount without an auditable correction.

### 4.2 Cart and Order Lifecycle Inconsistency

One cart is marked as abandoned despite having a completed order.

**Risk:** The recovery system could attempt to contact a customer who has already completed checkout.

**Recommended handling:** Reconcile cart status against completed order events and cancel any pending recovery attempt for that cart.

### 4.3 Consent Violation

One send attempt was recorded without an effective consent grant at the time of sending.

**Risk:** Contacting a customer without valid channel-specific consent creates compliance and reputational risk.

**Recommended handling:** Treat the event as a compliance incident. Preserve the historical record, investigate the dispatch path, and ensure consent is checked again immediately before actual provider dispatch.

### 4.4 Multiple Attribution Records

**Affected order:** `ORD-2026-002662`

Two attribution records are associated with the same order.

**Risk:** Multiple primary attributions can inflate campaign conversion counts and attributed revenue.

**Recommended handling:** Enforce a single-primary-attribution rule and retain the decision history for auditability.

The validator reports zero invalid attribution rows separately. This does not mean the multiple-attribution finding should be ignored; it is a distinct integrity check.

## 5. Communication and Suppression Analysis

The analytics endpoint reports the following communication results:

| Metric | Count |
|---|---:|
| Total send attempts | 10,003 |
| Sent | 1,728 |
| Scheduled | 1 |
| Suppressed | 8,274 |
| Failed | 0 |

### Suppression breakdown

| Reason | Count | Share |
|---|---:|---:|
| 24-hour frequency cap | 5,740 | 69.37% |
| 7-day frequency cap | 2,183 | 26.38% |
| No active consent | 351 | 4.24% |
| **Total** | **8,274** | **100%** |

The high suppression rate is primarily driven by frequency-cap rules.

This should not automatically be treated as a defect. Frequency caps protect customers from excessive communication. However, the distribution indicates that repeated attempts and customer-level scheduling deserve further analysis.

The suppression counts describe recorded send attempts, not necessarily unique customers.

## 6. Business Measurement Snapshot

| Metric | Observed value |
|---|---:|
| Customers | 30,000 |
| Carts | 50,000 |
| Currently abandoned carts | 19,456 |
| Recovered carts | 45 |
| Completed orders | 2,662 |
| Attributed orders | 45 |
| Attributed revenue | ₹2,62,917.70 |
| Recovery rate reported by API | 0.23% |

The reported recovery rate is a snapshot ratio:

Recovered carts / (Recovered carts + Currently abandoned carts).

It is not a fully cohort-based historical recovery rate.

Attributed revenue represents revenue associated with qualifying recovery messages. It does not establish that those messages caused the purchases.

A randomized control group is required to estimate incremental conversion and revenue lift.

## 7. Validation Approach

The validation script checks:

1. Database referential integrity.
2. Duplicate customer email addresses.
3. Duplicate send identifiers.
4. Cart total against cart-line totals.
5. Cart and session customer consistency.
6. Abandoned cart and completed order consistency.
7. Effective consent at send time.
8. Campaign and template compatibility.
9. Attribution record validity.
10. Multiple attribution records per order.
11. Customer-level rolling seven-day send frequency.

The script reports both expected anomalies and unexpected findings, making it possible to distinguish deliberately injected test cases from unanticipated data-quality problems.

## 8. Recommended Production Controls

| Risk | Recommended control |
|---|---|
| Invalid cart totals | Automated reconciliation and quarantine |
| Purchase after abandonment | Event-driven lifecycle reconciliation |
| Consent withdrawal | Final consent check before dispatch |
| Duplicate attribution | Unique constraints and primary attribution enforcement |
| Duplicate events | Idempotency keys |
| Excessive messaging | Atomic rolling-window frequency limits |
| Late-arriving events | Event-time processing and reconciliation |
| Provider delivery uncertainty | Webhook reconciliation and retry monitoring |

## 9. Limitations

- The dataset is synthetic and does not represent real customer behavior.
- Validation findings demonstrate controlled test scenarios, not production incident rates.
- The current implementation uses SQLite.
- External email and SMS delivery are not implemented.
- The analytics metrics count recorded events and attempts; they do not necessarily represent unique messages or customers.
- Incremental revenue cannot be established without controlled experimentation.

## 10. Conclusion

The validation process successfully detected all four deliberately injected anomaly categories and reported no additional unexpected findings.

This demonstrates the importance of treating data quality, consent enforcement, lifecycle consistency, and attribution integrity as core parts of a cart recovery system.

CartRecover is designed not only to identify recovery opportunities but also to detect situations where acting on the available data could produce incorrect, unsafe, or misleading business outcomes.