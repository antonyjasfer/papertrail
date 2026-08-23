from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class IClock(Protocol):
    """Protocol for time authority across lease, claim, outbox, and audit events."""

    def now_utc(self) -> datetime: ...


class ProductionClock:
    """Production wall clock using system UTC time."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class DeterministicTestClock:
    """Deterministic clock for unit, integration, and parity testing."""

    def __init__(self, fixed_time: Optional[datetime] = None) -> None:
        self._current_time = fixed_time or datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

    def set_time(self, new_time: datetime) -> None:
        self._current_time = new_time

    def advance(self, seconds: int) -> None:
        self._current_time += timedelta(seconds=seconds)

    def now_utc(self) -> datetime:
        return self._current_time
