"""
transaction_manager.py
------------------------
Module 1: Transaction Manager

Responsible for creating and tracking the lifecycle of every booking
transaction. In the movie-booking mapping, a "transaction" is a single
user's attempt to book one or more seats for a show.

States: CREATED -> ACTIVE -> (READ/WRITE)* -> COMMITTED
                                            -> ABORTED (rollback)

Each transaction also records timestamps so the Monitoring & Analytics
dashboard (Module 7) can compute waiting time / turnaround time.
"""

import itertools
import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class TxnState(Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


class OpType(Enum):
    READ = "READ"        # browsing a seat (acquire S-Lock)
    WRITE = "WRITE"       # confirming a seat (acquire X-Lock)
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"


@dataclass
class Operation:
    op_type: OpType
    seat_id: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Transaction:
    txn_id: str
    user: str
    show_id: str
    seat_ids: List[str]
    priority: int = 5          # lower number = higher priority (used by Priority scheduler)
    state: TxnState = TxnState.CREATED
    operations: List[Operation] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    read_set: set = field(default_factory=set)
    write_set: set = field(default_factory=set)

    def log_operation(self, op_type: OpType, seat_id: str = None):
        self.operations.append(Operation(op_type, seat_id))
        if op_type == OpType.READ and seat_id:
            self.read_set.add(seat_id)
        elif op_type == OpType.WRITE and seat_id:
            self.write_set.add(seat_id)

    @property
    def waiting_time(self) -> float:
        if self.started_at is None:
            return 0.0
        return self.started_at - self.created_at

    @property
    def turnaround_time(self) -> float:
        if self.finished_at is None:
            return 0.0
        return self.finished_at - self.created_at

    def snapshot(self) -> dict:
        return {
            "txn_id": self.txn_id,
            "user": self.user,
            "show_id": self.show_id,
            "seat_ids": self.seat_ids,
            "priority": self.priority,
            "state": self.state.value,
            "waiting_time": round(self.waiting_time, 3),
            "turnaround_time": round(self.turnaround_time, 3),
            "num_ops": len(self.operations),
        }


class TransactionManager:
    """Creates transactions and tracks all of them for the dashboard."""

    _id_counter = itertools.count(1)

    def __init__(self):
        self._lock = threading.Lock()
        self.transactions: dict[str, Transaction] = {}

    def create_transaction(self, user: str, show_id: str, seat_ids: List[str],
                            priority: int = 5) -> Transaction:
        txn_id = f"T{next(self._id_counter)}"
        txn = Transaction(txn_id=txn_id, user=user, show_id=show_id,
                           seat_ids=seat_ids, priority=priority)
        with self._lock:
            self.transactions[txn_id] = txn
        return txn

    def mark_active(self, txn: Transaction):
        txn.started_at = txn.started_at or time.time()
        txn.state = TxnState.ACTIVE

    def mark_waiting(self, txn: Transaction):
        txn.state = TxnState.WAITING

    def mark_committed(self, txn: Transaction):
        txn.log_operation(OpType.COMMIT)
        txn.state = TxnState.COMMITTED
        txn.finished_at = time.time()

    def mark_aborted(self, txn: Transaction):
        txn.log_operation(OpType.ROLLBACK)
        txn.state = TxnState.ABORTED
        txn.finished_at = time.time()

    def all_snapshots(self) -> List[dict]:
        with self._lock:
            return [t.snapshot() for t in self.transactions.values()]

    def get(self, txn_id: str) -> Optional[Transaction]:
        return self.transactions.get(txn_id)
