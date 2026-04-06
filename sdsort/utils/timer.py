import time
from dataclasses import dataclass, field


@dataclass
class Timer:
    _start: float = field(default=0.0, repr=False)
    _end: float = field(default=0.0, repr=False)

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self._end = time.perf_counter()

    @property
    def elapsed(self) -> float:
        end = self._end or time.perf_counter()  # still running if _end is 0
        return end - self._start
