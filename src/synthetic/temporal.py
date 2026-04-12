"""TemporalEngine — generate event arrival patterns (Poisson, bursty, cron-like)."""

import random
from datetime import datetime, timedelta


class TemporalEngine:
    """Generate realistic temporal event patterns."""

    WINDOW_MINUTES = 15
    PROJECT_START = datetime(2026, 1, 15, 0, 0, 0)  # Start of synthetic timeline

    def __init__(self, seed: int = 42):
        """Initialize temporal engine.

        Args:
            seed: Random seed
        """
        self.rng = random.Random(seed)
        self.current_time = self.PROJECT_START

    def get_windows(self, count: int) -> list[datetime]:
        """Get N window boundaries (15-min intervals from PROJECT_START)."""
        windows = []
        for i in range(count):
            window_start = self.PROJECT_START + timedelta(minutes=i * self.WINDOW_MINUTES)
            windows.append(window_start)
        return windows

    def poisson_arrivals(
        self,
        window_start: datetime,
        window_end: datetime,
        lambda_rate: float,
    ) -> list[datetime]:
        """Generate Poisson-distributed event times in a window.

        Args:
            window_start: Start of time window (ISO datetime)
            window_end: End of time window (ISO datetime)
            lambda_rate: Mean arrival rate (events per minute)

        Returns:
            List of timestamps in the window
        """
        arrivals = []
        window_duration_sec = (window_end - window_start).total_seconds()

        # Poisson: exponential inter-arrival times
        current = window_start
        while current < window_end:
            # Inter-arrival time in seconds (exponential with lambda_rate)
            if lambda_rate <= 0:
                break
            inter_arrival_sec = self.rng.expovariate(lambda_rate / 60.0)
            current += timedelta(seconds=inter_arrival_sec)

            if current < window_end:
                arrivals.append(current)

        return arrivals

    def bursty_arrivals(
        self,
        window_start: datetime,
        burst_count: int,
        inter_event_sec: float = 5.0,
    ) -> list[datetime]:
        """Generate a burst of closely-spaced events.

        Args:
            window_start: Start of burst
            burst_count: Number of events in burst
            inter_event_sec: Seconds between events in burst

        Returns:
            List of timestamps
        """
        arrivals = []
        current = window_start
        for _ in range(burst_count):
            arrivals.append(current)
            jitter = self.rng.uniform(-1, 1)  # +/- 1 second jitter
            current += timedelta(seconds=inter_event_sec + jitter)
        return arrivals

    def scheduled_arrivals(
        self,
        window_start: datetime,
        window_end: datetime,
        cadence_min: int,
    ) -> list[datetime]:
        """Generate cron-like scheduled arrivals.

        Args:
            window_start: Start of window
            window_end: End of window
            cadence_min: Repeat every N minutes (5, 15, 60, 1440)

        Returns:
            List of timestamps aligned to cadence
        """
        arrivals = []
        current = window_start

        # Align to cadence boundary
        mins_since_epoch = int((current - self.PROJECT_START).total_seconds() / 60)
        mins_to_next = (cadence_min - (mins_since_epoch % cadence_min)) % cadence_min
        current = current + timedelta(minutes=mins_to_next)

        while current < window_end:
            # Add jitter within 30 seconds
            jitter = timedelta(seconds=self.rng.uniform(-30, 30))
            arrivals.append(current + jitter)
            current += timedelta(minutes=cadence_min)

        return arrivals

    def uniform_random_time(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> datetime:
        """Get a random timestamp in window."""
        delta = (window_end - window_start).total_seconds()
        random_sec = self.rng.uniform(0, delta)
        return window_start + timedelta(seconds=random_sec)
