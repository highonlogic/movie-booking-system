"""Module 6 — Recovery Manager (stub).

Write-ahead logs, checkpoints, UNDO/REDO, crash simulation.
"""


class RecoveryManager:
    def log(self, record) -> None:
        raise NotImplementedError("Module 6: Recovery Manager not implemented yet")

    def checkpoint(self) -> None:
        raise NotImplementedError("Module 6: Recovery Manager not implemented yet")

    def recover(self) -> None:
        raise NotImplementedError("Module 6: Recovery Manager not implemented yet")
