"""
deadlock_manager.py
---------------------
Module 5: Deadlock Manager

Builds a wait-for graph from the Lock Manager's current wait-for edges
(txn_id -> txn_id it is blocked on) and detects cycles using DFS.

If a cycle is found, a victim is chosen (minimum-impact heuristic: the
transaction that has done the least work / touched the fewest seats is
rolled back, since restarting it wastes the least effort). The victim's
locks are released via the Lock Manager and its transaction is marked
ABORTED by the Transaction Manager - this is the "rollback" path in the
architecture diagram.

Demo mapping: Bob holds a lock while deciding, Charlie is waiting on a
seat Bob holds while Bob is (indirectly) waiting on something Charlie
holds -> cycle -> Deadlock Manager picks the lower-priority/newer txn as
the victim and rolls it back.
"""

from typing import Dict, List, Optional


class DeadlockManager:
    def __init__(self, lock_manager, transaction_manager):
        self.lock_manager = lock_manager
        self.transaction_manager = transaction_manager
        self.detected_cycles_log: List[List[str]] = []

    def _find_cycle(self, graph: Dict[str, str]) -> Optional[List[str]]:
        """
        Each node has at most one outgoing edge (a txn waits for exactly one
        lock holder at a time in this simulation), so a cycle detection is
        just: walk the chain from each node and see if we return to start.
        """
        for start in graph:
            visited = [start]
            current = graph.get(start)
            while current is not None:
                if current == start:
                    return visited + [current]
                if current in visited:
                    break  # cycle exists but doesn't include `start`
                visited.append(current)
                current = graph.get(current)
        return None

    def check_and_resolve(self) -> Optional[str]:
        """
        Call this periodically (e.g. from the Execution Engine's monitor
        loop). Returns the txn_id of the victim if a deadlock was resolved,
        else None.
        """
        graph = self.lock_manager.current_wait_for_graph()
        cycle = self._find_cycle(graph)
        if not cycle:
            return None

        self.detected_cycles_log.append(cycle)

        # victim selection: among txns in the cycle, pick the one with the
        # fewest completed operations (least work done = cheapest to redo)
        candidates = [
            self.transaction_manager.get(tid) for tid in set(cycle) if self.transaction_manager.get(tid)
        ]
        candidates = [c for c in candidates if c is not None]
        if not candidates:
            return None

        victim = min(candidates, key=lambda t: len(t.operations))

        # roll back the victim: release its locks, mark aborted
        self.lock_manager.release_all(victim.txn_id)
        self.transaction_manager.mark_aborted(victim)

        return victim.txn_id

    def cycle_history(self) -> List[List[str]]:
        return list(self.detected_cycles_log)
