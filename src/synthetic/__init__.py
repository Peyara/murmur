"""Synthetic GCP audit log trajectory generator.

Generates realistic GCP audit log sequences for testing and R&D.
Produces raw GCP Cloud Audit Log JSONL that parses to CanonicalEvents.
"""

from src.synthetic.composer import TrajectoryComposer


def generate_trajectory(
    actors: int = 10,
    windows: int = 20,
    attack_ratio: float = 0.1,
    seed: int = 42,
) -> list[dict]:
    """Generate synthetic GCP audit log trajectory.

    Args:
        actors: Number of service account actors (5-50)
        windows: Number of 15-minute windows (5-100)
        attack_ratio: Fraction of windows to inject attacks into (0.0-1.0)
        seed: Random seed for reproducibility

    Returns:
        List of raw GCP audit log dicts, sorted by timestamp, consumable by parser.py
    """
    composer = TrajectoryComposer(actors, windows, attack_ratio, seed)
    return composer.compose()
