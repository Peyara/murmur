"""
P2 — Flux divergence estimator.

Per-actor trajectory → compute empirical probability flux on each edge
(forward minus reverse) → aggregate per window using pre-registered aggregation
function (L1 norm as primary, max-edge as secondary).

Flux divergence is the net probability "leak" out of equilibrium: in a reversible
system, forward flux equals reverse flux on every edge; in an irreversible system,
there is net accumulation (positive flux) or depletion (negative flux) on edges
that form one-way chains.

This is a FROZEN interface stub for Phase 1. Implementers must NOT change
the signature or primary aggregation (L1).
"""

from typing import Literal, Dict
from bakeoff.common.trajectory import Trajectory


def score(
    traj: Trajectory,
    *,
    aggregation: Literal["l1", "max_edge"] = "l1",
) -> float:
    """
    Compute net probability flux per edge and aggregate.

    FROZEN SIGNATURE — do not change.

    Mathematical definition:
    ========================

    Given a trajectory:
    - Forward edge counts: fwd[e] = # times edge e appears in chronological order
    - Reverse edge counts: rev[e] = # times edge e appears in time-reversed trajectory
    - Total counts: N_fwd = sum of fwd[e], N_rev = sum of rev[e]

    Empirical flux per edge:
    - P_fwd(e) = fwd[e] / N_fwd
    - P_rev(e) = rev[e] / N_rev
    - net_flux(e) = P_fwd(e) - P_rev(e)

    (Note: N_fwd = N_rev = trajectory length, so this simplifies, but the
    probabilistic interpretation is key for handling short trajectories and
    missing edges.)

    Aggregation (pre-registered):
    Primary (L1 norm, PRE-REGISTERED):
        score = sum_e |net_flux(e)| = sum_e |P_fwd(e) - P_rev(e)|
        Rationale: measures total probability divergence from detailed balance.
        Invariant to permutation of edges. Detects one-way flows (where net_flux > 0
        on forward chain, < 0 on return path or absent).

    Secondary (max-edge, for ablation only):
        score = max_e |net_flux(e)|
        Rationale: detects extreme per-edge violations.

    Unseen-transition handling:
    - An edge never visited in forward remains at P_fwd = 0
    - An edge never visited in reverse remains at P_rev = 0
    - net_flux(e) = |P_fwd(e) - P_rev(e)| contributes to the L1 sum
    - No smoothing applied here (unlike P1); asymmetry from unobserved reverse
      is natural and desired.

    Pre-registered aggregation:
    - Primary: 'l1' (L1 norm of net-flux vector)
    - Secondary: 'max_edge' (maximum absolute flux per edge)
    - Rationale: L1 is interpretable as total probability divergence and robust
      to outlier edges; max-edge is sensitive to extreme violations.
    - MUST NOT add new aggregation variants without explicit design justification.

    Args:
        traj: Trajectory object (single actor, time-ordered transitions).
        aggregation: 'l1' (default, pre-registered) or 'max_edge' (secondary ablation).

    Returns:
        float: aggregated net flux, always >= 0. A value of 0 indicates
               reversibility (detailed balance). Higher values indicate
               stronger asymmetry / irreversibility.

    Raises:
        ValueError: if traj is empty or contains no transitions.
        ValueError: if aggregation is not 'l1' or 'max_edge'.
        TypeError: if traj is not a Trajectory object.

    Implementation notes for downstream:
    - Compute edge flux over the entire trajectory (no windowing here; windows
      are applied at the detector level, Phase 4).
    - Do NOT normalize by trajectory length or state-space size in this estimator
      (that happens at Phase 4 for relative scoring).
    - Prefer numpy.abs() for numerical stability if numpy is available, else abs().
    - Do NOT implement custom aggregations; only 'l1' and 'max_edge'.
    """
    from collections import Counter

    # Validate inputs.
    if not isinstance(traj, Trajectory):
        raise TypeError(f"traj must be a Trajectory object; got {type(traj).__name__}")

    if aggregation not in ("l1", "max_edge"):
        raise ValueError(
            f"aggregation must be 'l1' or 'max_edge'; got {aggregation!r}"
        )

    if len(traj) < 2:
        raise ValueError("Trajectory must contain at least 2 transitions to form edges.")

    # ===== Mathematics =====
    # Extract forward edges (src, dst, action) in chronological order.
    fwd_edges = traj.edges()

    # Get time-reversed trajectory and extract reverse edges.
    # time_reversed() swaps src/dst and reverses the temporal order.
    traj_rev = traj.time_reversed()
    rev_edges = traj_rev.edges()

    # Count edge occurrences (multiset cardinality).
    fwd_counts = Counter(fwd_edges)
    rev_counts = Counter(rev_edges)

    # Total number of edges (transitions - 1).
    # N_fwd = N_rev = number of edges, by construction.
    n_edges = len(fwd_edges)

    # For each edge, compute empirical transition probability and net flux.
    # Union of all edges observed in forward or reverse direction.
    all_edges = set(fwd_counts.keys()) | set(rev_counts.keys())

    net_fluxes = []
    for edge in all_edges:
        # P_fwd(e) = fwd[e] / n_edges; defaults to 0 if never seen forward.
        # P_rev(e) = rev[e] / n_edges; defaults to 0 if never seen reverse.
        p_fwd = fwd_counts.get(edge, 0) / n_edges
        p_rev = rev_counts.get(edge, 0) / n_edges

        # net_flux(e) = P_fwd(e) - P_rev(e)
        # Positive: more forward than reverse (asymmetry favoring forward).
        # Negative: more reverse than forward (asymmetry favoring reverse).
        # Zero: detailed balance on this edge.
        net_flux = p_fwd - p_rev
        net_fluxes.append(net_flux)

    # ===== Aggregation (pre-registered) =====
    if aggregation == "l1":
        # L1 norm of net-flux vector: sum of absolute values.
        # Interpretation: total probability divergence from detailed balance.
        score_val = sum(abs(flux) for flux in net_fluxes)

    else:  # aggregation == "max_edge"
        # Maximum absolute flux per edge.
        # Interpretation: largest per-edge asymmetry.
        score_val = max((abs(flux) for flux in net_fluxes), default=0.0)

    return float(score_val)


