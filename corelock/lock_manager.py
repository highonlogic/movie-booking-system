"""
lock_manager.py
-----------------
Module 4: Lock & Concurrency Manager

Implements Strict Two-Phase Locking (Strict 2PL) with Shared (S) and
Exclusive (X) locks on individual seats.

Compatibility matrix:
            S-Lock      X-Lock
  S-Lock    Compatible  Conflict
  X-Lock    Conflict    Conflict

- A seat being "browsed" needs an S-Lock (multiple users can browse the
  same seat at once - that's normal, like two people looking at the same
  seat map).
- A seat being "confirmed for payment" needs an X-Lock, upgraded from the
  transaction's own S-Lock if it holds one. X-Locks are exclusive - only
  one transaction may hold it.
- Strict 2PL: all locks held by a transaction are released only at
  COMMIT or ROLLBACK (never before), which is what makes Strict 2PL
  "strict" and guarantees no dirty reads of an uncommitted seat.
"""

import threading
import time
from enum import Enum
from collections import defaultdict
from typing import Dict, Set


class LockType(Enum):
    S = "S"   # Shared
    X = "X"   # Exclusive


class LockManager:
    def __init__(self, wait_timeout: float = 2.0):
        self._lock = threading.RLock()
        # seat_id -> {"type": LockType, "holders": {txn_id, ...}}
        self._lock_table: Dict[str, dict] = {}
        # txn_id -> set of seat_ids it holds a lock on
        self._held_by_txn: Dict[str, Set[str]] = defaultdict(set)
        # for the deadlock manager: txn_id -> seat_id it is currently waiting for
        self.wait_for: Dict[str, str] = {}
        self.wait_timeout = wait_timeout

    # ---- compatibility check -------------------------------------------------
    def _compatible(self, seat_id: str, requested: LockType, txn_id: str) -> bool:
        entry = self._lock_table.get(seat_id)
        if entry is None:
            return True
        holders = entry["holders"]
        if holders == {txn_id}:
            return True  # only the requesting txn holds it -> can upgrade
        if requested == LockType.S and entry["type"] == LockType.S:
            return True  # S-S compatible
        return False  # anything involving X is a conflict with other holders

    def acquire(self, txn_id: str, seat_id: str, lock_type: LockType) -> bool:
        """
        Blocking acquire with timeout. Returns True if the lock was granted,
        False if it timed out waiting (caller should treat this as a signal
        to abort / retry - the Deadlock Manager decides what happens next).
        """
        start = time.time()
        while True:
            with self._lock:
                if self._compatible(seat_id, lock_type, txn_id):
                    entry = self._lock_table.setdefault(
                        seat_id, {"type": lock_type, "holders": set()}
                    )
                    # upgrade S -> X if this txn already held S alone
                    entry["type"] = lock_type if lock_type == LockType.X else entry["type"]
                    entry["holders"].add(txn_id)
                    self._held_by_txn[txn_id].add(seat_id)
                    self.wait_for.pop(txn_id, None)
                    return True
                else:
                    # record who we're waiting on, for wait-for-graph construction
                    # (exclude ourselves - we may already hold an S-lock on this
                    # seat while waiting to upgrade it to X, which is not a
                    # self-wait, it's a wait on the OTHER holder(s))
                    other_holders = [
                        h for h in self._lock_table[seat_id]["holders"] if h != txn_id
                    ]
                    if other_holders:
                        self.wait_for[txn_id] = other_holders[0]

            if time.time() - start > self.wait_timeout:
                with self._lock:
                    self.wait_for.pop(txn_id, None)
                return False
            time.sleep(0.05)

    def release_all(self, txn_id: str):
        """Strict 2PL: called only at COMMIT or ROLLBACK time."""
        with self._lock:
            seat_ids = self._held_by_txn.pop(txn_id, set())
            for seat_id in seat_ids:
                entry = self._lock_table.get(seat_id)
                if entry and txn_id in entry["holders"]:
                    entry["holders"].discard(txn_id)
                    if not entry["holders"]:
                        del self._lock_table[seat_id]
            self.wait_for.pop(txn_id, None)

    def locks_held_by(self, txn_id: str) -> Set[str]:
        with self._lock:
            return set(self._held_by_txn.get(txn_id, set()))

    def current_wait_for_graph(self) -> Dict[str, str]:
        with self._lock:
            return dict(self.wait_for)

    def lock_table_snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {
                seat_id: {"type": v["type"].value, "holders": list(v["holders"])}
                for seat_id, v in self._lock_table.items()
            }
