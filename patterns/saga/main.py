"""
Money Transfer — Saga Pattern demo.

Scenarios:
  1. Happy path       — Alice sends $200 to Bob
  2. Early failure    — Alice sends $9999 (insufficient funds, no money moves)
  3. Mid-saga failure — Bob sends $100 to a non-existent account
                        (debit succeeds, credit fails → debit is compensated)
"""

from patterns.saga.db import get_connection, init_db, reset_db, seed_accounts
from patterns.saga.orchestrator import SagaOrchestrator


def _print_balances(label: str = "") -> None:
    conn = get_connection()
    rows = conn.execute("SELECT id, owner, balance FROM accounts ORDER BY owner").fetchall()
    conn.close()
    print(f"\n  Balances {label}")
    for r in rows:
        print(f"    {r['owner']:<10} ({r['id']}):  ${r['balance']:.2f}")


def _print_saga_log(saga_id: str) -> None:
    conn = get_connection()
    saga  = conn.execute("SELECT status, created_at FROM sagas WHERE id = ?", (saga_id,)).fetchone()
    steps = conn.execute(
        "SELECT step_name, status, result FROM saga_steps WHERE saga_id = ? ORDER BY id",
        (saga_id,),
    ).fetchall()
    conn.close()

    print(f"\n  Saga log [{saga_id[:8]}...]  status={saga['status']}")
    for s in steps:
        print(f"    [{s['status']:<12}]  {s['step_name']}")
        if s["result"]:
            print(f"                    {s['result']}")


def run() -> None:
    reset_db()
    seed_accounts()

    orchestrator = SagaOrchestrator()

    # ------------------------------------------------------------------
    print("\n" + "#" * 62)
    print("# SCENARIO 1: Happy Path — Alice sends $200 to Bob")
    print("#" * 62)
    _print_balances("before")
    saga_id = orchestrator.start("ACC-001", "ACC-002", 200)
    _print_balances("after")
    _print_saga_log(saga_id)

    # ------------------------------------------------------------------
    print("\n" + "#" * 62)
    print("# SCENARIO 2: Insufficient Funds — Alice tries to send $9999")
    print("#" * 62)
    _print_balances("before")
    saga_id = orchestrator.start("ACC-001", "ACC-003", 9999)
    _print_balances("after (unchanged)")
    _print_saga_log(saga_id)

    # ------------------------------------------------------------------
    print("\n" + "#" * 62)
    print("# SCENARIO 3: Mid-Saga Failure")
    print("#   Bob sends $100 to a ghost account.")
    print("#   Debit succeeds → credit fails → debit is compensated.")
    print("#" * 62)
    _print_balances("before")
    saga_id = orchestrator.start("ACC-002", "ACC-GHOST", 100)
    _print_balances("after (Bob's $100 restored)")
    _print_saga_log(saga_id)