def node_level_divergence(traj: Trajectory) -> Dict[str, float]:
    """
    Compute node-level net outward flux per node (helper for source/sink detection).

    For each node (state) in the trajectory, compute the net probability flux:
      divergence(node) = P(edges leaving node) - P(edges entering node)

    This is computed over the forward (chronological) direction only. Positive
    divergence indicates a "source" node (net outward flow, such as the root of
    an exfiltration chain). Negative divergence indicates a "sink" node (net
    inward flow). Near-zero divergence indicates a transient or balanced node.

    The source/sink signature is diagnostic for one-way flows: attacks that
    follow a path A → B → C → D (with a return path D → C optional) often
    exhibit strong sources at A and sinks at D. This helper can be used by
    downstream detectors to understand the trajectory's causal structure.

    Args:
        traj: Trajectory object.

    Returns:
        dict mapping node identifier (str) to net divergence (float).
        Keys are all unique nodes in traj.state_space().

    Raises:
        ValueError: if traj contains fewer than 2 transitions.
        TypeError: if traj is not a Trajectory object.
    """
    from collections import Counter

    if not isinstance(traj, Trajectory):
        raise TypeError(f"traj must be a Trajectory object; got {type(traj).__name__}")

    if len(traj) < 2:
        raise ValueError("Trajectory must contain at least 2 transitions.")

    fwd_edges = traj.edges()
    fwd_counts = Counter(fwd_edges)
    n_edges = len(fwd_edges)

    # Collect all nodes from state space.
    nodes = traj.state_space()

    divergence = {}
    for node in nodes:
        # Empirical flux out: sum of probabilities of edges leaving this node.
        flux_out = sum(count for (src, dst, _), count in fwd_counts.items() if src == node) / n_edges

        # Empirical flux in: sum of probabilities of edges entering this node.
        flux_in = sum(count for (src, dst, _), count in fwd_counts.items() if dst == node) / n_edges

        # Net divergence = outflow - inflow.
        divergence[node] = flux_out - flux_in

    return divergence
