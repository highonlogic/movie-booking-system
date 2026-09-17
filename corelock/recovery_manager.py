"""
recovery_manager.py
----------------------
Module 6: Recovery Manager

Implements a simple Write-Ahead Log (WAL) + UNDO/REDO recovery scheme,
and the "Simulate Crash" / "Recover" demo feature.

Log entry format (one JSON object per line, in logs/transaction_log.jsonl):
    {"txn_id": "T3", "seat_id": "B2", "before": "AVAILABLE",
     "after": "BOOKED", "op": "WRITE", "committed": false, "ts": ...}

- Before a seat's state is changed, the OLD value is written to the log
  (the "before-image", used for UNDO).
- When a transaction commits, a COMMIT record is appended - only then is
  the change considered durable.
- If a crash is simulated mid-transaction (payment "done" but the seat
  status update never got flushed / committed), Recovery:
      UNDO  -> any WRITE with no matching COMMIT record is rolled back
               to its before-image.
      REDO  -> any WRITE that DOES have a COMMIT record, but whose
               in-memory seat state doesn't reflect it, is re-applied.
"""

import json
import os
import time
from typing import List, Dict
from .seat_inventory import Cinema, SeatState


class RecoveryManager:
    def __init__(self, log_path: str = None):
        self.log_path = log_path or os.path.join(
            os.path.dirname(__file__), "logs", "transaction_log.jsonl"
        )
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        # truncate log fresh each run so demo output is deterministic
        open(self.log_path, "w").close()
        self.checkpoints: List[dict] = []

    # ---- writing -------------------------------------------------------------
    def log_write(self, txn_id: str, seat_id: str, before: str, after: str):
        self._append({
            "txn_id": txn_id, "seat_id": seat_id, "op": "WRITE",
            "before": before, "after": after, "committed": False,
            "ts": time.time(),
        })

    def log_commit(self, txn_id: str):
        self._append({"txn_id": txn_id, "op": "COMMIT", "ts": time.time()})

    def log_rollback(self, txn_id: str):
        self._append({"txn_id": txn_id, "op": "ROLLBACK", "ts": time.time()})

    def checkpoint(self, cinema: Cinema):
        """Records a full snapshot; recovery can start scanning from here instead of the whole log."""
        snap = {"ts": time.time(), "note": "checkpoint"}
        self.checkpoints.append(snap)
        self._append({"op": "CHECKPOINT", "ts": snap["ts"]})

    def _append(self, record: dict):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def read_log(self) -> List[dict]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path) as f:
            return [json.loads(line) for line in f if line.strip()]

    # ---- crash + recovery ------------------------------------------------------
    def simulate_crash(self, cinema: Cinema, seat_id: str, show_id: str):
        """
        Simulates: payment for `seat_id` succeeded (we WROTE the new state)
        but the process died before COMMIT was logged. We force the
        in-memory seat back to its pre-crash (dirty, uncommitted) state so
        `recover()` has something real to fix.
        """
        show = cinema.get_show(show_id)
        seat = show.get_seat(seat_id)
        seat.state = SeatState.BOOKED  # the "dirty" write that never got committed
        seat.booked_by = "CRASH_DIRTY_WRITE"

    def recover(self, cinema: Cinema) -> Dict[str, list]:
        """
        Scans the WAL and applies UNDO for uncommitted writes, REDO for
        committed writes not yet reflected. Returns a report for the
        dashboard: {"undone": [...], "redone": [...]}.
        """
        log = self.read_log()
        committed_txns = {r["txn_id"] for r in log if r.get("op") == "COMMIT"}
        rolled_back_txns = {r["txn_id"] for r in log if r.get("op") == "ROLLBACK"}

        undone, redone = [], []

        for record in log:
            if record.get("op") != "WRITE":
                continue
            txn_id, seat_id = record["txn_id"], record["seat_id"]
            show = self._find_show_with_seat(cinema, seat_id)
            if show is None:
                continue
            seat = show.get_seat(seat_id)

            if txn_id in committed_txns:
                # REDO: make sure the committed change is actually reflected
                if seat.state.value != record["after"]:
                    seat.state = SeatState[record["after"]]
                    redone.append({"txn_id": txn_id, "seat_id": seat_id, "to": record["after"]})
            else:
                # UNDO: this write was never committed (crash or rollback) -> restore before-image
                if seat.state.value != record["before"]:
                    seat.state = SeatState[record["before"]]
                    seat.booked_by = None
                    seat.locked_by = None
                    undone.append({"txn_id": txn_id, "seat_id": seat_id, "to": record["before"]})

        return {"undone": undone, "redone": redone}

    def _find_show_with_seat(self, cinema: Cinema, seat_id: str):
        for screen in cinema.screens.values():
            for show in screen.shows.values():
                if seat_id in show.seats:
                    return show
        return None
