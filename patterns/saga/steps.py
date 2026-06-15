"""
Saga steps and their compensating transactions for money transfer.

Each forward function raises StepFailure on a business error.
Each compensate function is the exact inverse of its forward counterpart.
"""

import sqlite3


class StepFailure(Exception):
    pass


# ---------------------------------------------------------------------------
# Step 1 — Validate transfer (read-only; compensation is a no-op)
# ---------------------------------------------------------------------------

def validate_transfer(conn: sqlite3.Connection, payload: dict) -> str:
    from_id = payload["from_account"]
    amount  = payload["amount"]

    if amount <= 0:
        raise StepFailure(f"Invalid amount: {amount}")

    row = conn.execute("SELECT balance FROM accounts WHERE id = ?", (from_id,)).fetchone()
    if not row:
        raise StepFailure(f"Source account {from_id} not found")
    if row["balance"] < amount:
        raise StepFailure(
            f"Insufficient funds in {from_id}: balance={row['balance']:.2f}, needed={amount}"
        )

    # Destination existence is intentionally checked at credit time,
    # mirroring a real distributed system where the destination service
    # is separate and may fail independently.
    return f"Validated: {from_id} -> {payload['to_account']}  amount={amount}"


def compensate_validate_transfer(conn: sqlite3.Connection, payload: dict) -> str:
    return "No-op (validation makes no writes)"


# ---------------------------------------------------------------------------
# Step 2 — Debit source account
# ---------------------------------------------------------------------------

def debit_source(conn: sqlite3.Connection, payload: dict) -> str:
    from_id = payload["from_account"]
    amount  = payload["amount"]

    cursor = conn.execute(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, from_id)
    )
    if cursor.rowcount == 0:
        raise StepFailure(f"Account {from_id} not found during debit")

    balance = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (from_id,)
    ).fetchone()["balance"]
    return f"Debited {amount} from {from_id}  (new balance: {balance:.2f})"


def compensate_debit_source(conn: sqlite3.Connection, payload: dict) -> str:
    """Credit the amount back — exact inverse of debit_source."""
    from_id = payload["from_account"]
    amount  = payload["amount"]

    conn.execute(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, from_id)
    )
    balance = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (from_id,)
    ).fetchone()["balance"]
    return f"Reversed: credited {amount} back to {from_id}  (new balance: {balance:.2f})"


# ---------------------------------------------------------------------------
# Step 3 — Credit destination account
# ---------------------------------------------------------------------------

def credit_destination(conn: sqlite3.Connection, payload: dict) -> str:
    to_id  = payload["to_account"]
    amount = payload["amount"]

    cursor = conn.execute(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, to_id)
    )
    if cursor.rowcount == 0:
        raise StepFailure(f"Account {to_id} not found during credit")

    balance = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (to_id,)
    ).fetchone()["balance"]
    return f"Credited {amount} to {to_id}  (new balance: {balance:.2f})"


def compensate_credit_destination(conn: sqlite3.Connection, payload: dict) -> str:
    """Debit the amount back — exact inverse of credit_destination."""
    to_id  = payload["to_account"]
    amount = payload["amount"]

    conn.execute(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, to_id)
    )
    balance = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (to_id,)
    ).fetchone()["balance"]
    return f"Reversed: debited {amount} back from {to_id}  (new balance: {balance:.2f})"


# ---------------------------------------------------------------------------
# Step 4 — Record transfer in audit log
# ---------------------------------------------------------------------------

def record_transfer(conn: sqlite3.Connection, payload: dict) -> str:
    conn.execute(
        """INSERT INTO transfer_log (saga_id, from_account, to_account, amount, status)
           VALUES (?, ?, ?, ?, 'COMPLETED')""",
        (payload["saga_id"], payload["from_account"], payload["to_account"], payload["amount"]),
    )
    return f"Audit log entry written for saga {payload['saga_id'][:8]}..."


def compensate_record_transfer(conn: sqlite3.Connection, payload: dict) -> str:
    conn.execute(
        "UPDATE transfer_log SET status = 'COMPENSATED' WHERE saga_id = ?",
        (payload["saga_id"],),
    )
    return f"Audit log marked COMPENSATED for saga {payload['saga_id'][:8]}..."
