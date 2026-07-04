"""
Deterministic constructed-input builders for Phase 1 mechanism tests (§6.3).

These builders create Trajectory objects with known mathematical properties
(irreversibility, stationarity, reversibility, etc.) to validate the P1/P2
estimators on constructed inputs. They test mechanism correctness only —
NOT world-level properties, archetypes, or detection performance.

All builders are fully determined by (seed, parameters) with no environmental
randomness (Date.now(), /dev/urandom, etc.). Regeneration is byte-identical.

Per §0: every output here is a constructed input with known formal properties,
not a simulation or world sample. Docstrings never claim validation of
detection or FP rates — only estimator math.
"""

import random
import math
from typing import Tuple, Dict, List
from bakeoff.common.trajectory import Trajectory, Transition


# ============================================================================
# Core constructors for §6.3 tests 1–4
# ============================================================================


def one_way_path(n_states: int, seed: int) -> Trajectory:
    """
    Construct a strictly one-directional path: 0 → 1 → 2 → ... → (n_states-1).

    No cycles, no returns. All transitions move forward.
    - Number of transitions: n_states - 1
    - Number of distinct edges: n_states - 1

    Used for mechanism test 1 (one-way vs. loop) to demonstrate that
    a strictly directional path should score strictly higher on P1/P2
    than a reversible cycle of equal edge count.

    Args:
        n_states: number of states in the path (must be >= 2).
                 States are labeled '0', '1', ..., str(n_states-1).
        seed: random seed (for consistency; determinism is intrinsic to
              this path's construction, not dependent on RNG).

    Returns:
        Trajectory: time-ordered sequence of transitions forming a linear path.

    Raises:
        ValueError: if n_states < 2.
    """
    if n_states < 2:
        raise ValueError(f"n_states must be >= 2; got {n_states}")

    random.seed(seed)  # Determinism guard

    states = [str(i) for i in range(n_states)]
    actions = ["move"] * (n_states - 1)

    return Trajectory.from_state_visits(
        actor="path_actor",
        states=states,
        actions=actions,
        start_time=0.0,
        dt=1.0,
    )


def closed_loop(n_states: int, seed: int) -> Trajectory:
    """
    Construct a reversible trajectory by traversing edges in both directions.

    For a given n_states, creates a trajectory where each edge appears in both
    forward and reverse directions with equal frequency:
    0 ↔ 1 ↔ 2 ↔ ... ↔ (n_states-1), with alternating forward-backward traversal.

    Example for n_states=5:
    0 → 1 → 0 → 1 → 0 (4 transitions, 1 distinct edge pair: (0,1) and (1,0))

    This is constructed to have the same number of transitions as one_way_path
    but exhibit reversibility: when time-reversed, the forward and reverse
    edge distributions are identical, yielding P1, P2 ≈ 0.

    Args:
        n_states: controls cycle structure. Creates a back-and-forth trajectory
                 between states 0 and 1, repeated n_states-1 times.
        seed: random seed (determinism guard).

    Returns:
        Trajectory: time-ordered sequence with reversible edge structure.

    Raises:
        ValueError: if n_states < 2.
    """
    if n_states < 2:
        raise ValueError(f"n_states must be >= 2; got {n_states}")

    random.seed(seed)

    # Build alternating path: 0 ↔ 1 ↔ 0 ↔ 1 ↔ ... (n_states-1 transitions)
    # This creates edges (0,1) and (1,0) equally
    states = ["0" if i % 2 == 0 else "1" for i in range(n_states)]
    actions = ["move"] * (n_states - 1)

    return Trajectory.from_state_visits(
        actor="loop_actor",
        states=states,
        actions=actions,
        start_time=0.0,
        dt=1.0,
    )


