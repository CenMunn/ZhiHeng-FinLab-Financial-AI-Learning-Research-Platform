from platform_app.contracts.models import CaseSnapshot


class CaseService:
    def __init__(self, snapshots: tuple[CaseSnapshot, ...]):
        self._snapshots = {item.snapshot_id:item for item in snapshots}
        if len(self._snapshots) != len(snapshots):
            raise ValueError("Duplicate snapshot IDs")

    def get(self, snapshot_id: str) -> CaseSnapshot:
        return self._snapshots[snapshot_id]

    def list(self) -> tuple[CaseSnapshot, ...]:
        return tuple(self._snapshots.values())
