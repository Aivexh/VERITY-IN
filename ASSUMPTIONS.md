# VERITY Module 1 — Architectural Assumptions & Decisions

This document records architectural decisions and design choices made during the implementation of VERITY Module 1.

---

### Decision 1: Single Authorized Ledger Write Service (`create_financial_transaction`)

* **Decision**: All ledger database insertions into `financial_transactions` are restricted to `create_financial_transaction(db, intent_id, attempt_id)`.
* **Reason**: Enforces Invariants I8 and I9 (Single Ledger Write Path). Ensures database-level isolation and strict pre-commit validation.
* **Affected Component**: `app/services/ledger_service.py`, `app/api/incidents.py`.
* **Alternative Considered**: Allowing API route handlers or review service to insert directly into `financial_transactions`.
* **Risk**: None. Ensures financial safety and prevents multiple entry paths to ledger creation.

---

### Decision 2: Automatic Refusal of Financial Commitments on Ambiguous / Review States

* **Decision**: Aggregate states `POTENTIAL_DUPLICATE`, `CONFLICTING_STATE`, `INSUFFICIENT_EVIDENCE`, and `MANUAL_REVIEW` reject automated transactions and mandate explicit human reviewer action.
* **Reason**: Priority #1 (Financial Correctness and Safety) & Invariant I3.
* **Affected Component**: `app/truth_engine/truth_engine.py`, `app/services/ledger_service.py`.
* **Alternative Considered**: Using confidence heuristics to auto-select attempts above a high threshold.
* **Risk**: Increases manual review queue volume when payment webhooks exhibit high ambiguity, but completely eliminates unauthorized double-charging.

---

### Decision 3: Deterministic SHA-256 Event Deduplication Hash

* **Decision**: Deduplication hash is computed over canonical JSON formatting of `provider:provider_reference:event_type:amount:currency:event_created_at:raw_payload`.
* **Reason**: Guarantees Invariant I1 (Idempotency) and I5 (Immutable Evidence). Replaying identical events yields an idempotent HTTP 200 no-op.
* **Affected Component**: `app/services/ingestion_service.py`.
* **Alternative Considered**: Relying on client-provided event UUIDs.
* **Risk**: Requires providers to send stable event attributes.

---

### Decision 4: Fallback Template Engine for Explanation Endpoint

* **Decision**: The `/api/transactions/:id/explain` endpoint uses a deterministic structured template engine when `AI_ENABLED=false` or LLM is unreachable.
* **Reason**: Section 21 requirement: AI failure must never cause financial or API failure.
* **Affected Component**: `app/services/explanation_service.py`.
* **Alternative Considered**: Returning HTTP 503 when AI is disabled.
* **Risk**: None. Guarantees endpoint availability regardless of external AI service state.