def ness_chain(seed: int) -> Tuple[Trajectory, Dict]:
    """
    Construct a 3-state nonequilibrium steady state (NESS) with constant occupation
    but nonzero net cycle current.

    Mathematical properties:
    - Stationary distribution: π(A) = π(B) = π(C) = 1/3 (constant occupation)
    - Transition matrix: biased toward forward cycle A → B → C → A
      * P(A → B) = 0.80, P(A → C) = 0.20
      * P(B → C) = 0.85, P(B → A) = 0.15
      * P(C → A) = 0.90, P(C → B) = 0.10
    - Detailed balance violated: e.g., π(A) P(A → B) = (1/3)*0.80 ≠ (1/3)*0.15 = π(B) P(B → A)
    - Net cycle current: positive (A → B → C → A biased)

    Used for mechanism test 2 (NESS anchor) to demonstrate:
    1. Shannon entropy rate (dH/dt) ≈ 0 (stationary distribution)
    2. P1 (forward/reverse KL) > 0 (captures asymmetry)
    3. P2 (flux divergence) > 0 (captures net cycle flux)

    This validates that irreversibility measures respond to cycle current,
    not just distributional entropy.

    Args:
        seed: random seed for trajectory sampling (Markov chain Monte Carlo).

    Returns:
        (trajectory, metadata) where:
        - trajectory: Trajectory object with 300 transitions sampled from the NESS chain.
        - metadata: dict with keys:
            'intended_stationary_dist': dict {state: probability}
            'intended_cycle_current': str describing net flux
            'transition_matrix': dict of per-state transition probabilities
            'description': human-readable summary
    """
    random.seed(seed)

    # Transition probabilities (unequal forward/reverse on the cycle)
    transition_matrix = {
        "A": [("B", 0.80), ("C", 0.20)],
        "B": [("C", 0.85), ("A", 0.15)],
        "C": [("A", 0.90), ("B", 0.10)],
    }

    # Sample a long trajectory from this Markov chain
    trajectory_length = 300
    current_state = "A"
    transitions = []

    for i in range(trajectory_length):
        t = float(i) * 1.0
        options, probs = zip(*transition_matrix[current_state])
        next_state = random.choices(list(options), weights=probs, k=1)[0]

        transitions.append(
            Transition(
                t=t,
                actor="ness_actor",
                src=current_state,
                dst=next_state,
                action="cycle",
            )
        )
        current_state = next_state

    traj = Trajectory(transitions)

    metadata = {
        "intended_stationary_dist": {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3},
        "intended_cycle_current": "positive (A→B→C→A biased due to unequal P(i→j) vs P(j→i))",
        "transition_matrix": transition_matrix,
        "description": (
            "3-state cycle with stationary π = (1/3, 1/3, 1/3) but nonzero net cycle flux. "
            "Used to anchor P1/P2 interpretation: they should capture flux, not entropy. "
            "The chain violates detailed balance on every edge."
        ),
    }

    return traj, metadata


def detailed_balance_chain(seed: int) -> Tuple[Trajectory, Dict]:
    """
    Construct a reversible chain satisfying detailed balance (per-edge balance).

    Mathematical properties:
    - Transition matrix: symmetric under reversal
      * P(A → B) = P(B → A) = 0.5
      * P(B → C) = P(C → B) = 0.5
      * Self-loops: P(A → A) = 0.0, P(B → B) = 0.0, P(C → C) = 0.0
    - Detailed balance holds: π(i) P(i → j) = π(j) P(j → i) for all i, j
    - Stationary distribution: π = (1/3, 1/3, 1/3) (for this implementation)
    - Net flux: zero on every edge in expectation

    Used for mechanism test 3 (reversal sanity):
    1. Time-reversing a trajectory from this chain should give P1 and P2 ≈ 0
       (since forward and reverse distributions are nearly identical).
    2. Both directions should score equivalently on irreversibility metrics.

    Args:
        seed: random seed for trajectory sampling.

    Returns:
        (trajectory, metadata) where:
        - trajectory: Trajectory object with 300 transitions.
        - metadata: dict documenting reversibility and expected P1/P2 values.
    """
    random.seed(seed)

    # Simple reversible chain: A ↔ B ↔ C, no self-loops
    # All transitions are 50/50 (symmetric)
    transition_matrix = {
        "A": [("B", 1.0)],
        "B": [("A", 0.5), ("C", 0.5)],
        "C": [("B", 1.0)],
    }

    trajectory_length = 300
    current_state = "A"
    transitions = []

    for i in range(trajectory_length):
        t = float(i) * 1.0
        options, probs = zip(*transition_matrix[current_state])
        next_state = random.choices(list(options), weights=probs, k=1)[0]

        transitions.append(
            Transition(
                t=t,
                actor="db_actor",
                src=current_state,
                dst=next_state,
                action="move",
            )
        )
        current_state = next_state

    traj = Trajectory(transitions)

    metadata = {
        "property": "satisfies detailed balance (reversible)",
        "expected_d_kl": "~0 (forward and reverse distributions nearly identical)",
        "expected_flux_divergence": "~0 (net flux ≈ 0 on all edges)",
        "transition_matrix": transition_matrix,
        "description": (
            "Symmetric random walk: A↔B↔C with equal forward/reverse probabilities. "
            "Forward and time-reversed trajectories should have statistically identical "
            "transition distributions. P1 and P2 should both score near zero."
        ),
    }

    return traj, metadata


