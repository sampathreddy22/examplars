# Saga Pattern — Money Transfer

## What Problem Does It Solve?

In a monolith you wrap everything in a single database transaction — if anything fails, the whole thing rolls back atomically. In a distributed system (microservices, separate databases) **there is no global transaction**. You can't hold a lock across two services.

The Saga pattern solves this by breaking a long-running operation into a **sequence of local transactions**, each with a **compensating transaction** that undoes it if a later step fails.

> "Instead of ACID across services, you get eventual consistency with explicit rollback logic."

---

## Two Styles of Saga

| Style | How it works | When to use |
|---|---|---|
| **Orchestration** | A central coordinator tells each service what to do | Easier to reason about, audit, and debug |
| **Choreography** | Each service listens for events and reacts | Looser coupling, harder to trace |

This implementation uses **orchestration** — the `SagaOrchestrator` drives every step and decides what to compensate.

---

## Core Concepts

### Local Transaction
Each step reads/writes only its own data and commits immediately. There is no waiting for other steps.

### Compensating Transaction
The **semantic undo** of a completed step. Not a SQL rollback — the step already committed. A compensation is a new write that reverses the effect.

```
debit_source          →  compensate_debit_source
credit_destination    →  compensate_credit_destination
record_transfer       →  compensate_record_transfer
validate_transfer     →  (no-op — made no writes)
```

### Saga Log
Every step's status is persisted before and after execution. If the process crashes mid-saga, the log tells you exactly where to resume or which compensations to replay.

---

## Money Transfer Steps

```
┌─────────────────────────────────────────────────────────────┐
│                   MONEY TRANSFER SAGA                       │
│                                                             │
│  Step 1: validate_transfer                                  │
│          Check source balance ≥ amount                      │
│          Check source account exists                        │
│          (no writes — compensation is a no-op)              │
│                                                             │
│  Step 2: debit_source                                       │
│          balance = balance - amount  (source account)       │
│          ↳ compensate: balance = balance + amount           │
│                                                             │
│  Step 3: credit_destination                                 │
│          balance = balance + amount  (dest account)         │
│          ↳ compensate: balance = balance - amount           │
│                                                             │
│  Step 4: record_transfer                                    │
│          Write audit log entry (status = COMPLETED)         │
│          ↳ compensate: update status = COMPENSATED          │
└─────────────────────────────────────────────────────────────┘
```

---

## Flow Diagrams

### Scenario 1 — Happy Path

```
Orchestrator          DB (accounts)         DB (sagas / steps)
     │                      │                       │
     │── INSERT saga ───────────────────────────────▶│ status=STARTED
     │                      │                       │
     │── validate ──────────▶ (read-only)            │
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── debit $200 ────────▶ Alice: 1000 → 800      │
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── credit $200 ───────▶ Bob:   500  → 700      │
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── write audit log ───▶ transfer_log row       │
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── saga: COMPLETED ───────────────────────────▶│
     │                      │                       │

Result: Alice=$800  Bob=$700   Saga=COMPLETED
```

---

### Scenario 2 — Early Failure (Insufficient Funds)

Validation fails before any write touches balances. Compensation is a no-op.

```
Orchestrator          DB (accounts)         DB (sagas / steps)
     │                      │                       │
     │── INSERT saga ───────────────────────────────▶│ status=STARTED
     │                      │                       │
     │── validate ──────────▶ balance=800 < 9999     │
     │◀─ FAIL ──────────────│                       │
     │── step: FAILED ──────────────────────────────▶│
     │                      │                       │
     │  [no compensations — nothing was written]     │
     │                      │                       │
     │── saga: COMPENSATED ─────────────────────────▶│
     │                      │                       │

Result: balances unchanged   Saga=COMPENSATED
```

---

### Scenario 3 — Mid-Saga Failure (Ghost Account)

The debit succeeds and commits. The credit then fails. The orchestrator runs compensations **in reverse order**.

