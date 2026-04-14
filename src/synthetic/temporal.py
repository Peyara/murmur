import random
import warnings
from datetime import datetime, timedelta


class TemporalEngine:
    """Generates realistic temporal profiles for synthetic GCP audit log events.

    Each profile is grounded in empirical evidence from real attack patterns,
    GCP platform constraints, and industry threat reports.
    """

    WINDOW_MINUTES = 15
    PROJECT_START = datetime(2026, 1, 15, 0, 0, 0)

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)  # noqa: S311  # nosec B311
        self.current_time = self.PROJECT_START

    def get_windows(self, count: int):
        return [self.PROJECT_START + timedelta(minutes=i * self.WINDOW_MINUTES) for i in range(count)]

    def poisson_arrivals(self, window_start, window_end, lambda_rate):
        """Generate Poisson-distributed arrivals for rare independent events.

        Suitable for modeling human ad-hoc admin actions or infrequent
        system events where arrivals are uncorrelated.

        Args:
            window_start: Beginning of time window
            window_end: End of time window
            lambda_rate: Average arrival rate (events per minute)

        Returns:
            List of datetime objects with Poisson-distributed spacing
        """
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
        """Generate a uniformly random timestamp within a window.

        Used for background noise, one-off events, or unconstrained actions.

        Args:
            window_start: Beginning of time window
            window_end: End of time window

        Returns:
            Single datetime object uniformly distributed in [window_start, window_end)
        """
        delta = (window_end - window_start).total_seconds()
        return window_start + timedelta(seconds=self.rng.uniform(0, delta))

    def burst_cluster(
        self, window_start: datetime, window_end: datetime, count: int, spread_sec: float = 30
    ) -> list[datetime]:
        """Generate a tight temporal cluster simulating smash-and-grab attacks.

        Evidence: Mandiant M-Trends 2026 reports median handoff time from
        initial access to lateral movement is 22 seconds. Effective attack
        chains compress multiple critical actions (gaining creds, testing access,
        executing payload) into seconds.

        Behavior: Pick a random anchor point within the window. Generate `count`
        timestamps clustered around the anchor using Gaussian jitter with
        sigma = spread_sec/3 (ensures ~99% of events within spread_sec).
        All times clamped to [window_start, window_end] and sorted.

        Args:
            window_start: Beginning of time window
            window_end: End of time window
            count: Number of events to generate
            spread_sec: Standard deviation of spread (in seconds). Default 30.

        Returns:
            Sorted list of datetime objects clustered within spread_sec
        """
        # Pick anchor point uniformly within the window
        window_duration_sec = (window_end - window_start).total_seconds()
        anchor_offset_sec = self.rng.uniform(spread_sec, window_duration_sec - spread_sec)
        anchor = window_start + timedelta(seconds=anchor_offset_sec)

        # Generate count timestamps with Gaussian jitter around anchor
        sigma = spread_sec / 3.0  # 99% within ±spread_sec
        timestamps = []
        for _ in range(count):
            jitter = self.rng.gauss(0, sigma)
            ts = anchor + timedelta(seconds=jitter)
            # Clamp to window bounds
            if ts < window_start:
                ts = window_start
            elif ts > window_end:
                ts = window_end
            timestamps.append(ts)

        return sorted(timestamps)

    def stealth_spread(
        self, window_start: datetime, window_end: datetime, count: int, min_gap_sec: float = 120
    ) -> list[datetime]:
        """Generate timestamps with enforced minimum gaps for patient attacks.

        Evidence: GCP IAM policy propagation takes typically 2 minutes,
        potentially 7+ minutes (https://cloud.google.com/iam/docs/access-change-propagation).
        Attackers performing privilege escalation MUST wait at least 2 minutes
        between granting and testing permissions. Mandiant M-Trends 2026 reports
        median dwell time is 14 days, indicating patient, methodical advancement.

        Behavior: Generate `count` timestamps spread across [window_start, window_end]
        with at least min_gap_sec between consecutive events. Add small random
        jitter (±10% of min_gap_sec) to avoid artificial regularity. If
        count × min_gap_sec exceeds window duration, reduce count and warn.

        Args:
            window_start: Beginning of time window
            window_end: End of time window
            count: Desired number of events (may be reduced)
            min_gap_sec: Minimum seconds between consecutive events. Default 120
                (GCP IAM propagation minimum).

        Returns:
            Sorted list of datetime objects with min_gap_sec separation
        """
        window_duration_sec = (window_end - window_start).total_seconds()

        # Check if request is feasible
        required_duration = count * min_gap_sec
        if required_duration > window_duration_sec:
            actual_count = max(1, int(window_duration_sec / min_gap_sec))
            if actual_count < count:
                warnings.warn(
                    f"stealth_spread: requested {count} events with {min_gap_sec}s "
                    f"gaps requires {required_duration:.0f}s, but window is only "
                    f"{window_duration_sec:.0f}s. Reducing to {actual_count} events.",
                    stacklevel=2,
                )
                count = actual_count

        timestamps = []
        current = window_start
        jitter_range = min_gap_sec * 0.1  # ±10% of min_gap_sec

        for i in range(count):
            # Add base gap plus random jitter
            jitter = self.rng.uniform(-jitter_range, jitter_range)
            current += timedelta(seconds=min_gap_sec + jitter)

            # Clamp to window bounds
            if current > window_end:
                current = window_end

            timestamps.append(current)

        return sorted(set(timestamps))  # Remove duplicates and sort

    def scheduled_periodic(
        self, window_start: datetime, window_end: datetime, interval_sec: float, jitter_sec: float = 2
    ) -> list[datetime]:
        """Generate timestamps at regular intervals with small jitter.

        Evidence: Cloud Scheduler fires on wall-clock time with small undocumented
        jitter. Minimum interval is 60 seconds. GCP's scheduler is highly regular,
        with typical deviation of ±1-2 seconds.

        Behavior: Generate timestamps at regular interval_sec intervals starting
        from window_start, with uniform random jitter of ±jitter_sec on each.
        All times within [window_start, window_end].

        Args:
            window_start: Beginning of time window
            window_end: End of time window
            interval_sec: Interval between events (in seconds)
            jitter_sec: Random jitter range ±jitter_sec. Default 2.

        Returns:
            Sorted list of datetime objects at regular intervals with jitter
        """
        timestamps = []
        current = window_start

        while current < window_end:
            # Add jitter to this event
            jitter = self.rng.uniform(-jitter_sec, jitter_sec)
            ts = current + timedelta(seconds=jitter)

            # Clamp to window bounds
            if ts > window_end:
                break

            timestamps.append(ts)
            current += timedelta(seconds=interval_sec)

        return sorted(timestamps)
