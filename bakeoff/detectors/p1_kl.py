"""
P1 — Forward/Reverse KL-divergence estimator.

Per-actor trajectory → estimate the empirical transition distribution over
the actor's observed state space → compute D_KL(forward ‖ reverse), where
'forward' is the transition distribution of the trajectory as-is, and 'reverse'
is the distribution of the time-reversed trajectory.

D_KL(forward ‖ reverse) measures asymmetry: a value of 0 indicates detailed
balance (reversibility); positive values indicate irreversibility (forward
and reverse distributions diverge).

This is a FROZEN interface stub for Phase 1. Implementers must NOT change
the signature. Pre-registered smoothing alpha is chosen on synthetic chains
only, before any world data — see PREDICTIONS.md.
"""

from typing import Optional
from bakeoff.common.trajectory import Trajectory


def score(
    traj: Trajectory,
    *,
    alpha: float = 1.0,
) -> float:
    """
    Compute D_KL(forward ‖ reverse) for a trajectory.

    FROZEN SIGNATURE — do not change.

    Mathematical definition:
    ========================

    Given a trajectory (sequence of transitions), define:
    - State space S = all (src, dst, action) edges visited
    - Transition counts: forward[s, a, d] = # times we traverse s --a--> d in chronological order
    - Reverse counts: reverse[s, a, d] = # times we traverse s --a--> d in the time-reversed trajectory

    With additive (Laplace) smoothing (alpha):
    - P_fwd(s, a, d) = (forward[s, a, d] + alpha) / (sum_s,a,d forward[s, a, d] + alpha * |S|)
    - P_rev(s, a, d) = (reverse[s, a, d] + alpha) / (sum_s,a,d reverse[s, a, d] + alpha * |S|)

    where |S| = number of unique edges observed.

    D_KL(forward ‖ reverse) = sum over all edges (s, a, d) of:
        P_fwd(s, a, d) * log(P_fwd(s, a, d) / P_rev(s, a, d))

    Terms with P_fwd(s, a, d) = 0 contribute 0 (by limit). Never skip zero terms;
    the presence of asymmetry is itself the signal.

    Unseen-transition handling:
    - Every observed (src, dst, action) triple receives at least alpha pseudo-counts
    - Unseen triples (not in forward or reverse) receive 0 probability and contribute 0 to D_KL
    - This avoids infinite divergence from truly novel edges

    Pre-registered hyperparameter (MUST NOT TUNE on world data):
    - alpha = 1.0 (additive smoothing, Laplace smoothing variant)
      Rationale: standard choice in NLP/statistical mechanics; handles small-sample
      bias without heavy regularization. Selected to pass mechanism tests 1–3 with
      high confidence on synthetic chains before touching any generated worlds.

    Args:
        traj: Trajectory object (single actor, time-ordered transitions).
        alpha: smoothing parameter (additive/Laplace). Default 1.0 is pre-registered
               and must NOT be changed without explicit justification documented
               in PREDICTIONS.md. Sensitivity to alpha is an ablation study (Phase 4).

    Returns:
        float: D_KL(forward ‖ reverse), always >= 0. A value of 0 (up to numerical
               precision) indicates a reversible trajectory (detailed balance).
               Higher values indicate stronger asymmetry / irreversibility.

    Raises:
        ValueError: if traj is empty or contains no transitions.
        TypeError: if traj is not a Trajectory object.

    Implementation notes for downstream:
    - Use math.log (natural logarithm) for numerical stability.
    - Handle 0 * log(0/x) = 0 carefully: use L'Hôpital or explicit check.
    - Do NOT normalize D_KL by trajectory length or state-space size here
      (relative normalization happens at the detector level, Phase 4).
    - Do NOT implement cross-entropy or other variants; this signature is D_KL only.
    """
    import math
    from collections import Counter

    # Validate input
    if not isinstance(traj, Trajectory):
        raise TypeError(
            f"Expected Trajectory object, got {type(traj).__name__}"
        )
    if len(traj) == 0:
        raise ValueError("Trajectory must contain at least one transition.")

    # Extract forward edges: (src, dst, action) tuples in chronological order
    forward_edges = traj.edges()
    forward_counts = Counter(forward_edges)

    # Extract reverse edges by time-reversing the trajectory.
    # time_reversed() swaps src↔dst for each transition and re-orders chronologically.
    reversed_traj = traj.time_reversed()
    reverse_edges = reversed_traj.edges()
    reverse_counts = Counter(reverse_edges)

    # State space S = union of all edges observed in forward or reverse.
    # Each edge is counted separately to allow for asymmetry.
    all_edges = set(forward_counts.keys()) | set(reverse_counts.keys())
    num_edges = len(all_edges)

    # Total transitions (normalization constant for probability distributions).
    # Both forward and reverse have the same total (= len(traj)) by construction.
    total_forward = len(forward_edges)
    total_reverse = len(reverse_edges)

    # Compute KL divergence: D_KL(P_fwd || P_rev) = Σ_edges P_fwd(e) * log(P_fwd(e) / P_rev(e))
    # With Laplace (additive) smoothing:
    #   P_fwd(edge) = (count_fwd + alpha) / (total_fwd + alpha * |S|)
    #   P_rev(edge) = (count_rev + alpha) / (total_rev + alpha * |S|)
    #
    # Smoothing ensures P_fwd(e) > 0 and P_rev(e) > 0 for all e ∈ S,
    # avoiding log(0) and division by zero. For edges with count_fwd = 0,
    # the term contributes P_fwd(e) * log(P_fwd(e) / P_rev(e)) with the smoothed
    # probability, which is > 0.

    kl_divergence = 0.0

    for edge in all_edges:
        count_fwd = forward_counts.get(edge, 0)
        count_rev = reverse_counts.get(edge, 0)

        # Apply Laplace smoothing
        p_fwd = (count_fwd + alpha) / (total_forward + alpha * num_edges)
        p_rev = (count_rev + alpha) / (total_reverse + alpha * num_edges)

        # KL divergence term: p_fwd * log(p_fwd / p_rev)
        # With Laplace smoothing, both p_fwd and p_rev are strictly > 0.
        kl_divergence += p_fwd * math.log(p_fwd / p_rev)

    # KL divergence is guaranteed >= 0 by Gibbs' inequality.
    # Clamp to handle potential floating-point underflow artifacts.
    return max(0.0, kl_divergence)
