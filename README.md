
# CartRecover
### Abandoned Cart Recovery and Conversion Attribution System

CartRecover is a data-driven abandoned-cart recovery system that identifies abandoned shopping carts, evaluates customer consent and communication eligibility, schedules recovery campaigns, and attributes completed purchases to recovery messages.

## 1. Key Features

- Abandoned cart identification using configurable inactivity thresholds.
- Customer email and SMS consent validation.
- Consent withdrawal handling using effective dates.
- Frequency caps across communication channels.
- Quiet-hour scheduling.
- Campaign and message-template selection.
- Recovery message scheduling and suppression tracking.
- Message event tracking (delivery, bounce, open, click).
- Last-click conversion attribution.
- Duplicate attribution prevention.
- Deterministic synthetic data generation.
- Data-integrity validation and anomaly detection.
- REST API built with FastAPI.

**Important:** The current implementation schedules recovery messages but does not dispatch real emails or SMS messages through external providers.

## 2. Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| Data generation | Faker |
| Data processing | Pandas, NumPy |
| API documentation | Swagger / OpenAPI |
| Testing | Pytest |

## 3. Project Structure

```text
CartRecover/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── analytics.py
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   ├── models/
│   │   │   └── entities.py
│   │   ├── services/
│   │   │   ├── recovery_engine.py
│   │   │   ├── campaign_service.py
│   │   │   └── attribution_service.py
│   │   ├── database.py
│   │   └── main.py
│   ├── generator/
│   │   ├── generate.py
│   │   └── validate.py
│   ├── tests/
│   └── requirements.txt
├── data/
│   ├── exports/
│   ├── generated/
│   ├── ground_truth/
│   └── generation_summary.json
├── docs/
│   ├── SOLUTION_DESIGN.md
│   ├── DATA_QUALITY_REPORT.md
│   └── AI_ROADMAP.md
├── .gitignore
├── pytest.ini
└── README.md
```

## 4. Database Design

The system uses 12 relational entities.

| Entity | Purpose |
|---|---|
| Customer | Customer master information |
| Consent | Channel-specific consent history |
| CustomerSession | Customer browsing sessions |
| Cart | Shopping cart and lifecycle status |
| CartLine | Products and quantities in a cart |
| Campaign | Recovery campaign configuration |
| MessageTemplate | Campaign message templates |
| SendAttempt | Scheduled, sent, failed, and suppressed messages |
| Order | Completed and other purchase records |
| Attribution | Conversion attribution records |
| CartEvent | Cart lifecycle event history |
| MessageEvent | Delivery and engagement event history |

Primary keys, foreign keys, unique constraints, check constraints, and indexes enforce important data-integrity rules.

## 5. Business Rules

### Abandonment
- Default inactivity threshold: 180 minutes.
- Cart lifecycle states include ACTIVE, ABANDONED, PURCHASED, and RECOVERED.
- Carts with completed purchases are not eligible for recovery.

### Consent
- Consent is evaluated using effective start and end dates.
- The latest effective consent record determines the applicable status.
- Withdrawn consent prevents communication through that channel.

### Frequency Caps
- Maximum one successful send in a rolling 24-hour window.
- Maximum two successful sends in a rolling 7-day window.
- Frequency limits apply across channels.

### Quiet Hours
- Quiet hours: 9:00 PM to 8:00 AM.
- Messages scheduled during quiet hours are moved to the next allowed time.

### Conversion Attribution
- Only SENT messages qualify.
- Customer and cart must match the completed order.
- A CLICKED event must occur before the order.
- The click must fall within the campaign attribution window.
- The most recent eligible click receives attribution.
- Only one primary attribution is allowed per order.

## 6. Data Generation

The synthetic dataset is generated using a deterministic seed.

Default configuration:

| Parameter | Value |
|---|---:|
| Random seed | 20261022 |
| Scale | 1.0 |
| Customers | 30,000 |
| Carts | 50,000 |
| Sessions | 50,000 |
| Cart lines | 90,193 |
| Campaigns | 5 |
| Send attempts | 10,003 |
| Orders | 2,662 |

The generator also produces consent records, templates, cart events, message events, and attribution records.

Four intentional anomaly scenarios are included:
1. Message sent after consent withdrawal.
2. Cart considered abandoned despite a completed purchase.
3. Duplicate primary attribution for an order.
4. Cart total inconsistent with its cart-line totals.

The generated data includes ground-truth records for these scenarios.

## 7. Installation

Python 3.12 or later is recommended.

Clone or extract the project and navigate to its root directory.

Create a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r backend/requirements.txt
```

Set the Python import path:

```powershell
$env:PYTHONPATH = "backend"
```

## 8. Generate Data

From the project root:

```powershell
python backend/generator/generate.py --reset
```

For a smaller dataset:

```powershell
python backend/generator/generate.py --reset --scale 0.1
```

The generator uses a fixed seed to support reproducibility.

## 9. Validate Data

Run:

```powershell
python backend/generator/validate.py
```

The validator checks:
- Foreign-key violations.
- Duplicate identifiers.
- Cart-total inconsistencies.
- Customer and session consistency.
- Invalid consent and send conditions.
- Campaign and template consistency.
- Duplicate attribution.
- Frequency-cap violations.

The four intentionally injected anomalies should be distinguished from unexpected validation failures.

## 10. Run the API

From the project root:

```powershell
uvicorn app.main:app --reload
```

If the import path is not configured:

```powershell
uvicorn app.main:app --reload --app-dir backend
```

API documentation:

http://127.0.0.1:8000/docs

Health check:

http://127.0.0.1:8000/health

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/recovery/evaluate` | Evaluate cart recovery eligibility |
| POST | `/api/campaigns/schedule` | Schedule or suppress a recovery message |
| POST | `/api/attribution` | Attribute an eligible completed order |
| GET | `/` | Application status |
| GET | `/health` | Health check |

## 11. Run Tests

Run the complete test suite:

```powershell
pytest -v
```

The current test suite contains 25 passing tests covering database integrity, recovery eligibility, campaign scheduling, and conversion attribution.

## 12. Currency and Data Representation

Monetary values are stored as integers representing paise (INR minor units). Some legacy database column names use the suffix `_cents`; their stored values represent paise, not US cents.

## 13. Limitations

- The database is SQLite-based.
- External email and SMS delivery integrations are not implemented.
- API scheduling does not automatically dispatch messages.
- The dataset is synthetic and intended for development, demonstration, and evaluation.
- Production deployment would require additional concurrency controls, authentication, provider integrations, monitoring, and operational security.

## 14. Reproducibility

The generator uses a fixed seed of `20261022`.

Generated CSV and JSON exports, ground-truth records, and generation summaries are retained under the `data/` directory.

Checksums can be used to compare outputs across repeated generation runs.
