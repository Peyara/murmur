"""
Phase 1 mechanism tests: validation of estimator correctness on constructed inputs.
See bakeoff/PREDICTIONS.md for pre-registered predictions.

Exports: deterministic constructed-input builders for tests 1–4:
- one_way_path(n_states, seed) → Trajectory with strictly directional flow
- closed_loop(n_states, seed) → Trajectory with equal edge count, closed cycle
- ness_chain(seed) → (Trajectory, metadata) with nonequilibrium steady state
- detailed_balance_chain(seed) → (Trajectory, metadata) with detailed balance
- variable_length_sampler(chain_spec, length, seed) → Trajectory of given length
- shannon_entropy_rate(traj, window_size) → float entropy rate dH/dt
"""

from bakeoff.mechanism_tests.builders import (
    one_way_path,
    closed_loop,
    ness_chain,
    detailed_balance_chain,
    variable_length_sampler,
    shannon_entropy_rate,
    ness_chain_spec,
    detailed_balance_chain_spec,
)

__all__ = [
    "one_way_path",
    "closed_loop",
    "ness_chain",
    "detailed_balance_chain",
    "variable_length_sampler",
    "shannon_entropy_rate",
    "ness_chain_spec",
    "detailed_balance_chain_spec",
]
