"""
main.py
--------
CoreLock demo orchestration.

Run with:
    python -m corelock.main

This wires together all 6 backend modules (Transaction Manager, Scheduler,
Execution Engine, Lock Manager, Deadlock Manager, Recovery Manager) around
the Movie Ticket Booking seat inventory, and runs three demo scenarios:

  1. Normal flow      - Alice books A1-A2, commits successfully.
  2. Voluntary rollback - Bob holds B1-B2 then rolls back (seats freed).
  3. Conflict abort    - Charlie tries to book Alice's already-BOOKED
                          seats (A1-A2) -> immediately aborted.
  4. Deadlock          - Dave wants seats [C1, C2] in that order, Eve wants
                          [C2, C1] in that order, both start at once ->
                          circular wait -> Deadlock Manager detects the
                          cycle and rolls back one victim.
  5. Crash & Recovery  - simulate a crash where a seat's payment "wrote
                          through" but never committed, then recover().

At the end it prints the OS-scheduler's execution order (for the Gantt
chart), the final seat grid, and the recovery report.
"""

import time

from .seat_inventory import Cinema
from .transaction_manager import TransactionManager
from .lock_manager import LockManager
from .scheduler import Scheduler, Algorithm
from .execution_engine import ExecutionEngine
from .recovery_manager import RecoveryManager


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_seat_grid(cinema: Cinema, show_id: str):
    show = cinema.get_show(show_id)
    print(f"\nSeat grid for show {show_id} ({show.movie} @ {show.time}):")
    for r in range(show.rows):
        row_letter = chr(ord("A") + r)
        cells = []
        for c in range(1, show.cols + 1):
            seat = show.get_seat(f"{row_letter}{c}")
            symbol = {"AVAILABLE": ".", "LOCKED": "L", "BOOKED": "X"}[seat.state.value]
            cells.append(symbol)
        print(f"  Row {row_letter}: " + " ".join(cells))
    print("  Legend: . = available, L = locked, X = booked")


def main():
    cinema = Cinema.seed_demo_data()
    show_id = "S101"

    txn_manager = TransactionManager()
    lock_manager = LockManager(wait_timeout=1.5)
    scheduler = Scheduler(algorithm=Algorithm.PRIORITY)
    recovery_manager = RecoveryManager()
    engine = ExecutionEngine(cinema, txn_manager, lock_manager, scheduler,
                              recovery_manager, max_concurrent=4)
    engine.start_monitor()

    # ---------------------------------------------------------------- Scenario 1-3
    print_header("SCENARIO 1-3: Normal booking, voluntary rollback, conflict abort")

    alice = txn_manager.create_transaction("Alice", show_id, ["A1", "A2"], priority=1)
    bob = txn_manager.create_transaction("Bob", show_id, ["B1", "B2"], priority=3)

    scheduler.add(alice)
    scheduler.add(bob)
    batch = scheduler.next_batch(2)

    # Alice commits normally; Bob holds his seats for a moment then rolls back.
    engine.run_all_threaded(
        batch,
        hold_map={bob.txn_id: 0.3},
        commit_map={bob.txn_id: False},
    )

    # Charlie now tries to book Alice's seats, which are already BOOKED.
    charlie = txn_manager.create_transaction("Charlie", show_id, ["A1", "A2"], priority=2)
    scheduler.add(charlie)
    engine.run_all_threaded(scheduler.next_batch(1))

    print_seat_grid(cinema, show_id)

    # ---------------------------------------------------------------- Scenario 4
    print_header("SCENARIO 4: Deadlock (circular wait) between Dave and Eve")

    dave = txn_manager.create_transaction("Dave", show_id, ["C1", "C2"], priority=4)
    eve = txn_manager.create_transaction("Eve", show_id, ["C2", "C1"], priority=4)
    scheduler.add(dave)
    scheduler.add(eve)
    deadlock_batch = scheduler.next_batch(2)

    # Both hold their first seat for long enough that they collide on the second,
    # producing a genuine circular wait for the Deadlock Manager to catch.
    engine.run_all_threaded(
        deadlock_batch,
        hold_map={dave.txn_id: 0.5, eve.txn_id: 0.5},
    )

    print("\nDeadlock cycles detected during this run:")
    for cycle in engine.deadlock_manager.cycle_history():
        print("  " + " -> ".join(cycle))

    print_seat_grid(cinema, show_id)

    # ---------------------------------------------------------------- Scenario 5
    print_header("SCENARIO 5: Crash & Recovery")

    print("Simulating a crash: seat D1 gets a dirty BOOKED write with no COMMIT logged...")
    engine.recovery_manager.simulate_crash(cinema, "D1", show_id)
    print_seat_grid(cinema, show_id)

    print("\nRunning recovery (UNDO uncommitted writes, REDO committed-but-missing ones)...")
    report = engine.recovery_manager.recover(cinema)
    print(f"  UNDO applied to: {report['undone']}")
    print(f"  REDO applied to: {report['redone']}")

    print_seat_grid(cinema, show_id)

    # ---------------------------------------------------------------- Summary
    print_header("SCHEDULER EXECUTION ORDER (for Gantt chart)")
    print(" -> ".join(scheduler.gantt_snapshot()))

    print_header("TRANSACTION SUMMARY")
    for snap in txn_manager.all_snapshots():
        print(snap)

    print_header("EVENT LOG")
    for line in engine.get_event_log():
        print(line)

    engine.stop_monitor()


if __name__ == "__main__":
    main()
