# CartRecover

### Abandoned Cart Recovery & Conversion Attribution System

**A consent-aware cart recovery platform with campaign scheduling, conversion attribution, synthetic data generation, and an interactive analytics dashboard.**

CartRecover is an end-to-end system designed to identify abandoned shopping carts, evaluate customer communication eligibility, schedule personalized recovery campaigns, and attribute completed purchases to eligible recovery interactions.

The system emphasizes **data integrity, customer consent, explainable business decisions, and measurable campaign outcomes**.

It combines a FastAPI backend, SQLite relational database, deterministic synthetic data generator, and React-based operations dashboard.

> **Implementation scope:** Recovery messages are scheduled and recorded in the database. The application does not send real emails or SMS messages through external providers.

---

## 1. Key Features

### Cart Recovery and Eligibility

- Identify abandoned carts using configurable inactivity thresholds.
- Evaluate cart status and completed purchase history.
- Validate channel-specific EMAIL and SMS consent.
- Respect consent withdrawal and effective-date history.
- Apply cross-channel communication frequency caps.
- Return explicit eligibility and suppression reasons.

### Campaign Scheduling

- Select configured recovery campaigns and message templates.
- Apply quiet-hour restrictions.
- Schedule eligible recovery messages.
- Record suppressed scheduling attempts.
- Generate unique send identifiers.
- Prevent duplicate scheduling operations where enforced by the backend.

### Conversion Attribution

- Attribute completed purchases to qualifying recovery interactions.
- Require a valid clicked recovery message.
- Enforce campaign attribution windows.
- Match customer and cart relationships.
- Use last-eligible-click attribution.
- Prevent multiple primary attributions for the same order.
- Distinguish unattributed orders from attributed conversions.

### Data Engineering and Quality

- Generate deterministic synthetic e-commerce data.
- Maintain 12 related database entities.
- Validate referential integrity and business constraints.
- Inject four known anomaly scenarios for quality testing.
- Export canonical CSV datasets and ground-truth records.
- Support reproducible generation using a fixed random seed.

### Interactive Operations Dashboard

- Display cart recovery and customer metrics.
- Monitor messaging statuses and suppression reasons.
- Track completed orders and attributed revenue.
- Display delivery, open, and click event counts.
- Evaluate cart recovery eligibility from the browser.
- Submit campaign scheduling requests.
- Test order attribution.
- Display actual API responses and errors.

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite |
| Frontend styling | CSS |
| Backend | Python, FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Synthetic data generation | Faker |
| Data processing | Pandas, NumPy |
| API documentation | Swagger UI / OpenAPI |
| Backend testing | Pytest |
| Version control | Git, GitHub |

### System Architecture

```text
                  React Operations Dashboard
                              |
                              | HTTP / JSON
                              v
                       FastAPI Backend
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
        Eligibility      Campaign        Attribution
          Engine         Scheduling         Service
               |              |              |
               +--------------+--------------+
                              |
                              v
                      SQLAlchemy ORM
                              |
                              v
                       SQLite Database
                              ^
                              |
                   Synthetic Data Generator
                              |
                              v
                  Validation and Ground Truth
```

The React development server proxies `/api` requests to the FastAPI backend.

---

## 3. Project Structure

