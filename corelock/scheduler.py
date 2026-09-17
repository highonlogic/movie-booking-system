"""
scheduler.py
-------------
Module 2: OS Scheduler

Decides the ORDER in which incoming booking requests (transactions) are
handed to the Concurrent Execution Engine, simulating an OS process
scheduler deciding which "process" (booking request) runs next.

Supported algorithms:
    FCFS      - First Come First Served (by created_at timestamp)
    SJF        - Shortest Job First (fewest seats requested = "shorter job")
    RR         - Round Robin (fixed time-slice turns, cycles through queue)
    PRIORITY   - lower txn.priority value = served first (e.g. premium members)

This module does not touch locks or seats directly - it only decides
scheduling order. The actual work happens in execution_engine.py.
"""

from enum import Enum
from collections import deque
from typing import List
from .transaction_manager import Transaction


class Algorithm(Enum):
    FCFS = "FCFS"
    SJF = "SJF"
    ROUND_ROBIN = "ROUND_ROBIN"
    PRIORITY = "PRIORITY"


class Scheduler:
    def __init__(self, algorithm: Algorithm = Algorithm.FCFS, time_quantum: int = 1):
        self.algorithm = algorithm
        self.time_quantum = time_quantum  # used only by Round Robin (num seats processed per turn)
        self.ready_queue: deque[Transaction] = deque()
        self.waiting_queue: List[Transaction] = []  # txns waiting on a lock, tracked for the dashboard
        self.execution_order: List[str] = []  # txn_ids in the order they were scheduled, for the Gantt chart

    def add(self, txn: Transaction):
        self.ready_queue.append(txn)

    def _sorted_snapshot(self) -> List[Transaction]:
        """Returns the ready queue reordered per the active algorithm, WITHOUT mutating it."""
        items = list(self.ready_queue)
        if self.algorithm == Algorithm.FCFS:
            return sorted(items, key=lambda t: t.created_at)
        if self.algorithm == Algorithm.SJF:
            return sorted(items, key=lambda t: (len(t.seat_ids), t.created_at))
        if self.algorithm == Algorithm.PRIORITY:
            return sorted(items, key=lambda t: (t.priority, t.created_at))
        if self.algorithm == Algorithm.ROUND_ROBIN:
            return items  # RR keeps arrival order; fairness comes from time-slicing in the engine
        return items

    def next_batch(self, n: int = 1) -> List[Transaction]:
        """
        Pop up to `n` transactions in scheduling order. This is what the
        Execution Engine calls to get the next transaction(s) to run.
        """
        ordered = self._sorted_snapshot()
        batch = ordered[:n]
        for txn in batch:
            self.ready_queue.remove(txn)
            self.execution_order.append(txn.txn_id)
        return batch

    def has_pending(self) -> bool:
        return len(self.ready_queue) > 0

    def gantt_snapshot(self) -> List[str]:
        return list(self.execution_order)
