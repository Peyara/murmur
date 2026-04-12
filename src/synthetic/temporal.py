import random
from datetime import datetime, timedelta


class TemporalEngine:
    WINDOW_MINUTES = 15
    PROJECT_START = datetime(2026, 1, 15, 0, 0, 0)

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)  # noqa: S311
        self.current_time = self.PROJECT_START

    def get_windows(self, count: int):
        return [
            self.PROJECT_START + timedelta(minutes=i * self.WINDOW_MINUTES)
            for i in range(count)
        ]

    def poisson_arrivals(self, window_start, window_end, lambda_rate):
        arrivals = []
        current = window_start
        while current < window_end:
            if lambda_rate <= 0:
                break
            inter_arrival_sec = self.rng.expovariate(lambda_rate / 60.0)
            current += timedelta(seconds=inter_arrival_sec)
            if current < window_end:
                arrivals.append(current)
        return arrivals

    def uniform_random_time(self, window_start, window_end):
        delta = (window_end - window_start).total_seconds()
        return window_start + timedelta(seconds=self.rng.uniform(0, delta))