```text
CartRecover/
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |   |-- analytics.py
|   |   |   |-- routes.py
|   |   |   `-- schemas.py
|   |   |-- models/
|   |   |   `-- entities.py
|   |   |-- services/
|   |   |   |-- recovery_engine.py
|   |   |   |-- campaign_service.py
|   |   |   `-- attribution_service.py
|   |   |-- database.py
|   |   `-- main.py
|   |-- generator/
|   |   |-- generate.py
|   |   `-- validate.py
|   |-- tests/
|   `-- requirements.txt
|
|-- frontend/
|   |-- public/
|   |-- src/
|   |   |-- App.jsx
|   |   |-- App.css
|   |   |-- index.css
|   |   `-- main.jsx
|   |-- index.html
|   |-- package.json
|   |-- package-lock.json
|   |-- vite.config.js
|   `-- .gitignore
|
|-- data/
|   |-- exports/
|   |-- ground_truth/
|   `-- generation_summary.json
|
|-- docs/
|   |-- SOLUTION_DESIGN.md
|   |-- DATA_QUALITY_REPORT.md
|   `-- AI_ROADMAP.md
|
|-- .gitignore
|-- pytest.ini
`-- README.md
```

**Note:** The generated SQLite database, Python virtual environment, frontend dependencies, and frontend build output are excluded from Git.

---

## 4. Database Design

The system uses 12 relational entities.

| Entity | Purpose |
|---|---|
| Customer | Customer profile information |
| Consent | Channel-specific consent history |
| CustomerSession | Customer browsing sessions |
| Cart | Shopping carts and lifecycle status |
| CartLine | Products, quantities, and cart-line values |
| Campaign | Recovery campaign configurations |
| MessageTemplate | Recovery message templates |
| SendAttempt | Scheduled, sent, failed, and suppressed attempts |
| Order | Purchase and order records |
| Attribution | Conversion attribution records |
| CartEvent | Cart lifecycle event history |
| MessageEvent | Delivery and engagement events |

The schema uses primary keys, foreign keys, unique constraints, check constraints, and indexes to enforce important data-integrity rules.

---

## 5. Business Rules

### 5.1 Abandoned Cart Identification

- Default inactivity threshold: **180 minutes**.
- Supported cart lifecycle states include `ACTIVE`, `ABANDONED`, `PURCHASED`, and `RECOVERED`.
- Carts associated with completed purchases are ineligible for recovery.
- Eligibility evaluation returns explicit reasons for approval or suppression.

The minimum inactivity threshold is not a maximum cart-age restriction. The current implementation can evaluate older abandoned carts.

### 5.2 Customer Consent

- Consent is evaluated separately for EMAIL and SMS.
- Consent records contain effective start and end dates.
- The latest applicable effective consent record determines the communication status.
- Withdrawn or unavailable active consent prevents communication on the corresponding channel.

### 5.3 Frequency Caps

The configured limits are:

| Window | Maximum successful sends |
|---|---:|
| Rolling 24 hours | 1 |
| Rolling 7 days | 2 |

Frequency limits apply across communication channels.

### 5.4 Quiet Hours

- Quiet hours: **9:00 PM to 8:00 AM**.
- Scheduling during restricted hours is deferred to the next permitted time.
- A scheduled message is not equivalent to a dispatched message.

### 5.5 Conversion Attribution

An order can be attributed only when the applicable rules are satisfied:

1. The order is completed.
2. A qualifying recovery send exists.
3. The send has status `SENT`.
4. The customer and cart relationships match.
5. A qualifying `CLICKED` event exists before the order.
6. The click falls within the campaign attribution window.
7. The most recent eligible click is selected.
8. The order does not already have a primary attribution.

The API may return results such as:

- `ALREADY_ATTRIBUTED` — an existing primary attribution prevents duplication.
- `NOT_ATTRIBUTED` — no qualifying recovery interaction was found.

**Attributed revenue should not be interpreted as incremental revenue caused by the campaign.**

---

## 6. Synthetic Data Generation

The system generates a deterministic synthetic e-commerce dataset.

### Dataset Configuration

| Parameter | Value |
|---|---:|
| Random seed | `20261022` |
| Scale | `1.0` |
| Customers | 30,000 |
| Consent records | 71,834 |
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
| **Total records** | **405,576** |

These counts describe the generated dataset before any additional dashboard testing or API mutations.

### Intentional Data Anomalies

Four known anomaly scenarios are included:

1. A recovery message sent without valid effective consent.
2. A cart marked abandoned despite an associated completed purchase.
3. Duplicate attribution records associated with the same order.
4. A cart total inconsistent with its cart-line totals.

Ground-truth records support verification of these scenarios.

The validation process distinguishes intentionally injected anomalies from unexpected data-quality failures.

---

## 7. Installation and Setup

### Prerequisites

- Python 3.12 or a compatible version
- Node.js and npm
- Git
- Windows PowerShell for the commands shown below

### 7.1 Clone the Repository

```powershell
git clone https://github.com/dhanshriii/CartRecover.git
cd CartRecover
```

### 7.2 Create a Python Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 7.3 Install Backend Dependencies

```powershell
pip install -r backend/requirements.txt
```

### 7.4 Configure Python Import Path

From the project root:

```powershell
$env:PYTHONPATH = "backend"
```

This enables Python to resolve the backend application modules when commands are run from the repository root.

---

## 8. Generate the Dataset

The generated SQLite database is not committed to Git.

Before running the backend for the first time, generate the local database.

From the project root:

```powershell
python backend/generator/generate.py --reset
```

For a smaller development dataset:

```powershell
python backend/generator/generate.py --reset --scale 0.1
```

**Warning:** The `--reset` option regenerates the database and can overwrite local test changes, including scheduling and attribution records created through the dashboard.

The generator uses a fixed seed to support reproducible output.

---

## 9. Validate the Dataset

From the project root:

```powershell
python backend/generator/validate.py
```

The validation process checks:

- Foreign-key violations.
- Duplicate identifiers.
- Cart-total inconsistencies.
- Customer and session consistency.
- Consent and communication eligibility.
- Campaign and template relationships.
- Duplicate attribution.
- Frequency-cap violations.

Review the results alongside the intentional anomaly ground truth.

For additional context, see `docs/DATA_QUALITY_REPORT.md`.

---

## 10. Run the Backend API

Open a terminal at the project root and activate the Python environment.

```powershell
.\.venv\Scripts\Activate.ps1
```

Start the FastAPI server:

```powershell
uvicorn app.main:app --reload --app-dir backend
```

Alternatively, run it from inside the backend directory:

```powershell
cd backend
uvicorn app.main:app --reload
```

### Backend URLs

| Service | URL |
|---|---|
| API server | http://127.0.0.1:8000 |
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI specification | http://127.0.0.1:8000/openapi.json |
| Health check | http://127.0.0.1:8000/health |

Keep this terminal running while using the dashboard.

---

## 11. Run the React Dashboard

Open a **second terminal** from the project root.

Navigate to the frontend:

```powershell
cd frontend
```

Install frontend dependencies:

```powershell
npm install
```

Start the Vite development server:

```powershell
npm run dev
```

Open the dashboard at:

**http://localhost:5173**

### Dashboard Capabilities

The dashboard contains the following functional sections.

#### Overview

Displays:

- Total customers.
- Currently abandoned carts.
- Recovered carts.
- Attributed revenue.

#### Messaging Analytics

Displays:

- Total send attempts.
- Sent messages.
- Scheduled messages.
- Suppressed messages.
- Failed messages.
- Suppression rate.
- Suppression reason breakdown.
- Delivery, open, and click event counts.

#### Conversion Analytics

Displays:

- Completed orders.
- Attributed orders.
- Attributed order share.
- Purchased carts.
- Recovery rate snapshot.

#### Recovery Eligibility

Allows the operator to:

1. Enter a cart ID.
2. Select EMAIL or SMS.
3. Evaluate recovery eligibility.
4. Inspect the decision, consent information, frequency-cap status, and suppression reasons.

#### Campaign Scheduling

Allows the operator to:

1. Enter a cart ID.
2. Select a communication channel.
3. Provide a unique send ID.
4. Submit a scheduling request.
5. Inspect the resulting status, campaign, template, scheduled time, and suppression reason.

#### Conversion Attribution

Allows the operator to:

1. Enter a completed order ID.
2. Provide an attribution ID.
3. Submit an attribution request.
4. Inspect whether attribution was created, already existed, or was not eligible.

### Frontend–Backend Communication

The Vite development server proxies `/api` and `/health` requests to:

```text
http://127.0.0.1:8000
```

Both the frontend and backend servers must be running for the dashboard to retrieve live data.

### Production Build

To verify that the frontend compiles:

```powershell
cd frontend
npm run build
```

The generated `dist/` directory is ignored by Git.

**Deployment note:** The Vite proxy is a development-server feature. Production deployment requires configuring an API reverse proxy or appropriate backend URL and CORS settings.

---

## 12. API Reference

The backend exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Application status |
| GET | `/health` | Health check |
| GET | `/api/analytics/overview` | Aggregated dashboard metrics |
| POST | `/api/recovery/evaluate` | Evaluate cart recovery eligibility |
| POST | `/api/campaigns/schedule` | Schedule or suppress a recovery message |
| POST | `/api/attribution` | Evaluate and record qualifying attribution |

### 12.1 Recovery Eligibility

**Endpoint**

`POST /api/recovery/evaluate`

Example request:

```json
{
  "cart_id": "CART-2026-002157",
  "channel": "EMAIL"
}
```

Example response fields include:

- `cart_id`
- `customer_id`
- `channel`
- `decision`
- `eligible`
- `reasons`
- `evaluated_at`
- `abandonment_time`
- `active_consent_id`
- `sent_last_24h`
- `sent_last_7d`
- `frequency_caps`

### 12.2 Campaign Scheduling

**Endpoint**

`POST /api/campaigns/schedule`

Example request:

```json
{
  "cart_id": "CART-2026-002157",
  "channel": "EMAIL",
  "send_id": "SEND-DEMO-001"
}
```

A successful scheduling response can include:

```json
{
  "status": "SCHEDULED",
  "suppression_reason": null,
  "message": "Recovery message scheduled. No external message has been dispatched."
}
```

The complete response also contains send, cart, campaign, template, channel, and scheduling information.

### 12.3 Order Attribution

**Endpoint**

`POST /api/attribution`

Example request:

```json
{
  "order_id": "ORD-2026-000045",
  "attribution_id": "ATTR-DEMO-001"
}
```

The result depends on existing attribution records and qualifying recovery-message interactions.

For example, an order without an eligible clicked recovery message can return:

```json
{
  "status": "NOT_ATTRIBUTED",
  "order_id": "ORD-2026-000045",
  "reason": "NO_ELIGIBLE_CLICKED_MESSAGE"
}
```

### 12.4 Analytics Overview

**Endpoint**

`GET /api/analytics/overview`

The response contains grouped metrics for:

- Customers.
- Carts and recovery.
- Messaging attempts and engagement events.
- Suppression reasons.
- Completed orders.
- Attributed orders and revenue.
- Measurement limitations.

The dashboard uses this endpoint to display live data from the backend.

---

## 13. Analytics and Measurement Definitions

The dashboard provides operational analytics based on the generated database.

### Recovery Rate

The reported recovery rate is a **snapshot ratio** using recovered and currently abandoned carts. It is not a historical cohort-based recovery rate.

### Attribution Rate

The attributed order rate represents the proportion of completed orders with recorded attribution.

It should not be interpreted as the percentage of all abandoned carts recovered.

### Attributed Revenue

Attributed revenue represents the value of orders linked to qualifying recovery interactions.

It is **not a measure of incremental revenue**. Measuring incrementality would require additional methodology, such as controlled experiments or holdout groups.

### Engagement Metrics

Delivery, open, and click metrics count recorded events.

They are not necessarily unique customer or unique message engagement rates.

### Suppression Metrics

Suppression reasons are aggregated from recorded suppressed send attempts.

High suppression rates should be interpreted in the context of consent, communication frequency limits, and the synthetic data distribution.

---

## 14. Testing

The backend includes automated tests for database integrity and business logic.

From the project root, with the Python environment active:

```powershell
pytest -v
```

The test suite contains **25 tests**, previously verified as passing.

Coverage includes:

- Database integrity.
- Recovery eligibility.
- Campaign scheduling.
- Conversion attribution.

### Dashboard Integration Testing

The following workflows have also been manually exercised:

| Scenario | Observed result |
|---|---|
| Evaluate an eligible abandoned cart | `ELIGIBLE` |
| Schedule an eligible recovery message | `SCHEDULED` |
| Attempt attribution for an already attributed order | `ALREADY_ATTRIBUTED` |
| Attempt attribution without a qualifying clicked message | `NOT_ATTRIBUTED` |
| Load analytics from the backend | Successful |
| Build the React frontend | Successful |

A successful new attribution through the dashboard has not been separately verified in this manual test sequence.

These tests verify API behavior and frontend integration. They do not constitute production load testing or external message-delivery testing.

---

## 15. Currency Representation

Monetary values are stored as integers representing **paise**, the minor currency unit of INR.

Some legacy database columns use names ending in `_cents`, but their stored values represent paise rather than US cents.

For display purposes:

```text
INR amount = stored paise / 100
```

The dashboard formats attributed revenue in Indian rupees.

---

## 16. Known Limitations

- The application uses SQLite rather than a production-scale database.
- Synthetic data is used instead of real customer data.
- No external email or SMS provider integration is implemented.
- Scheduling does not automatically dispatch messages.
- No background delivery worker is implemented.
- The dashboard is intended for development and demonstration.
- Authentication and role-based access control are not implemented.
- Production deployment would require stronger concurrency handling, security, monitoring, and operational safeguards.
- Analytics are descriptive and do not establish campaign incrementality.
- The current attribution approach uses qualifying click interactions rather than causal measurement.
- The current recovery eligibility rules do not impose a maximum abandoned-cart age.

---

## 17. Reproducibility

The synthetic generator uses the fixed seed:

```text
20261022
```

To regenerate the dataset:

```powershell
python backend/generator/generate.py --reset
```

To validate the generated dataset:

```powershell
python backend/generator/validate.py
```

The repository retains canonical CSV exports and ground-truth data. The generated SQLite database and duplicate JSON exports are excluded from version control.

The repository also contains checksum files from earlier generation comparisons. These should not be treated as independently verified checksums of the final full-scale dataset.

Running the generator again with the same seed and configuration supports deterministic reproduction. Outputs may still depend on the implementation and dependency versions.

---

## 18. Technical Documentation

Additional documentation is available in the `docs/` directory.

| Document | Description |
|---|---|
| `SOLUTION_DESIGN.md` | System architecture, business logic, and technical decisions |
| `DATA_QUALITY_REPORT.md` | Dataset integrity checks and intentional anomaly analysis |
| `AI_ROADMAP.md` | Proposed AI/ML extensions and future improvements |

### Potential Future Enhancements

- Machine learning-based recovery propensity prediction.
- Personalized send-time optimization.
- Customer segmentation.
- Recovery-message recommendation.
- Provider integrations for email and SMS delivery.
- Background workers and delivery retries.
- Campaign experiments and holdout-based incrementality measurement.
- Authentication and role-based access control.
- Production monitoring and alerting.

These are future development opportunities, not features currently implemented.

---

## 19. Repository

**GitHub:** https://github.com/dhanshriii/CartRecover

**Project:** CartRecover — Abandoned Cart Recovery and Conversion Attribution System

**Purpose:** Demonstrate a working, consent-aware e-commerce recovery workflow, with reproducible synthetic data, business-rule enforcement, conversion attribution, and an interactive operational dashboard.