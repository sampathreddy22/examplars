"""
Saga Orchestrator — drives steps forward, compensates in reverse on failure.

Every step is persisted in saga_steps before and after execution so the saga
state is fully recoverable after a crash.
"""

import json
import uuid
from datetime import datetime, timezone

from patterns.saga.db import get_connection, transaction
from patterns.saga.steps import (
    StepFailure,
    compensate_credit_destination,
    compensate_debit_source,
    compensate_record_transfer,
    compensate_validate_transfer,
    credit_destination,
    debit_source,
    record_transfer,
    validate_transfer,
)

# Ordered steps: (name, forward, compensating)
TRANSFER_STEPS = [
    ("validate_transfer", validate_transfer, compensate_validate_transfer),
    ("debit_source", debit_source, compensate_debit_source),
    ("credit_destination", credit_destination, compensate_credit_destination),
    ("record_transfer", record_transfer, compensate_record_transfer),
]


class SagaOrchestrator:

    def start(self, from_account: str, to_account: str, amount: float) -> str:
        saga_id = str(uuid.uuid4())
        payload = {
            "saga_id": saga_id,
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
        }

        conn = get_connection()
        with transaction(conn):
            conn.execute(
                "INSERT INTO sagas (id, type, status, payload) VALUES (?, 'MONEY_TRANSFER', 'STARTED', ?)",
                (saga_id, json.dumps(payload)),
            )
        conn.close()

        print(f"\n{'='*62}")
        print(f"  SAGA {saga_id[:8]}...  STARTED")
        print(f"  {from_account} -> {to_account}   amount=${amount:.2f}")
        print(f"{'='*62}")

        completed: list[tuple[str, object, int]] = []

        for step_name, forward_fn, compensate_fn in TRANSFER_STEPS:
            conn = get_connection()
            step_id = self._insert_step(conn, saga_id, step_name)

            try:
                with transaction(conn):
                    result = forward_fn(conn, payload)
                    self._update_step(conn, step_id, "COMPLETED", result)

                print(f"  [OK]   {step_name}")
                print(f"         {result}")
                completed.append((step_name, compensate_fn, step_id))

            except (StepFailure, Exception) as exc:
                conn2 = get_connection()
                with transaction(conn2):
                    self._update_step(conn2, step_id, "FAILED", str(exc))
                conn2.close()

                print(f"  [FAIL] {step_name}")
                print(f"         {exc}")
                conn.close()
                self._compensate(saga_id, payload, completed)
                return saga_id

            finally:
                conn.close()

        self._set_saga_status(saga_id, "COMPLETED")
        print(f"\n  SAGA {saga_id[:8]}...  COMPLETED")
        return saga_id

    # ------------------------------------------------------------------

    def _insert_step(self, conn, saga_id: str, step_name: str) -> int:
        cursor = conn.execute(
            "INSERT INTO saga_steps (saga_id, step_name, status, executed_at) VALUES (?, ?, 'IN_PROGRESS', ?)",
            (saga_id, step_name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid

    def _update_step(self, conn, step_id: int, status: str, result: str) -> None:
        conn.execute(
            "UPDATE saga_steps SET status = ?, result = ? WHERE id = ?",
            (status, result, step_id),
        )

    def _set_saga_status(self, saga_id: str, status: str) -> None:
        conn = get_connection()
        with transaction(conn):
            conn.execute(
                "UPDATE sagas SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status, saga_id),
            )
        conn.close()

    def _compensate(
        self,
        saga_id: str,
        payload: dict,
        completed: list[tuple[str, object, int]],
    ) -> None:
        print("\n  --- Compensation started (reverse order) ---")
        self._set_saga_status(saga_id, "COMPENSATING")

        for step_name, compensate_fn, step_id in reversed(completed):
            conn = get_connection()
            try:
                with transaction(conn):
                    result = compensate_fn(conn, payload)
                    self._update_step(conn, step_id, "COMPENSATED", result)
                print(f"  [COMP] {step_name}")
                print(f"         {result}")
            except Exception as exc:
                print(f"  [COMP-FAIL] {step_name}: {exc}")
                print("  *** MANUAL INTERVENTION REQUIRED ***")
            finally:
                conn.close()

        self._set_saga_status(saga_id, "COMPENSATED")
        print(f"\n  SAGA {saga_id[:8]}...  COMPENSATED")
