"""
P1e — Excess (Nonadiabatic) Entropy Production.

Per-actor scoring relative to the actor's own trailing steady-state baseline.

Score = D_KL(current-window transition distribution || actor's rolling-baseline
transition distribution), Laplace-smoothed.

Rationale (PREDICTIONS.md physics decision, 2026-07-03):
- Benign automation is a non-equilibrium steady state (NESS) whose persistent
  currents are HOUSEKEEPING (large but structural → ~0 excess).
- An attack drives the actor OFF its own steady state → positive EXCESS.
- Hard negatives (ETL/backup/break-glass one-way benign) are scored as ~0
  (housekeeping, structural to that actor's type).
- Living-off-the-land attacks (novel order/rate but reusing actor's own edges)
  are caught via rate/structure deviation being estimable with per-actor data.

FROZEN SIGNATURE: rolling-window scorer with N >= 80 transitions minimum
(locked decision from PREDICTIONS.md Correction 2).
"""

import math
from typing import Callable, List, Tuple, Optional
from collections import Counter
from bakeoff.common.trajectory import Trajectory, Transition


def score_window(
    actor_traj_up_to_now: Trajectory,
    window_transitions: Trajectory,
    *,
    alpha: float = 1.0,
) -> float:
    """
    Score a window as excess entropy production relative to actor's trailing baseline.

    Mathematical definition:
    ========================

    The trailing baseline is the empirical transition distribution of all transitions
    in actor_traj_up_to_now EXCEPT those in window_transitions. This represents the
    actor's "normal" (steady-state) behavior.

    The window distribution is the transition distribution of window_transitions.

    Excess EP = D_KL(window_distribution ‖ baseline_distribution), Laplace-smoothed.

    If the window deviates from the actor's historical pattern, D_KL > 0.
    If the window matches the actor's historical pattern exactly, D_KL ≈ 0.

    With Laplace smoothing (alpha):
    - P_window(edge) = (count_in_window + alpha) / (|window| + alpha * num_edges)
    - P_baseline(edge) = (count_in_baseline + alpha) / (|baseline| + alpha * num_edges)

    where num_edges = union of edges in window and baseline.

    D_KL(window ‖ baseline) = sum over all edges e of:
        P_window(e) * log(P_window(e) / P_baseline(e))

    Pre-registered hyperparameter:
    - alpha = 1.0 (Laplace/additive smoothing)

    Args:
        actor_traj_up_to_now: Trajectory — all transitions for this actor up to now,
                             including the current window. Used to extract the baseline
                             (everything except window_transitions).
        window_transitions: Trajectory — the current window to score. Must be a
                           sub-trajectory of actor_traj_up_to_now (in terms of content,
                           though the actual object may be constructed separately).
        alpha: smoothing parameter (default 1.0, pre-registered).

    Returns:
        float: D_KL(window ‖ baseline), always >= 0. Higher values indicate
               stronger deviation from the actor's normal pattern.

    Raises:
        ValueError: if actor_traj_up_to_now is empty, if actor_traj_up_to_now and
                   window_transitions have different actor IDs, or if window_transitions
                   is longer than actor_traj_up_to_now.
        TypeError: if inputs are not Trajectory objects.
    """
    # Validate inputs
    if not isinstance(actor_traj_up_to_now, Trajectory):
        raise TypeError(
            f"actor_traj_up_to_now must be a Trajectory object, "
            f"got {type(actor_traj_up_to_now).__name__}"
        )
    if not isinstance(window_transitions, Trajectory):
        raise TypeError(
            f"window_transitions must be a Trajectory object, "
            f"got {type(window_transitions).__name__}"
        )

    if len(actor_traj_up_to_now) == 0:
        raise ValueError("actor_traj_up_to_now must not be empty.")

    if actor_traj_up_to_now.actor != window_transitions.actor:
        raise ValueError(
            f"actor_traj_up_to_now and window_transitions must belong to the same actor; "
            f"got {actor_traj_up_to_now.actor} vs {window_transitions.actor}"
        )

    if len(window_transitions) > len(actor_traj_up_to_now):
        raise ValueError(
            f"window_transitions cannot be longer than actor_traj_up_to_now; "
            f"got {len(window_transitions)} vs {len(actor_traj_up_to_now)}"
        )

    # Extract baseline: all transitions in actor_traj_up_to_now EXCEPT those in window
    # by time range. Identify window by its time bounds.
    window_t_min = window_transitions[0].t
    window_t_max = window_transitions[-1].t

    baseline_transitions = [
        t for t in actor_traj_up_to_now
        if not (window_t_min <= t.t <= window_t_max)
    ]

    if not baseline_transitions:
        # Window includes all transitions; baseline is empty.
        # In this case, we can't estimate a baseline distribution.
        # Return 0 as a safe default (no history, no deviation measurable).
        return 0.0

    # Create baseline and window edge count distributions
    baseline_edges = Trajectory(baseline_transitions).edges()
    window_edges = window_transitions.edges()

    baseline_counts = Counter(baseline_edges)
    window_counts = Counter(window_edges)

    # Union of all edges observed in baseline or window
    all_edges = set(baseline_counts.keys()) | set(window_counts.keys())
    num_edges = len(all_edges)

    if num_edges == 0:
        return 0.0

    # Total transition counts
    total_baseline = len(baseline_edges)
    total_window = len(window_edges)

    if total_baseline == 0 or total_window == 0:
        return 0.0

    # Compute D_KL(window ‖ baseline) with Laplace smoothing
    kl_divergence = 0.0

    for edge in all_edges:
        count_window = window_counts.get(edge, 0)
        count_baseline = baseline_counts.get(edge, 0)

        # Laplace smoothing
        p_window = (count_window + alpha) / (total_window + alpha * num_edges)
        p_baseline = (count_baseline + alpha) / (total_baseline + alpha * num_edges)

        # KL term
        kl_divergence += p_window * math.log(p_window / p_baseline)

    return max(0.0, kl_divergence)


