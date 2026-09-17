"""Module 4 — Lock & Concurrency Manager (stub).

S-Lock / X-Lock on seats, lock table, 2PL / Strict 2PL, compatibility matrix.
"""


class LockManager:
    def acquire_shared(self, txn_id: str, resource_id: str) -> None:
        raise NotImplementedError("Module 4: Lock Manager not implemented yet")

    def acquire_exclusive(self, txn_id: str, resource_id: str) -> None:
        raise NotImplementedError("Module 4: Lock Manager not implemented yet")

    def release_all(self, txn_id: str) -> None:
        raise NotImplementedError("Module 4: Lock Manager not implemented yet")
