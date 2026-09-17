"""
execution_engine.py
----------------------
Module 3: Concurrent Execution Engine

Simulates multiple users booking seats AT THE SAME TIME using real Python
threads (each transaction runs on its own thread, so genuine race
conditions can occur without the Lock Manager). A semaphore caps how many
transactions run truly concurrently (simulating limited "worker" capacity,
similar to an OS limiting concurrently running processes), and a
background monitor thread periodically asks the Deadlock Manager to check
for cycles.

This module is the glue: it pulls transactions from the Scheduler, runs
them through Lock Manager -> critical section (seat read/write) ->
Recovery Manager logging -> Commit/Rollback, while the Deadlock Manager
watches for cycles in the background.
"""

import threading
import time
from typing import List

from .transaction_manager import TransactionManager, Transaction, OpType
from .lock_manager import LockManager, LockType
from .scheduler import Scheduler
from .deadlock_manager import DeadlockManager
from .recovery_manager import RecoveryManager
from .seat_inventory import Cinema, SeatState


class ExecutionEngine:
    def __init__(self, cinema: Cinema, txn_manager: TransactionManager,
                 lock_manager: LockManager, scheduler: Scheduler,
                 recovery_manager: RecoveryManager, max_concurrent: int = 4):
        self.cinema = cinema
        self.txn_manager = txn_manager
        self.lock_manager = lock_manager
        self.scheduler = scheduler
        self.recovery_manager = recovery_manager
        self.deadlock_manager = DeadlockManager(lock_manager, txn_manager)

        self._semaphore = threading.Semaphore(max_concurrent)  # limits concurrent "running processes"
        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(target=self._deadlock_monitor_loop, daemon=True)
        self.event_log: List[str] = []
        self._event_lock = threading.Lock()

    # ---- public control --------------------------------------------------------
    def start_monitor(self):
        self._monitor_thread.start()

    def stop_monitor(self):
        self._monitor_stop.set()

    def _deadlock_monitor_loop(self):
        while not self._monitor_stop.is_set():
            victim = self.deadlock_manager.check_and_resolve()
            if victim:
                self._log(f"[DEADLOCK] Cycle detected -> rolled back victim {victim}")
            time.sleep(0.1)

    def _log(self, msg: str):
        with self._event_lock:
            self.event_log.append(msg)

    def get_event_log(self) -> List[str]:
        with self._event_lock:
            return list(self.event_log)

    # ---- running a transaction ---------------------------------------------------
    def run_transaction(self, txn: Transaction, hold_seconds: float = 0.0,
                         should_commit: bool = True):
        """
        Executes one booking transaction (browse -> lock -> pay -> commit),
        intended to be called inside its own thread. This is the
        "critical section" where a real system would risk race conditions
        without proper locking.
        """
        with self._semaphore:
            self.txn_manager.mark_active(txn)
            self._log(f"[START] {txn.txn_id} ({txn.user}) requesting seats {txn.seat_ids}")

            show = self.cinema.get_show(txn.show_id)
            acquired_seats = []

            # Phase 1 (2PL growing phase): acquire S-Lock while "browsing"
            for seat_id in txn.seat_ids:
                txn.log_operation(OpType.READ, seat_id)
                got = self.lock_manager.acquire(txn.txn_id, seat_id, LockType.S)
                if not got:
                    self._log(f"[WAIT-TIMEOUT] {txn.txn_id} could not get S-lock on {seat_id}")
                    self._abort(txn)
                    return
                acquired_seats.append(seat_id)

            if hold_seconds > 0:
                self._log(f"[HOLD] {txn.txn_id} holding seats {txn.seat_ids} for {hold_seconds}s")
                time.sleep(hold_seconds)

            if not should_commit:
                # This transaction is scripted to just hold and then roll back
                # (used to demonstrate a clean, voluntary rollback).
                self._log(f"[ROLLBACK] {txn.txn_id} voluntarily rolling back")
                self._abort(txn)
                return

            # Phase 2: upgrade to X-Lock and write (confirm payment)
            for seat_id in txn.seat_ids:
                seat = show.get_seat(seat_id)
                if seat.state == SeatState.BOOKED:
                    self._log(f"[CONFLICT] {txn.txn_id} found {seat_id} already BOOKED -> abort")
                    self._abort(txn)
                    return

                got = self.lock_manager.acquire(txn.txn_id, seat_id, LockType.X)
                if not got:
                    self._log(f"[WAIT-TIMEOUT] {txn.txn_id} could not get X-lock on {seat_id}")
                    self._abort(txn)
                    return

                before = seat.state.value
                seat.state = SeatState.LOCKED
                seat.locked_by = txn.txn_id
                self.recovery_manager.log_write(txn.txn_id, seat_id, before, SeatState.BOOKED.value)
                txn.log_operation(OpType.WRITE, seat_id)

            # Phase 3 (2PL shrinking phase): commit - make it durable, release all locks
            for seat_id in txn.seat_ids:
                seat = show.get_seat(seat_id)
                seat.state = SeatState.BOOKED
                seat.booked_by = txn.user
                seat.locked_by = None

            self.recovery_manager.log_commit(txn.txn_id)
            self.lock_manager.release_all(txn.txn_id)
            self.txn_manager.mark_committed(txn)
            self._log(f"[COMMIT] {txn.txn_id} ({txn.user}) booked seats {txn.seat_ids}")

    def _abort(self, txn: Transaction):
        show = self.cinema.get_show(txn.show_id)
        for seat_id in self.lock_manager.locks_held_by(txn.txn_id):
            seat = show.get_seat(seat_id)
            if seat.locked_by == txn.txn_id:
                seat.state = SeatState.AVAILABLE
                seat.locked_by = None
        self.recovery_manager.log_rollback(txn.txn_id)
        self.lock_manager.release_all(txn.txn_id)
        self.txn_manager.mark_aborted(txn)

    def run_all_threaded(self, transactions: List[Transaction], hold_map: dict = None,
                          commit_map: dict = None):
        """
        Launches one thread per transaction (this is what makes the
        concurrency real rather than simulated in sequence), then waits
        for all of them to finish.
        """
        hold_map = hold_map or {}
        commit_map = commit_map or {}
        threads = []
        for txn in transactions:
            t = threading.Thread(
                target=self.run_transaction,
                args=(txn, hold_map.get(txn.txn_id, 0.0), commit_map.get(txn.txn_id, True)),
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
