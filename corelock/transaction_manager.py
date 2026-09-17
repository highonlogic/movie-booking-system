"""Module 1 — Transaction Manager.

A transaction is: User X books Seat [Row-Col] for Show [Movie, Time, Screen].

Lifecycle (DBMS states):
  NEW → ACTIVE → PARTIALLY_COMMITTED → COMMITTED
                 ↘ FAILED → ABORTED (ROLLBACK)

Operations:
  BEGIN, READ (browse / hold seat in cart), WRITE (confirm payment intent),
  COMMIT, ROLLBACK.

Seat transitions here (Lock Manager will own S/X locks later):
  READ   : Available → Locked  (held in cart)
  WRITE  : record write-set; seat stays Locked until commit
  COMMIT : Locked → Booked
  ROLLBACK: restore previous seat state (UNDO)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from corelock.seat_inventory import SeatInventory, SeatPos, SeatState


class TransactionState(Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    PARTIALLY_COMMITTED = "PARTIALLY_COMMITTED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class OperationType(Enum):
    BEGIN = "BEGIN"
    READ = "READ"
    WRITE = "WRITE"
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"


TERMINAL_STATES = {TransactionState.COMMITTED, TransactionState.ABORTED}


@dataclass
class Operation:
    op_type: OperationType
    timestamp: float
    show_id: Optional[str] = None
    seat: Optional[SeatPos] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "op": self.op_type.value,
            "timestamp": self.timestamp,
            "show_id": self.show_id,
            "seat": self.seat,
            "detail": self.detail,
        }


@dataclass
class UndoRecord:
    """Before-image used by ROLLBACK (and later by Recovery Manager UNDO)."""

    show_id: str
    seat: SeatPos
    prev_state: SeatState
    prev_held_by: Optional[str]


@dataclass
class BookingRequest:
    """Incoming booking: what the user wants, before/while it is a transaction."""

    user_id: str
    show_id: str
    seats: List[SeatPos]
    priority: int = 0  # higher = premium / member (OS Priority scheduler)
    burst_time: float = 1.0  # estimated work units (SJF)

    def describe(self) -> str:
        labels = [f"({r},{c})" for r, c in self.seats]
        return f"User {self.user_id} books seats {', '.join(labels)} on show {self.show_id}"


@dataclass
class Transaction:
    txn_id: str
    request: BookingRequest
    state: TransactionState = TransactionState.NEW
    operations: List[Operation] = field(default_factory=list)
    read_set: Set[SeatPos] = field(default_factory=set)
    write_set: Set[SeatPos] = field(default_factory=set)
    undo_log: List[UndoRecord] = field(default_factory=list)
    arrival_time: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    completion_time: Optional[float] = None
    error: Optional[str] = None

    def log_op(self, op_type: OperationType, show_id: Optional[str] = None,
               seat: Optional[SeatPos] = None, detail: str = "") -> None:
        self.operations.append(
            Operation(
                op_type=op_type,
                timestamp=time.time(),
                show_id=show_id,
                seat=seat,
                detail=detail,
            )
        )

    def waiting_time(self) -> Optional[float]:
        if self.start_time is None:
            return None
        return self.start_time - self.arrival_time

    def turnaround_time(self) -> Optional[float]:
        if self.completion_time is None:
            return None
        return self.completion_time - self.arrival_time

    def to_dict(self) -> dict:
        return {
            "txn_id": self.txn_id,
            "user_id": self.request.user_id,
            "show_id": self.request.show_id,
            "seats": list(self.request.seats),
            "priority": self.request.priority,
            "state": self.state.value,
            "read_set": list(self.read_set),
            "write_set": list(self.write_set),
            "operations": [op.to_dict() for op in self.operations],
            "arrival_time": self.arrival_time,
            "start_time": self.start_time,
            "completion_time": self.completion_time,
            "waiting_time": self.waiting_time(),
            "turnaround_time": self.turnaround_time(),
            "error": self.error,
        }


class TransactionError(Exception):
    pass


class TransactionManager:
    """Creates booking requests and drives READ / WRITE / COMMIT / ROLLBACK."""

    def __init__(self, inventory: SeatInventory) -> None:
        self.inventory = inventory
        self._transactions: Dict[str, Transaction] = {}
        self._lock = threading.RLock()

    # ----- factory -----

    def create_transaction(
        self,
        user_id: str,
        show_id: str,
        seats: List[SeatPos],
        priority: int = 0,
        burst_time: float = 1.0,
        txn_id: Optional[str] = None,
    ) -> Transaction:
        if not seats:
            raise TransactionError("A booking request must include at least one seat")
        self.inventory.get_show(show_id)  # validate show exists
        request = BookingRequest(
            user_id=user_id,
            show_id=show_id,
            seats=list(seats),
            priority=priority,
            burst_time=burst_time,
        )
        txn = Transaction(
            txn_id=txn_id or f"T-{uuid.uuid4().hex[:8]}",
            request=request,
        )
        with self._lock:
            self._transactions[txn.txn_id] = txn
        return txn

    def get(self, txn_id: str) -> Transaction:
        with self._lock:
            if txn_id not in self._transactions:
                raise TransactionError(f"Unknown transaction '{txn_id}'")
            return self._transactions[txn_id]

    def all_transactions(self) -> List[Transaction]:
        with self._lock:
            return list(self._transactions.values())

    def active_transactions(self) -> List[Transaction]:
        return [t for t in self.all_transactions() if t.state == TransactionState.ACTIVE]

    # ----- lifecycle -----

    def begin(self, txn_id: str) -> Transaction:
        with self._lock:
            txn = self.get(txn_id)
            self._require_state(txn, TransactionState.NEW, "BEGIN")
            txn.state = TransactionState.ACTIVE
            txn.start_time = time.time()
            txn.log_op(OperationType.BEGIN, detail=txn.request.describe())
            return txn

    def read(self, txn_id: str, seat: Optional[SeatPos] = None) -> SeatState:
        """READ: browse / hold a seat in cart (Available → Locked).

        If `seat` is omitted, READ is applied to every seat in the booking request.
        Returns the last seat's observed state after the hold.
        """
        with self._lock:
            txn = self.get(txn_id)
            self._require_state(txn, TransactionState.ACTIVE, "READ")
            seats = [seat] if seat is not None else list(txn.request.seats)
            last_state = SeatState.AVAILABLE
            for pos in seats:
                last_state = self._read_one(txn, pos)
            return last_state

    def write(self, txn_id: str, seat: Optional[SeatPos] = None) -> None:
        """WRITE: payment confirmation intent. Seat stays Locked until COMMIT."""
        with self._lock:
            txn = self.get(txn_id)
            self._require_state(txn, TransactionState.ACTIVE, "WRITE")
            seats = [seat] if seat is not None else list(txn.request.seats)
            for pos in seats:
                self._write_one(txn, pos)

    def commit(self, txn_id: str) -> Transaction:
        """COMMIT: durable booking — Locked → Booked for the write-set."""
        with self._lock:
            txn = self.get(txn_id)
            self._require_state(txn, TransactionState.ACTIVE, "COMMIT")
            if not txn.write_set:
                self._fail(txn, "COMMIT without WRITE — nothing to make durable")
            txn.state = TransactionState.PARTIALLY_COMMITTED
            show = self.inventory.get_show(txn.request.show_id)
            for pos in txn.write_set:
                seat = show.get_seat(*pos)
                if seat.held_by not in (txn.txn_id, None) and seat.state != SeatState.AVAILABLE:
                    self._fail(txn, f"Seat {pos} is held by {seat.held_by}")
                if seat.state == SeatState.BOOKED and seat.held_by != txn.txn_id:
                    self._fail(txn, f"Seat {pos} is already booked")
                self._record_undo(txn, txn.request.show_id, pos, seat.state, seat.held_by)
                seat.state = SeatState.BOOKED
                seat.held_by = txn.txn_id
            txn.state = TransactionState.COMMITTED
            txn.completion_time = time.time()
            txn.log_op(OperationType.COMMIT, show_id=txn.request.show_id, detail="booking confirmed")
            return txn

    def rollback(self, txn_id: str, reason: str = "explicit ROLLBACK") -> Transaction:
        """ROLLBACK: UNDO seat updates from the before-image log."""
        with self._lock:
            txn = self.get(txn_id)
            if txn.state in TERMINAL_STATES:
                raise TransactionError(f"Cannot ROLLBACK {txn.txn_id} from {txn.state.value}")
            self._apply_undo(txn)
            txn.state = TransactionState.ABORTED
            txn.completion_time = time.time()
            txn.error = reason
            txn.log_op(OperationType.ROLLBACK, show_id=txn.request.show_id, detail=reason)
            return txn

    def fail_and_rollback(self, txn_id: str, reason: str) -> Transaction:
        with self._lock:
            txn = self.get(txn_id)
            if txn.state not in TERMINAL_STATES:
                txn.state = TransactionState.FAILED
            return self.rollback(txn_id, reason=reason)

    # ----- internals -----

    def _read_one(self, txn: Transaction, pos: SeatPos) -> SeatState:
        show = self.inventory.get_show(txn.request.show_id)
        seat = show.get_seat(*pos)
        observed = seat.state
        if observed == SeatState.BOOKED and seat.held_by != txn.txn_id:
            self._fail(txn, f"Seat {pos} is already booked")
        if observed == SeatState.LOCKED and seat.held_by not in (None, txn.txn_id):
            self._fail(txn, f"Seat {pos} is held in another user's cart ({seat.held_by})")
        if observed == SeatState.AVAILABLE:
            self._record_undo(txn, txn.request.show_id, pos, seat.state, seat.held_by)
            seat.state = SeatState.LOCKED
            seat.held_by = txn.txn_id
        txn.read_set.add(pos)
        txn.log_op(
            OperationType.READ,
            show_id=txn.request.show_id,
            seat=pos,
            detail=f"observed {observed.value}; held as Locked",
        )
        return seat.state

    def _write_one(self, txn: Transaction, pos: SeatPos) -> None:
        show = self.inventory.get_show(txn.request.show_id)
        seat = show.get_seat(*pos)
        if pos not in txn.read_set:
            # WRITE without prior READ still needs a hold (strict-ish 2PL later).
            self._read_one(txn, pos)
            seat = show.get_seat(*pos)
        if seat.held_by != txn.txn_id:
            self._fail(txn, f"WRITE on seat {pos} without holding it")
        txn.write_set.add(pos)
        txn.log_op(
            OperationType.WRITE,
            show_id=txn.request.show_id,
            seat=pos,
            detail="payment intent recorded",
        )

    def _record_undo(
        self,
        txn: Transaction,
        show_id: str,
        pos: SeatPos,
        prev_state: SeatState,
        prev_held_by: Optional[str],
    ) -> None:
        for rec in txn.undo_log:
            if rec.show_id == show_id and rec.seat == pos:
                return  # keep original before-image
        txn.undo_log.append(
            UndoRecord(
                show_id=show_id,
                seat=pos,
                prev_state=prev_state,
                prev_held_by=prev_held_by,
            )
        )

    def _apply_undo(self, txn: Transaction) -> None:
        for rec in reversed(txn.undo_log):
            seat = self.inventory.get_show(rec.show_id).get_seat(*rec.seat)
            if seat.held_by in (txn.txn_id, rec.prev_held_by, None):
                seat.state = rec.prev_state
                seat.held_by = rec.prev_held_by

    def _require_state(self, txn: Transaction, expected: TransactionState, op: str) -> None:
        if txn.state != expected:
            raise TransactionError(
                f"{op} not allowed on {txn.txn_id} in state {txn.state.value} (need {expected.value})"
            )

    def _fail(self, txn: Transaction, reason: str) -> None:
        txn.state = TransactionState.FAILED
        txn.error = reason
        self._apply_undo(txn)
        txn.state = TransactionState.ABORTED
        txn.completion_time = time.time()
        txn.log_op(OperationType.ROLLBACK, show_id=txn.request.show_id, detail=reason)
        raise TransactionError(reason)
