"""Module 2 — OS Scheduler (stub).

Will order booking requests: FCFS, SJF, Round Robin, Priority.
"""


class Scheduler:
    def __init__(self, algorithm: str = "FCFS") -> None:
        self.algorithm = algorithm
        self.ready_queue: list = []
        self.waiting_queue: list = []

    def enqueue(self, txn) -> None:
        raise NotImplementedError("Module 2: OS Scheduler not implemented yet")

    def next_transaction(self):
        raise NotImplementedError("Module 2: OS Scheduler not implemented yet")
