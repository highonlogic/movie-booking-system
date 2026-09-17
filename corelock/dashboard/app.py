"""
dashboard/app.py
------------------
Module 7: Monitoring & Analytics Dashboard (Streamlit)

Run with:
    streamlit run corelock/dashboard/app.py

Live view of:
  - Seat map (color-coded: available / locked / booked)
  - Transaction table (state, waiting time, turnaround time)
  - Lock table (who holds what)
  - Deadlock history
  - "Simulate Crash" + "Recover" buttons for the recovery demo
  - Scheduler's execution order (Gantt-style list)

This dashboard builds its OWN engine instance in Streamlit's session_state
so it survives reruns (Streamlit reruns the whole script on every
interaction), and exposes buttons that trigger new booking transactions,
a crash, and recovery - all backed by the real corelock modules, not
mocked data.
"""

import sys
import os
import time

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from corelock.seat_inventory import Cinema
from corelock.transaction_manager import TransactionManager
from corelock.lock_manager import LockManager
from corelock.scheduler import Scheduler, Algorithm
from corelock.execution_engine import ExecutionEngine
from corelock.recovery_manager import RecoveryManager

SHOW_ID = "S101"

st.set_page_config(page_title="CoreLock Dashboard", layout="wide")


def init_state():
    if "engine" in st.session_state:
        return
    cinema = Cinema.seed_demo_data()
    txn_manager = TransactionManager()
    lock_manager = LockManager(wait_timeout=1.5)
    scheduler = Scheduler(algorithm=Algorithm.PRIORITY)
    recovery_manager = RecoveryManager()
    engine = ExecutionEngine(cinema, txn_manager, lock_manager, scheduler,
                              recovery_manager, max_concurrent=4)
    engine.start_monitor()

    st.session_state.cinema = cinema
    st.session_state.txn_manager = txn_manager
    st.session_state.lock_manager = lock_manager
    st.session_state.scheduler = scheduler
    st.session_state.recovery_manager = recovery_manager
    st.session_state.engine = engine
    st.session_state.recovery_report = None


init_state()

cinema = st.session_state.cinema
txn_manager = st.session_state.txn_manager
lock_manager = st.session_state.lock_manager
scheduler = st.session_state.scheduler
recovery_manager = st.session_state.recovery_manager
engine = st.session_state.engine

st.title("CoreLock: Movie Ticket Booking Concurrency Simulator")
st.caption("OS Scheduling + DBMS Concurrency Control, demoed on a seat-booking system")

# ------------------------------------------------------------------ Controls
st.subheader("Book seats")
col1, col2, col3, col4 = st.columns(4)
with col1:
    user = st.text_input("User name", value="Guest1")
with col2:
    seats_input = st.text_input("Seat(s), comma-separated", value="A1")
with col3:
    priority = st.number_input("Priority (lower = higher)", min_value=1, max_value=10, value=5)
with col4:
    algo_name = st.selectbox("Scheduler algorithm", [a.value for a in Algorithm])
    scheduler.algorithm = Algorithm(algo_name)

if st.button("Submit booking request"):
    seat_ids = [s.strip().upper() for s in seats_input.split(",") if s.strip()]
    txn = txn_manager.create_transaction(user, SHOW_ID, seat_ids, priority=priority)
    scheduler.add(txn)
    batch = scheduler.next_batch(1)
    engine.run_all_threaded(batch)
    st.rerun()

st.divider()

# ------------------------------------------------------------------ Crash / Recovery demo
st.subheader("Crash & Recovery demo")
c1, c2, c3 = st.columns(3)
with c1:
    crash_seat = st.text_input("Seat to crash (dirty write)", value="B1")
with c2:
    if st.button("💥 Simulate Crash"):
        recovery_manager.simulate_crash(cinema, crash_seat.strip().upper(), SHOW_ID)
        st.rerun()
with c3:
    if st.button("🛠️ Recover"):
        st.session_state.recovery_report = recovery_manager.recover(cinema)
        st.rerun()

if st.session_state.recovery_report:
    st.success(f"Recovery report: {st.session_state.recovery_report}")

st.divider()

# ------------------------------------------------------------------ Seat map
st.subheader("Live seat map")
show = cinema.get_show(SHOW_ID)
color_map = {"AVAILABLE": "🟩", "LOCKED": "🟨", "BOOKED": "🟥"}
for r in range(show.rows):
    row_letter = chr(ord("A") + r)
    row_cols = st.columns(show.cols)
    for c in range(1, show.cols + 1):
        seat = show.get_seat(f"{row_letter}{c}")
        row_cols[c - 1].markdown(
            f"**{seat.seat_id}**<br>{color_map[seat.state.value]}", unsafe_allow_html=True
        )
st.caption("🟩 Available   🟨 Locked (in progress)   🟥 Booked")

st.divider()

# ------------------------------------------------------------------ Transactions table
left, right = st.columns(2)
with left:
    st.subheader("Transactions")
    snaps = txn_manager.all_snapshots()
    if snaps:
        st.dataframe(snaps, use_container_width=True)
    else:
        st.write("No transactions yet.")

    st.subheader("Scheduler execution order (Gantt)")
    st.write(" → ".join(scheduler.gantt_snapshot()) or "—")

with right:
    st.subheader("Lock table")
    st.json(lock_manager.lock_table_snapshot())

    st.subheader("Deadlock history")
    cycles = engine.deadlock_manager.cycle_history()
    if cycles:
        for cyc in cycles:
            st.write(" → ".join(cyc))
    else:
        st.write("No deadlocks detected yet.")

st.divider()
st.subheader("Event log")
st.text("\n".join(engine.get_event_log()[-30:]) or "—")

if st.button("🔄 Reset simulation"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
