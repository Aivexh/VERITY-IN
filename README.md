<div align="center">

# VERITY

### Deterministic Financial Truth Engine

Verity reconciles conflicting payment observations from merchant, gateway, bank and webhook systems and decides what is **safe to commit to the ledger**. When evidence is ambiguous, it sends the case to manual review instead of guessing.

**[Live Demo](https://verity-1-drxq.onrender.com/)** · **[Canonical Investigation](https://verity-1-drxq.onrender.com/transactions/tx_canonical_retry_001)** · **[Naive vs VERITY](https://verity-1-drxq.onrender.com/compare/tx_canonical_retry_001)**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=fff)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=fff)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=fff)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=fff)
[![Live](https://img.shields.io/badge/demo-live-brightgreen)](https://verity-1-drxq.onrender.com/)

[Problem](#the-problem) · [Live Demo](#live-demo) · [Guarantees](#guarantees) · [Architecture](#architecture) · [Quick Start](#quick-start) · [API](#api) · [Testing](#testing) · [Team](#team)

</div>

---

## The Problem

A gateway times out, the merchant retries, and now the bank shows two successes while the webhook is still delayed.

```
Attempt 1 → Gateway timeout
Attempt 2 → Gateway SUCCESS · Bank SUCCESS · Webhook DELAYED
```

Verity sees **₹4,000** of exposure but can only attribute **₹2,000** to a legitimate payment intent. Booking ₹4,000 would be wrong, so Verity treats uncertainty as a first-class state and commits nothing until it is safe.

> Observed payment activity is not automatically financial truth.

## Live Demo

**https://verity-1-drxq.onrender.com/**

> Hosted on Render. The first load may be slow if the service is waking up.

| Page | What it shows |
|---|---|
| [Command Center](https://verity-1-drxq.onrender.com/) | Real-time monitor of payment intent resolution and duplicate-commitment prevention |
| [Investigation](https://verity-1-drxq.onrender.com/transactions/tx_canonical_retry_001) | Drill-down into the canonical retry transaction |
| [Compare (Naive vs VERITY)](https://verity-1-drxq.onrender.com/compare/tx_canonical_retry_001) | Side-by-side outcome of a naive system vs Verity |
| [Simulation Center](https://verity-1-drxq.onrender.com/simulate) | Run deterministic scenarios |
| [Live Incident](https://verity-1-drxq.onrender.com/live/run_demo_001) | Follow an incident as it unfolds |
| [Reliability](https://verity-1-drxq.onrender.com/reliability) | Reliability view of the engine |

**30-second tour:** open the Command Center → click *Launch Demo Investigation* → open *Compare* to see the naive system book ₹4,000 while Verity commits ₹0 and flags the case for review.

## Guarantees

| ID | Guarantee |
|---|---|
| I1 | **Idempotency:** replaying duplicate events has no extra financial effect |
| I2 | **Determinism:** `generate(scenario, seed)` always produces the same events |
| I3 / I7 | **Safe ambiguity:** `POTENTIAL_DUPLICATE`, `CONFLICTING_STATE`, `INSUFFICIENT_EVIDENCE`, `MANUAL_REVIEW` never auto-create a transaction |
| I4 | **One transaction per intent:** enforced by a DB uniqueness constraint on `intent_id` |
| I5 | **Immutable events:** observations are append-only |
| I8 / I9 | **Single ledger write path:** transactions are created only through one authorized route |

`MANUAL_REVIEW` is a successful safety outcome, not a failure.

## Architecture

```mermaid
flowchart TB
    A[Merchant / Gateway / Bank / Webhook] --> B[Event Ingestion]
    B --> C[Reconciliation Engine]
    C --> D[Duplicate & Conflict Detection]
    D --> E{Safe to commit?}
    E -->|Yes| F[Ledger Transaction]
    E -->|No| G[Incident + Manual Review]
    G --> H[Reviewer Decision]
    F --> I[Dashboard]
    H --> I
```

Events are stored immutably, grouped by payment intent and attempt, and compared across providers. Only a safe interpretation reaches the ledger.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.12, SQLAlchemy, Alembic, Pydantic |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, TanStack Query |
| Database | PostgreSQL |
| Testing | Pytest, Hypothesis |
| Infra | Docker Compose, Render (demo hosting) |

## Project Structure

```
Verity/
├── app/          # FastAPI backend
├── src/          # Next.js frontend
├── tests/        # Unit, API and property-based tests
├── migrations/   # Alembic migrations
├── scripts/      # Helper scripts
├── docker-compose.yml
├── .env.example
└── ASSUMPTIONS.md
```

## Quick Start

**Requirements:** Docker and Docker Compose. (Without Docker: Python 3.12+, Node.js 18+, PostgreSQL.)

```bash
git clone https://github.com/AlphaStorm-X/Verity.git
cd Verity
cp .env.example .env
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

**Without Docker**

```bash
# backend
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

# frontend
npm install
npm run dev
```

## Configuration

| Variable | Purpose | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Yes |

## Canonical Scenario

```bash
curl -X POST "http://localhost:8000/api/simulations/CANONICAL_DEMO/run?seed=42"
```

| Metric | Result |
|---|---|
| Observed exposure | ₹4,000 |
| Candidate legitimate amount | ₹2,000 |
| Committed to ledger | ₹0 |
| State | `POTENTIAL_DUPLICATE` / `MANUAL_REVIEW` |

Then open the dashboard, inspect the timeline and incident, and submit a review decision (`CONFIRM_ATTEMPT` or `MARK_DUPLICATE`).

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/events` | Ingest a payment observation |
| GET | `/api/events` | List events |
| GET | `/api/transactions` | List transactions |
| GET | `/api/transactions/:id` | Transaction details |
| GET | `/api/transactions/:id/timeline` | Event timeline |
| GET | `/api/transactions/:id/analysis` | Reconciliation analysis |
| POST | `/api/transactions/:id/explain` | Generate explanation |
| GET | `/api/incidents` | List incidents |
| GET | `/api/incidents/:id` | Incident details |
| POST | `/api/incidents/:id/review` | Review an incident |
| POST | `/api/simulations` | Create simulation |
| POST | `/api/simulations/:id/run` | Run simulation |
| GET | `/api/dashboard` | Dashboard metrics |

## Testing

```bash
pytest      # backend, incl. Hypothesis property-based tests
npm test    # frontend
```

Property-based tests check invariants such as *duplicate replay → no additional financial effect* and *ambiguous state → no automatic ledger transaction*.

## Limitations

Demonstration system, not a production payment processor. No compliance claims are made. Not yet implemented: authentication, real provider integrations, streaming ingestion at scale, production observability.

## Contributing

Fork → clone → branch → install dependencies → `pytest && npm test` → make changes → run tests again → open a PR. Changes to the ledger write path must preserve the guarantees above.

## Team

| Contributor | GitHub |
|---|---|
| Monika Yadav | [@AlphaStorm-X](https://github.com/AlphaStorm-X) |
| Kashish | [@Kashish-17-06](https://github.com/Kashish-17-06) |
| Aivexh | [@Aivexh](https://github.com/Aivexh) |
