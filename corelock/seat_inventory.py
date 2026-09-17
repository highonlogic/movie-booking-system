"""In-memory seat inventory: Screens → Shows → Seats.

Working data lives in Python dicts / 2D grids (no external DB).
Seat states: Available, Locked (held in cart), Booked (paid).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SeatState(Enum):
    AVAILABLE = "Available"
    LOCKED = "Locked"
    BOOKED = "Booked"


SeatPos = Tuple[int, int]  # (row, col) 0-indexed


@dataclass
class Seat:
    row: int
    col: int
    state: SeatState = SeatState.AVAILABLE
    held_by: Optional[str] = None  # transaction id holding a lock/booking

    @property
    def label(self) -> str:
        return f"{chr(ord('A') + self.row)}{self.col + 1}"

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "label": self.label,
            "state": self.state.value,
            "held_by": self.held_by,
        }


@dataclass
class Show:
    show_id: str
    movie: str
    start_time: str
    screen_id: str
    rows: int
    cols: int
    seats: List[List[Seat]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.seats:
            self.seats = [
                [Seat(r, c) for c in range(self.cols)] for r in range(self.rows)
            ]

    def get_seat(self, row: int, col: int) -> Seat:
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(f"Seat ({row}, {col}) is outside the {self.rows}x{self.cols} grid")
        return self.seats[row][col]

    def snapshot(self) -> List[List[str]]:
        return [[seat.state.value for seat in row] for row in self.seats]

    def counts(self) -> Dict[str, int]:
        tally = {s.value: 0 for s in SeatState}
        for row in self.seats:
            for seat in row:
                tally[seat.state.value] += 1
        return tally


@dataclass
class Screen:
    screen_id: str
    name: str
    rows: int = 10
    cols: int = 10


class SeatInventory:
    """Cinema inventory used by the Transaction Manager as the 'database'."""

    def __init__(self) -> None:
        self.screens: Dict[str, Screen] = {}
        self.shows: Dict[str, Show] = {}

    def add_screen(self, screen_id: str, name: str, rows: int = 10, cols: int = 10) -> Screen:
        screen = Screen(screen_id=screen_id, name=name, rows=rows, cols=cols)
        self.screens[screen_id] = screen
        return screen

    def add_show(
        self,
        show_id: str,
        movie: str,
        start_time: str,
        screen_id: str,
    ) -> Show:
        if screen_id not in self.screens:
            raise KeyError(f"Unknown screen '{screen_id}'")
        screen = self.screens[screen_id]
        show = Show(
            show_id=show_id,
            movie=movie,
            start_time=start_time,
            screen_id=screen_id,
            rows=screen.rows,
            cols=screen.cols,
        )
        self.shows[show_id] = show
        return show

    def get_show(self, show_id: str) -> Show:
        if show_id not in self.shows:
            raise KeyError(f"Unknown show '{show_id}'")
        return self.shows[show_id]

    def seed_demo_cinema(self) -> None:
        """One screen, one popular show, 10x10 grid — sized for a live demo."""
        self.add_screen("SCR-1", "Audi 1", rows=10, cols=10)
        self.add_show(
            show_id="SHOW-1",
            movie="CoreLock: The Premiere",
            start_time="19:00",
            screen_id="SCR-1",
        )