def rolling_scorer(
    actor_trajectory: Trajectory,
    *,
    window_size: int = 80,
    alpha: float = 1.0,
) -> Callable[[float], Optional[float]]:
    """
    Create a rolling-window scorer for a single actor.

    Returns a callable that, given a time t, scores the window of the last
    window_size transitions ending at time t, relative to the actor's baseline
    (all transitions before the window).

    The scorer emits (t, score) tuples as windows slide through the trajectory.

    Args:
        actor_trajectory: Trajectory object (single actor, all transitions).
        window_size: number of transitions per rolling window (default 80,
                    per §8 locked decision).
        alpha: smoothing parameter for score_window() (default 1.0).

    Returns:
        Callable[[float], Optional[float]] — a function that, given a time t,
        returns the P1e score for a window ending at time t (or None if no valid
        window exists at t). The window is the last window_size transitions
        up to and including time t.

    Raises:
        ValueError: if actor_trajectory is empty or has fewer than window_size transitions.
        TypeError: if actor_trajectory is not a Trajectory object.
    """
    if not isinstance(actor_trajectory, Trajectory):
        raise TypeError(
            f"actor_trajectory must be a Trajectory object, "
            f"got {type(actor_trajectory).__name__}"
        )

    if len(actor_trajectory) < window_size:
        raise ValueError(
            f"actor_trajectory must have at least window_size ({window_size}) transitions; "
            f"got {len(actor_trajectory)}"
        )

    # Precompute transitions sorted by time (should already be ordered, but verify)
    transitions_by_time = sorted(actor_trajectory.transitions, key=lambda t: t.t)

    def scorer_at_time(t: float) -> Optional[Tuple[float, float]]:
        """
        Score a rolling window ending at (or before) time t.

        Args:
            t: time anchor. Returns score for the window of the last window_size
               transitions with t_transition <= t.

        Returns:
            Tuple (window_end_time, score) if a valid window exists at t,
            else None.
        """
        # Find all transitions up to time t
        transitions_up_to_t = [
            tr for tr in transitions_by_time if tr.t <= t
        ]

        if len(transitions_up_to_t) < window_size:
            # Not enough history yet; no valid window
            return None

        # Extract the window: last window_size transitions
        window_start_idx = len(transitions_up_to_t) - window_size
        window_trans = transitions_up_to_t[window_start_idx:]

        # The baseline is everything before the window
        baseline_trans = transitions_up_to_t[:window_start_idx]

        # Construct trajectories and score
        baseline_traj = Trajectory(baseline_trans)
        window_traj = Trajectory(window_trans)
        all_up_to_t = Trajectory(transitions_up_to_t)

        score = score_window(all_up_to_t, window_traj, alpha=alpha)
        window_end_time = window_traj[-1].t

        return (window_end_time, score)

    return scorer_at_time


def rolling_scorer_stream(
    actor_trajectory: Trajectory,
    *,
    window_size: int = 80,
    alpha: float = 1.0,
) -> List[Tuple[float, float]]:
    """
    Emit a stream of (window_end_time, score) tuples for a rolling-window analysis
    of a single actor.

    Slides a window of window_size transitions through the trajectory, emitting
    one (time, score) pair per valid window position.

    Args:
        actor_trajectory: Trajectory object (single actor).
        window_size: number of transitions per window (default 80).
        alpha: smoothing parameter (default 1.0).

    Returns:
        List of (window_end_time, score) tuples, ordered by window_end_time.
        Empty if trajectory has fewer than window_size transitions.

    Raises:
        ValueError, TypeError: same as rolling_scorer().
    """
    if not isinstance(actor_trajectory, Trajectory):
        raise TypeError(
            f"actor_trajectory must be a Trajectory object, "
            f"got {type(actor_trajectory).__name__}"
        )

    if len(actor_trajectory) < window_size:
        return []

    transitions = list(actor_trajectory.transitions)
    results = []

    # Slide window over the trajectory
    for window_end_idx in range(window_size - 1, len(transitions)):
        window_start_idx = window_end_idx - window_size + 1

        window_trans = transitions[window_start_idx : window_end_idx + 1]
        baseline_trans = transitions[:window_start_idx]

        if not baseline_trans:
            # No baseline yet (window starts at position 0)
            # Still compute the score, but with an empty baseline
            window_traj = Trajectory(window_trans)
            all_up_to_here = window_traj
        else:
            window_traj = Trajectory(window_trans)
            all_up_to_here = Trajectory(transitions[: window_end_idx + 1])

        score = score_window(all_up_to_here, window_traj, alpha=alpha)
        window_end_time = window_trans[-1].t

        results.append((window_end_time, score))

    return results
