from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Self


@dataclass(slots=True)
class Timer:
    _start: float = field(default=0.0, repr=False)
    _end: float = field(default=0.0, repr=False)

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed(self) -> float:
        end = self._end or time.perf_counter()  # still running if _end is 0
        return end - self._start
