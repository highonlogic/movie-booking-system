# CoreLock: Simulating Transaction Scheduling and Concurrency Control

**Team:** TriCoders | **Project Code:** OSDBMS-V-2026-T235
**Real-life application:** Movie Ticket Booking System

A combined OS + DBMS college project. Booking a movie seat is modeled as
a database transaction; multiple users booking at once are simulated
with real Python threads; an OS-style scheduler decides request order;
a lock manager (Strict 2PL, S/X locks) prevents double-booking; a
deadlock manager detects and resolves circular waits; and a recovery
manager demonstrates crash recovery via UNDO/REDO on a write-ahead log.

See `PROJECT_CONTEXT.md` for the full design writeup (architecture,
modules, tech stack, challenges, assumptions).

## Run the console demo

```bash
python -m corelock.main
```

This runs five scripted scenarios: a normal booking, a voluntary
rollback, a conflict-abort, a real thread-level deadlock (with
detection + rollback), and a crash + recovery cycle — printing the
seat grid, event log, and transaction summary at each stage.

## Run the live dashboard

```bash
pip install -r requirements.txt
streamlit run corelock/dashboard/app.py
```

Lets you submit booking requests interactively, pick the scheduling
algorithm, trigger a simulated crash, and run recovery — all watching
the same seat map, lock table, and deadlock log update live.

## Project structure

```
corelock/
├── seat_inventory.py      # Screens -> Shows -> Seats data model
├── transaction_manager.py  # Module 1: transaction lifecycle
├── scheduler.py             # Module 2: FCFS/SJF/RR/Priority scheduling
├── execution_engine.py      # Module 3: threaded concurrent execution
├── lock_manager.py          # Module 4: S/X locks, Strict 2PL
├── deadlock_manager.py       # Module 5: wait-for graph, victim selection
├── recovery_manager.py       # Module 6: WAL, checkpoints, UNDO/REDO
├── dashboard/app.py           # Module 7: Streamlit monitoring dashboard
├── logs/                       # transaction_log.jsonl written here at runtime
└── main.py                      # console demo orchestration
```
