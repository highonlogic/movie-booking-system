"""CoreLock orchestration entry point.

Currently demos Module 1 (Transaction Manager) on a 10x10 demo show.
"""

from __future__ import annotations

from corelock.seat_inventory import SeatInventory
from corelock.transaction_manager import TransactionError, TransactionManager, TransactionState


def _print_txn(txn) -> None:
    print(f"  {txn.txn_id} | user={txn.request.user_id} | state={txn.state.value}")
    for op in txn.operations:
        seat = f" seat={op.seat}" if op.seat else ""
        print(f"    {op.op_type.value}{seat} — {op.detail}")


def demo_module_1() -> None:
    inventory = SeatInventory()
    inventory.seed_demo_cinema()
    tm = TransactionManager(inventory)
    show = inventory.get_show("SHOW-1")

    print("=== CoreLock Module 1: Transaction Manager ===")
    print(f"Show: {show.movie} @ {show.start_time} on {show.screen_id}")
    print(f"Grid: {show.rows}x{show.cols}  initial counts={show.counts()}\n")

    # Happy path: cart hold → payment WRITE → COMMIT
    t1 = tm.create_transaction("U-alice", "SHOW-1", seats=[(0, 0), (0, 1)], priority=1)
    tm.begin(t1.txn_id)
    tm.read(t1.txn_id)
    print(f"After Alice READ (cart hold): {show.counts()}")
    tm.write(t1.txn_id)
    tm.commit(t1.txn_id)
    print(f"After Alice COMMIT: {show.counts()}")
    _print_txn(t1)

    # Rollback path: hold seats then abort
    t2 = tm.create_transaction("U-bob", "SHOW-1", seats=[(1, 0)], priority=0)
    tm.begin(t2.txn_id)
    tm.read(t2.txn_id)
    print(f"\nAfter Bob READ: {show.counts()}")
    tm.rollback(t2.txn_id, reason="user cancelled payment")
    print(f"After Bob ROLLBACK: {show.counts()}")
    _print_txn(t2)

    # Conflict: Charlie tries Alice's already-booked seats
    t3 = tm.create_transaction("U-charlie", "SHOW-1", seats=[(0, 0)])
    tm.begin(t3.txn_id)
    try:
        tm.read(t3.txn_id)
    except TransactionError as exc:
        print(f"\nCharlie conflict (expected): {exc}")
    print(f"Charlie final state: {t3.state.value}")
    assert t1.state == TransactionState.COMMITTED
    assert t2.state == TransactionState.ABORTED
    assert t3.state == TransactionState.ABORTED
    print("\nModule 1 demo complete.")


if __name__ == "__main__":
    demo_module_1()