```
Orchestrator          DB (accounts)         DB (sagas / steps)
     │                      │                       │
     │── INSERT saga ───────────────────────────────▶│ status=STARTED
     │                      │                       │
     │── validate ──────────▶ (read-only, passes)    │
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── debit $100 ────────▶ Bob: 700 → 600         │ ← committed!
     │◀─ ok ────────────────│                       │
     │── step: COMPLETED ───────────────────────────▶│
     │                      │                       │
     │── credit $100 ───────▶ ACC-GHOST not found    │
     │◀─ FAIL ──────────────│                       │
     │── step: FAILED ──────────────────────────────▶│
     │                      │                       │
     │       ╔══ COMPENSATION (reverse order) ══╗    │
     │       ║                                  ║    │
     │── compensate debit ──▶ Bob: 600 → 700     ║    │ ← reversed!
     │◀─ ok ────────────────│                   ║    │
     │── step: COMPENSATED ─────────────────────║───▶│
     │                      │                   ║    │
     │── compensate validate▶ (no-op)            ║    │
     │── step: COMPENSATED ─────────────────────╚───▶│
     │                      │                       │
     │── saga: COMPENSATED ─────────────────────────▶│
     │                      │                       │

Result: Bob=$700 (restored)   Saga=COMPENSATED
```

---

## Database Schema

```
┌──────────────┐        ┌───────────────────────────┐
│   accounts   │        │          sagas             │
├──────────────┤        ├───────────────────────────┤
│ id     TEXT  │        │ id         TEXT  PK        │
│ owner  TEXT  │        │ type       TEXT            │
│ balance REAL │        │ status     TEXT            │
│  CHECK ≥ 0   │        │   STARTED                 │
└──────────────┘        │   COMPENSATING            │
                        │   COMPLETED               │
                        │   COMPENSATED             │
                        │ payload    TEXT  (JSON)    │
                        │ created_at TEXT            │
                        │ updated_at TEXT            │
                        └────────────┬──────────────┘
                                     │ 1
                                     │
                                     │ N
                        ┌────────────▼──────────────┐
                        │        saga_steps          │
                        ├───────────────────────────┤
                        │ id          INT   PK       │
                        │ saga_id     TEXT  FK       │
                        │ step_name   TEXT           │
                        │ status      TEXT           │
                        │   IN_PROGRESS             │
                        │   COMPLETED               │
                        │   FAILED                  │
                        │   COMPENSATED             │
                        │ result      TEXT           │
                        │ executed_at TEXT           │
                        └───────────────────────────┘

                        ┌───────────────────────────┐
                        │       transfer_log         │
                        ├───────────────────────────┤
                        │ id           INT   PK      │
                        │ saga_id      TEXT          │
                        │ from_account TEXT          │
                        │ to_account   TEXT          │
                        │ amount       REAL          │
                        │ status       TEXT          │
                        │   COMPLETED               │
                        │   COMPENSATED             │
                        │ created_at   TEXT          │
                        └───────────────────────────┘
```

---

## Saga Lifecycle State Machine

```
              ┌─────────┐
              │ STARTED │
              └────┬────┘
                   │ all steps succeed
          ┌────────▼────────┐
          │   COMPLETED     │
          └─────────────────┘

              ┌─────────┐
              │ STARTED │
              └────┬────┘
                   │ any step fails
         ┌─────────▼──────────┐
         │   COMPENSATING     │
         └─────────┬──────────┘
                   │ all compensations done
         ┌─────────▼──────────┐
         │   COMPENSATED      │
         └────────────────────┘
```

---

## Key Trade-offs

| Property | Saga | Distributed 2PC |
|---|---|---|
| Availability | High (no global lock) | Low (coordinator is SPOF) |
| Consistency | Eventual | Strong |
| Complexity | Explicit compensation logic | Protocol complexity |
| Failure visibility | Full audit log per step | Opaque lock state |
| Recovery | Replay from saga log | Coordinator restart |

**Sagas expose intermediate state.** Between step 2 (debit) and step 3 (credit), another observer could briefly see Bob's balance unchanged and Alice's balance reduced. This is the trade-off for not holding a global lock.

---

## Running

```bash
uv run examplars saga
```

The DB is recreated fresh on every run at `data/saga.db`.

---

## Project Layout

```
patterns/saga/
├── README.md          ← you are here
├── __init__.py
├── db.py              ← schema, seed, reset
├── steps.py           ← forward + compensating functions
├── orchestrator.py    ← saga engine (drives steps, triggers compensation)
└── main.py            ← 3 demo scenarios
```
