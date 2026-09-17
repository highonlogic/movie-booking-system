"""
seat_inventory.py
------------------
Data model for CoreLock's real-life application: a Movie Ticket Booking System.

Hierarchy: Screen -> Show -> Seat grid

Each Seat has a state machine:
    AVAILABLE -> LOCKED (S-Lock, user browsing/selecting)
    LOCKED    -> BOOKED (X-Lock, payment confirmed / COMMIT)
    LOCKED    -> AVAILABLE (lock released / ROLLBACK)
    BOOKED    -> AVAILABLE (only via recovery UNDO, e.g. after a simulated crash)

This module has NO threading logic of its own - it is the "database table"
that everything else (Lock Manager, Transaction Manager, Recovery Manager)
reads and writes.
"""

import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List


class SeatState(Enum):
    AVAILABLE = "AVAILABLE"
    LOCKED = "LOCKED"
    BOOKED = "BOOKED"


@dataclass
class Seat:
    seat_id: str          # e.g. "A1", "B7"
    state: SeatState = SeatState.AVAILABLE
    locked_by: str = None      # transaction id currently holding a lock
    booked_by: str = None      # user who has confirmed this booking

    def snapshot(self) -> dict:
        return {
            "seat_id": self.seat_id,
            "state": self.state.value,
            "locked_by": self.locked_by,
            "booked_by": self.booked_by,
        }


class Show:
    """A single showtime on a screen, with its own seat grid."""

    def __init__(self, show_id: str, movie: str, time: str, rows: int = 5, cols: int = 6):
        self.show_id = show_id
        self.movie = movie
        self.time = time
        self.rows = rows
        self.cols = cols
        self._lock = threading.Lock()  # protects the seats dict itself (structural safety net)
        self.seats: Dict[str, Seat] = {}
        for r in range(rows):
            row_letter = chr(ord("A") + r)
            for c in range(1, cols + 1):
                seat_id = f"{row_letter}{c}"
                self.seats[seat_id] = Seat(seat_id=seat_id)

    def get_seat(self, seat_id: str) -> Seat:
        with self._lock:
            return self.seats.get(seat_id)

    def seat_grid_snapshot(self) -> List[dict]:
        with self._lock:
            return [s.snapshot() for s in self.seats.values()]


class Screen:
    """A physical screen that can host multiple shows (different times)."""

    def __init__(self, screen_id: str):
        self.screen_id = screen_id
        self.shows: Dict[str, Show] = {}

    def add_show(self, show: Show):
        self.shows[show.show_id] = show

    def get_show(self, show_id: str) -> Show:
        return self.shows.get(show_id)


class Cinema:
    """Top-level container: a set of screens. This is CoreLock's whole 'database'."""

    def __init__(self):
        self.screens: Dict[str, Screen] = {}

    def add_screen(self, screen: Screen):
        self.screens[screen.screen_id] = screen

    def get_show(self, show_id: str) -> Show:
        for screen in self.screens.values():
            show = screen.get_show(show_id)
            if show:
                return show
        return None

    @classmethod
    def seed_demo_data(cls) -> "Cinema":
        """Creates one screen with one show, used by main.py's demo."""
        cinema = cls()
        screen = Screen("Screen-1")
        show = Show(show_id="S101", movie="Inception", time="7:00 PM", rows=5, cols=6)
        screen.add_show(show)
        cinema.add_screen(screen)
        return cinema