def variable_length_sampler(
    chain_spec: Dict, length: int, seed: int
) -> Trajectory:
    """
    Sample a trajectory of a given length from a Markov chain specification.

    Used for mechanism test 4 (estimator convergence) to study how P1/P2 scores
    vary with trajectory length. Enables measurement of minimum trajectory length
    needed for stable estimates and informing §3.1's simulation horizon.

    Args:
        chain_spec: dict with keys:
            'transition_matrix': dict of {state: [(next_state, prob), ...]}
                                 (per-state outgoing transitions with probabilities)
            'start_state': initial state (default 'A')
            'actor': actor identifier (default 'test_actor')
        length: desired number of transitions (must be >= 1).
        seed: random seed for sampling.

    Returns:
        Trajectory: sampled from the chain with exactly `length` transitions.

    Raises:
        ValueError: if length < 1 or if a sampled state is not in transition_matrix.
    """
    if length < 1:
        raise ValueError(f"length must be >= 1; got {length}")

    random.seed(seed)

    transition_matrix = chain_spec["transition_matrix"]
    current_state = chain_spec.get("start_state", "A")
    actor = chain_spec.get("actor", "test_actor")

    transitions = []

    for i in range(length):
        t = float(i) * 1.0
        if current_state not in transition_matrix:
            raise ValueError(
                f"State {current_state!r} not in transition_matrix. "
                f"Available states: {set(transition_matrix.keys())}"
            )

        options, probs = zip(*transition_matrix[current_state])
        next_state = random.choices(list(options), weights=probs, k=1)[0]

        transitions.append(
            Transition(
                t=t,
                actor=actor,
                src=current_state,
                dst=next_state,
                action="step",
            )
        )
        current_state = next_state

    return Trajectory(transitions)


# ============================================================================
# Helpers for NESS anchor test (mechanism test 2)
# ============================================================================


def shannon_entropy_rate(traj: Trajectory, window_size: int = 50) -> float:
    """
    Estimate Shannon entropy rate (dH/dt) from a trajectory using sliding windows.

    For a trajectory sampled from a stationary distribution (equilibrium or NESS),
    the entropy rate should be approximately zero — occupancy probabilities are
    not drifting. This helps distinguish "constant occupation" (stationary) from
    "changing occupation" (nonstationary drift).

    Used for mechanism test 2 (NESS anchor) as a sanity check: verify that
    the NESS chain has dH/dt ≈ 0 while P1 and P2 read strongly positive.

    Mathematical definition:
    - Compute Shannon entropy H(t) over a sliding window of window_size transitions.
    - For two consecutive windows: entropy_rate ≈ (H_window2 - H_window1) / window_size
    - Units: nats per transition (or per unit time if dt is not 1.0)

    Interpretation:
    - entropy_rate ≈ 0: stationary (occupation stable)
    - entropy_rate > 0: occupancy expanding (exploring new states)
    - entropy_rate < 0: occupancy contracting (settling on fewer states)

    Args:
        traj: Trajectory object (any length).
        window_size: size (number of transitions) per sliding window.
                    Should be small relative to trajectory length (default 50).

    Returns:
        float: estimated entropy rate (nats per transition), typically in range [-1, 1].
               For a stationary trajectory, expect |entropy_rate| < 0.1.

    Raises:
        ValueError: if trajectory has fewer than 2 * window_size transitions.
    """
    if len(traj) < 2 * window_size:
        raise ValueError(
            f"Trajectory too short ({len(traj)} transitions) for "
            f"window_size={window_size}. Need at least {2 * window_size}."
        )

    def compute_entropy(states: List[str]) -> float:
        """Compute Shannon entropy H = -sum_i p_i log(p_i) of a state sequence."""
        if not states:
            return 0.0

        counts: Dict[str, int] = {}
        for state in states:
            counts[state] = counts.get(state, 0) + 1

        n = len(states)
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / n
                entropy -= p * math.log(p)  # Natural logarithm

        return entropy

    # Extract destination states in two consecutive windows
    window1_states = [traj[i].dst for i in range(window_size)]
    window2_states = [traj[i].dst for i in range(window_size, 2 * window_size)]

    h1 = compute_entropy(window1_states)
    h2 = compute_entropy(window2_states)

    # Rate of change: ΔH / Δt, where Δt = window_size transitions
    entropy_rate = (h2 - h1) / window_size

    return entropy_rate


# ============================================================================
# Convenience re-exports for NESS and detailed-balance chains as specifications
# ============================================================================


def ness_chain_spec() -> Dict:
    """
    Return the transition matrix specification for the NESS chain.

    Useful for variable_length_sampler to generate NESS trajectories
    of arbitrary length.

    Returns:
        dict with 'transition_matrix', 'start_state', 'actor' keys.
    """
    return {
        "transition_matrix": {
            "A": [("B", 0.80), ("C", 0.20)],
            "B": [("C", 0.85), ("A", 0.15)],
            "C": [("A", 0.90), ("B", 0.10)],
        },
        "start_state": "A",
        "actor": "ness_actor",
    }


def detailed_balance_chain_spec() -> Dict:
    """
    Return the transition matrix specification for the detailed-balance chain.

    Useful for variable_length_sampler to generate DB trajectories
    of arbitrary length.

    Returns:
        dict with 'transition_matrix', 'start_state', 'actor' keys.
    """
    return {
        "transition_matrix": {
            "A": [("B", 1.0)],
            "B": [("A", 0.5), ("C", 0.5)],
            "C": [("B", 1.0)],
        },
        "start_state": "A",
        "actor": "db_actor",
    }
