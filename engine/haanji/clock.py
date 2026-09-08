"""Simulated time.

The demo and the benchmark run against mock providers. Those providers sleep
for the *nominal* latency a real provider would take, divided by a scale
factor, so a hundred calls can be replayed in under a minute. Every duration
the engine reports is multiplied back by the same factor, so the numbers in
the results are always nominal milliseconds and never depend on how fast the
harness was told to run.
"""
from __future__ import annotations
import asyncio
import os
import time


class Clock:
    def __init__(self, speed: float | None = None):
        self.speed = float(os.environ.get("HAANJI_TIME_SCALE", 1.0)) if speed is None else speed
        if self.speed <= 0:
            raise ValueError("time scale must be positive")

    async def sleep_ms(self, ms: float) -> None:
        if ms > 0:
            await asyncio.sleep(ms / 1000.0 / self.speed)

    def nominal(self, measured_ms: float) -> float:
        """Convert a wall-clock measurement back to nominal milliseconds."""
        return measured_ms * self.speed

    @staticmethod
    def now_ms() -> float:
        return time.perf_counter() * 1000


CLOCK = Clock()


def set_speed(speed: float) -> None:
    CLOCK.speed = float(speed)
