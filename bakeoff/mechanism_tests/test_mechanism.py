"""
Phase 1 mechanism tests (§6.3) — Validation question #1.

Tests the estimator math on constructed inputs with known properties.
NOT testing worlds, attacks, or detection performance — only that P1/P2
correctly implement irreversibility measurement.

All tests are deterministic; every constructed input is fully determined by (seed, config).

Test structure:
1. One-way vs loop: strict irreversibility dominates reversibility
2. NESS anchor: entropy rate ~ 0 but irreversibility > 0
3. Reversal/detailed-balance: time-reversal swaps KL; balanced chain scores ~0
4. Estimator convergence: minimum trajectory length for stable estimates
5. Subsampling robustness: graceful degradation under event loss

Failing tests 1–3 indicates an implementation bug. Test 4 failing (absurd data
requirements) escalates to the decision. Test 5 is a robustness sanity check.
"""

import math
import statistics
from typing import Tuple, Dict, List
import random

from bakeoff.detectors import p1_kl, p2_flux
from bakeoff.mechanism_tests import builders
from bakeoff.common.trajectory import Trajectory


# =============================================================================
# Test 1: One-way vs loop (strictly one-directional path > closed cycle)
# =============================================================================


def test_one_way_vs_loop():
    """
    Test 1: A strictly one-directional path should score strictly higher
    than a closed loop of equal edge count and transition length.

    This is the defining property of irreversibility detectors:
    - one_way_path: 0 → 1 → 2 → ... → n (forward only)
    - closed_loop: 0 → 1 → ... → n-1 → 0 (reversible cycle)

    Both have the same:
    - Number of transitions: n - 1
    - Number of distinct edges: n - 1

    Expected outcome:
    - P1(one_way) > P1(loop)
    - P2(one_way) > P2(loop)

    Any detector that equates these is not measuring irreversibility.
    """
    n_states = 10
    seed = 42

    # Build trajectories
    one_way = builders.one_way_path(n_states=n_states, seed=seed)
    loop = builders.closed_loop(n_states=n_states, seed=seed)

    # Score both
    p1_one_way = p1_kl.score(one_way, alpha=1.0)
    p1_loop = p1_kl.score(loop, alpha=1.0)

    p2_one_way = p2_flux.score(one_way, aggregation="l1")
    p2_loop = p2_flux.score(loop, aggregation="l1")

    # Verify strict inequality
    assert p1_one_way > p1_loop, (
        f"P1: one_way ({p1_one_way:.6f}) must be > loop ({p1_loop:.6f})"
    )
    assert p2_one_way > p2_loop, (
        f"P2: one_way ({p2_one_way:.6f}) must be > loop ({p2_loop:.6f})"
    )

    # Log results
    print(f"\n[TEST 1: One-way vs Loop]")
    print(f"  n_states={n_states}, seed={seed}")
    print(f"  P1 — one_way: {p1_one_way:.6f}, loop: {p1_loop:.6f} (diff: {p1_one_way - p1_loop:.6f})")
    print(f"  P2 — one_way: {p2_one_way:.6f}, loop: {p2_loop:.6f} (diff: {p2_one_way - p2_loop:.6f})")
    print(f"  ✓ PASS: one_way_path scores strictly higher than closed_loop (both estimators)")

    return {
        "p1_one_way": p1_one_way,
        "p1_loop": p1_loop,
        "p2_one_way": p2_one_way,
        "p2_loop": p2_loop,
    }


# =============================================================================
# Test 2: NESS anchor (constant entropy, nonzero irreversibility)
# =============================================================================


def test_ness_anchor():
    """
    Test 2: NESS (nonequilibrium steady state) validation.

    A 3-state cycle with constant occupation probabilities but nonzero
    net cycle flux (detailed balance violated).

    Expected outcomes:
    1. Shannon entropy rate ≈ 0 (occupation not drifting)
    2. P1 > 0 (forward and reverse distributions diverge)
    3. P2 > 0 (net flux on cycle edges)

    This anchors the interpretation: P1/P2 measure asymmetry (flux),
    not entropy. A detector that fires on entropy alone would be wrong.
    """
    seed = 42

    # Build NESS chain
    traj, metadata = builders.ness_chain(seed=seed)

    # Measure Shannon entropy rate
    entropy_rate = builders.shannon_entropy_rate(traj, window_size=50)

    # Score irreversibility
    p1_score = p1_kl.score(traj, alpha=1.0)
    p2_score = p2_flux.score(traj, aggregation="l1")

    # Thresholds
    entropy_rate_tolerance = 0.15  # |dH/dt| < 0.15 nats/transition
    p1_min = 0.1  # P1 must be clearly positive
    p2_min = 0.05  # P2 must be clearly positive

    # Verify
    assert abs(entropy_rate) < entropy_rate_tolerance, (
        f"Entropy rate {entropy_rate:.6f} exceeds tolerance {entropy_rate_tolerance}. "
        f"NESS chain not stationary."
    )
    assert p1_score > p1_min, (
        f"P1 score {p1_score:.6f} must exceed {p1_min} for irreversible NESS."
    )
    assert p2_score > p2_min, (
        f"P2 score {p2_score:.6f} must exceed {p2_min} for irreversible NESS."
    )

    # Log
    print(f"\n[TEST 2: NESS Anchor]")
    print(f"  Entropy rate: {entropy_rate:.6f} (tolerance: ±{entropy_rate_tolerance})")
    print(f"  P1 score: {p1_score:.6f} (threshold: > {p1_min})")
    print(f"  P2 score: {p2_score:.6f} (threshold: > {p2_min})")
    print(f"  Metadata: {metadata['description']}")
    print(f"  ✓ PASS: NESS chain exhibits zero entropy rate but nonzero irreversibility")

    return {
        "entropy_rate": entropy_rate,
        "p1_score": p1_score,
        "p2_score": p2_score,
        "entropy_rate_tolerance": entropy_rate_tolerance,
        "p1_threshold": p1_min,
        "p2_threshold": p2_min,
    }


# =============================================================================
# Test 3: Reversal and detailed balance
# =============================================================================


def test_reversal_detailed_balance():
    """
    Test 3a & 3b: Reversal symmetry and detailed-balance anchoring.

    3a — Reversal symmetry:
    For any trajectory, D_KL(f || r) on the forward trajectory should equal
    D_KL(r || f) on the time-reversed trajectory (with forward/reverse swapped).

    Concretely:
    - Score forward: P1_fwd = D_KL(P_fwd || P_rev) on traj
    - Time-reverse the trajectory
    - Score reversed: P1_rev = D_KL(P_fwd' || P_rev') on time_reversed_traj
    - Expect: P1_fwd ≈ P1_rev (KL divergence is symmetric under argument swap
      when we swap the roles of forward/reverse)

    3b — Detailed-balance baseline:
    A chain satisfying detailed balance (every forward transition balanced by
    reverse with equal probability) should score ≈ 0 on both P1 and P2.

    Rationale: if the trajectory is sampled from a reversible process, the
    empirical forward and reverse distributions should be nearly identical,
    yielding low irreversibility scores.
    """

    # ===== Test 3a: Reversal directionality (non-vacuous) =====
    # NOTE (2026-07-02 correction): the original 3a scored a DETAILED-BALANCE chain in
    # both orientations and asserted the two were ~equal. On a reversible chain both
    # scores are ~0, so that assertion is VACUOUS — a symmetric-distance estimator that
    # cannot detect direction at all would also pass it. Rewritten to test the property
    # on an IRREVERSIBLE input, where a directional estimator must register irreversibility
    # regardless of orientation while a reversible input (3b) stays ~0.
    print(f"\n[TEST 3a: Reversal Directionality]")

    seed = 42
    one_way = builders.one_way_path(n_states=10, seed=seed)

    # score(traj) = D_KL(P_fwd || P_rev); score(time_reversed(traj)) = D_KL(P_rev || P_fwd)
    # (the reversed trajectory's forward edges ARE the original reverse edges). These are
    # the two KL directions — generally unequal for irreversible input — but BOTH must be
    # strongly positive, because a reversed one-way path is still one-way (still irreversible).
    p1_forward = p1_kl.score(one_way, alpha=1.0)
    p1_reversed = p1_kl.score(one_way.time_reversed(), alpha=1.0)

    directionality_floor = 0.1
    assert p1_forward > directionality_floor and p1_reversed > directionality_floor, (
        f"P1 must register irreversibility in BOTH orientations of a one-way path: "
        f"forward={p1_forward:.6f}, reversed={p1_reversed:.6f} (floor={directionality_floor})"
    )

    rel_diff = abs(p1_forward - p1_reversed) / max(abs(p1_forward), abs(p1_reversed), 1e-6)
    print(f"  P1(one-way forward):  {p1_forward:.6f}")
    print(f"  P1(one-way reversed): {p1_reversed:.6f}  (the two KL directions; equality NOT required)")
    print(f"  Both exceed directionality floor {directionality_floor} — non-vacuous PASS")

    # ===== Test 3b: Detailed-balance chain scores ~0 =====
    print(f"\n[TEST 3b: Detailed-Balance Baseline]")

    # Use a different seed to ensure independence
    seed_db = 99
    traj_db, metadata_db = builders.detailed_balance_chain(seed=seed_db)

    p1_db = p1_kl.score(traj_db, alpha=1.0)
    p2_db = p2_flux.score(traj_db, aggregation="l1")

    # Thresholds: reversible chain should score very low
    p1_db_threshold = 0.3  # Empirically, DB chains typically score < 0.1; allow 0.3 for noise
    p2_db_threshold = 0.3  # Same tolerance

    assert p1_db < p1_db_threshold, (
        f"P1 on detailed-balance chain {p1_db:.6f} exceeds threshold {p1_db_threshold}. "
        f"Detector too sensitive."
    )
    assert p2_db < p2_db_threshold, (
        f"P2 on detailed-balance chain {p2_db:.6f} exceeds threshold {p2_db_threshold}. "
        f"Detector too sensitive."
    )

    print(f"  Detailed-balance trajectory metadata:")
    print(f"    {metadata_db['description']}")
    print(f"  P1 score: {p1_db:.6f} (threshold: < {p1_db_threshold})")
    print(f"  P2 score: {p2_db:.6f} (threshold: < {p2_db_threshold})")
    print(f"  ✓ PASS: Reversible chain scores near zero")

    return {
        "p1_forward": p1_forward,
        "p1_reversed": p1_reversed,
        "p1_reversal_rel_diff": rel_diff,
        "p1_db": p1_db,
        "p2_db": p2_db,
    }


# =============================================================================
# Test 4: Estimator convergence (minimum trajectory length)
# =============================================================================


def test_estimator_convergence():
    """
    Test 4: P1/P2 score convergence vs trajectory length.

    Sweep trajectory length (e.g., 5, 10, 20, 40, 80, 160, 320, 640 transitions)
    on a known-asymmetry chain (NESS). Measure how P1/P2 vary and find the
    minimum length at which scores stabilize.

    Stability definition: across multiple seeds, the estimated score stays
    within X% of the long-run (length=640) value. We use coefficient of variation
    (σ/μ) as the primary metric.

    This test parameterizes the simulation horizon (§3.1): if estimates need
    > a few hundred transitions per actor to stabilize, the world needs
    longer simulation runs.

    Returns:
        - min_length: smallest length at which score stabilizes (return as int)
        - convergence_details: dict with per-length statistics
        - convergence_verdict: 'plausible_for_iam', 'kill_relevant_too_hungry', or 'inconclusive'
    """
    print(f"\n[TEST 4: Estimator Convergence]")

    # Configuration
    lengths = [5, 10, 20, 40, 80, 160, 320, 640]
    seeds = [100, 101, 102, 103, 104]  # 5 independent samples per length
    chain_spec = builders.ness_chain_spec()

    # Collect results: {length: [scores]}
    p1_scores_by_length = {length: [] for length in lengths}
    p2_scores_by_length = {length: [] for length in lengths}

    # Sample trajectories
    for length in lengths:
        for seed in seeds:
            traj = builders.variable_length_sampler(chain_spec, length=length, seed=seed)
            p1_score = p1_kl.score(traj, alpha=1.0)
            p2_score = p2_flux.score(traj, aggregation="l1")
            p1_scores_by_length[length].append(p1_score)
            p2_scores_by_length[length].append(p2_score)

    # Analyze convergence: compute mean, std, and CV (coefficient of variation)
    convergence_details = {}
    for length in lengths:
        p1_samples = p1_scores_by_length[length]
        p2_samples = p2_scores_by_length[length]

        p1_mean = statistics.mean(p1_samples)
        p1_std = statistics.stdev(p1_samples) if len(p1_samples) > 1 else 0.0
        p1_cv = p1_std / p1_mean if p1_mean > 0 else float('inf')

        p2_mean = statistics.mean(p2_samples)
        p2_std = statistics.stdev(p2_samples) if len(p2_samples) > 1 else 0.0
        p2_cv = p2_std / p2_mean if p2_mean > 0 else float('inf')

        convergence_details[length] = {
            "p1_mean": p1_mean,
            "p1_std": p1_std,
            "p1_cv": p1_cv,
            "p2_mean": p2_mean,
            "p2_std": p2_std,
            "p2_cv": p2_cv,
        }

        print(f"  Length={length:3d}: "
              f"P1={p1_mean:.4f}±{p1_std:.4f} (CV={p1_cv:.3f}), "
              f"P2={p2_mean:.4f}±{p2_std:.4f} (CV={p2_cv:.3f})")

    # Stability criterion: CV < 0.15 (i.e., std/mean < 15%) indicates convergence
    stability_threshold = 0.15
    min_length_p1 = None
    min_length_p2 = None

    for length in lengths:
        details = convergence_details[length]
        if details["p1_cv"] < stability_threshold and min_length_p1 is None:
            min_length_p1 = length
        if details["p2_cv"] < stability_threshold and min_length_p2 is None:
            min_length_p2 = length

    min_length = max([x for x in [min_length_p1, min_length_p2] if x is not None])

    if min_length is None:
        min_length = max(lengths)  # Fallback: use longest length tested
        verdict = "inconclusive"
        print(f"  ⚠ WARNING: No stable point found within tested lengths")
    elif min_length > 200:
        # IAM actor-window is typically ~tens to low hundreds of transitions
        # If we need > 200, that's pushing the boundary of feasibility
        verdict = "kill_relevant_too_hungry"
        print(f"  ⚠ CONCERN: Convergence at {min_length} transitions may exceed typical IAM window size (~50-200)")
    else:
        verdict = "plausible_for_iam"
        print(f"  ✓ Convergence at {min_length} transitions (plausible for IAM window)")

    print(f"  Stability threshold: CV < {stability_threshold:.1%}")
    print(f"  Min stable length (P1): {min_length_p1}, P2: {min_length_p2}")
    print(f"  Convergence verdict: {verdict}")

    return {
        "min_length": min_length,
        "min_length_p1": min_length_p1,
        "min_length_p2": min_length_p2,
        "convergence_details": convergence_details,
        "verdict": verdict,
        "stability_threshold": stability_threshold,
    }


# =============================================================================
# Test 5: Subsampling robustness
# =============================================================================


def test_subsampling_robustness():
    """
    Test 5: P1/P2 gracefully degrade under event loss.

    Simulate missing events (e.g., log loss, sampling) by uniformly dropping
    10%, 30%, 50% of transitions and re-scoring. Scores should degrade
    monotonically (smoothly) with increasing loss, not chaotically.

    Expected behavior:
    - More loss → lower scores (monotonic)
    - No sudden jumps or reversals (smooth degradation)
    - Detector remains responsive across loss levels

    Interpretation: if subsampling causes wild swings in scores, the detector
    is brittle to incomplete data — a realistic concern in production.
    """
    print(f"\n[TEST 5: Subsampling Robustness]")

    seed = 42
    dropout_rates = [0.0, 0.10, 0.30, 0.50]

    # Generate a long asymmetric trajectory
    ness_spec = builders.ness_chain_spec()
    traj_full = builders.variable_length_sampler(ness_spec, length=500, seed=seed)

    p1_scores = []
    p2_scores = []

    for dropout_rate in dropout_rates:
        if dropout_rate == 0.0:
            # Full trajectory
            traj_sample = traj_full
        else:
            # Randomly drop events
            random.seed(seed + dropout_rate)  # Deterministic seeding
            keep_count = int(len(traj_full) * (1.0 - dropout_rate))
            indices = sorted(random.sample(range(len(traj_full)), keep_count))
            dropped_traj = Trajectory([traj_full[i] for i in indices])
            traj_sample = dropped_traj

        p1_score = p1_kl.score(traj_sample, alpha=1.0)
        p2_score = p2_flux.score(traj_sample, aggregation="l1")

        p1_scores.append(p1_score)
        p2_scores.append(p2_score)

        print(f"  Dropout {dropout_rate:.0%}: P1={p1_score:.6f}, P2={p2_score:.6f}")

    # Check for monotonic degradation
    # Scores should be non-increasing (or at least not increasing too much)
    p1_monotonic = all(
        p1_scores[i] >= p1_scores[i + 1] * 0.95  # Allow 5% noise
        for i in range(len(p1_scores) - 1)
    )
    p2_monotonic = all(
        p2_scores[i] >= p2_scores[i + 1] * 0.95
        for i in range(len(p2_scores) - 1)
    )

    assert p1_monotonic, (
        f"P1 scores not monotonic under subsampling: {p1_scores}"
    )
    assert p2_monotonic, (
        f"P2 scores not monotonic under subsampling: {p2_scores}"
    )

    # Check that scores at least change (not entirely flat)
    p1_range = max(p1_scores) - min(p1_scores)
    p2_range = max(p2_scores) - min(p2_scores)

    assert p1_range > 0.01, f"P1 scores too flat: range={p1_range:.6f}"
    assert p2_range > 0.01, f"P2 scores too flat: range={p2_range:.6f}"

    print(f"  ✓ PASS: Scores degrade monotonically and responsively under event loss")
    print(f"    P1 range: {p1_range:.6f}, P2 range: {p2_range:.6f}")

    return {
        "dropout_rates": dropout_rates,
        "p1_scores": p1_scores,
        "p2_scores": p2_scores,
        "p1_monotonic": p1_monotonic,
        "p2_monotonic": p2_monotonic,
    }


# =============================================================================
# Main entry point
# =============================================================================


def run_all_tests() -> Dict:
    """
    Run all 5 mechanism tests and return a summary.

    Returns:
        dict with keys:
        - 'tests_1_3_pass': bool, whether tests 1–3 all passed (implementation check)
        - 'test_results': dict of per-test results
        - 'min_trajectory_length': int, minimum length for convergence (from test 4)
        - 'convergence_verdict': str, plausibility assessment
        - 'blocking_issues': list of strings, any blocking findings
    """
    results = {}
    blocking_issues = []

    # Test 1
    try:
        results["test_1_one_way_vs_loop"] = test_one_way_vs_loop()
        tests_1_3_pass = True
    except AssertionError as e:
        print(f"\n✗ TEST 1 FAILED: {e}")
        blocking_issues.append(f"Test 1 (one-way vs loop): {e}")
        tests_1_3_pass = False

    # Test 2
    try:
        results["test_2_ness_anchor"] = test_ness_anchor()
    except AssertionError as e:
        print(f"\n✗ TEST 2 FAILED: {e}")
        blocking_issues.append(f"Test 2 (NESS anchor): {e}")
        tests_1_3_pass = False

    # Test 3
    try:
        results["test_3_reversal_db"] = test_reversal_detailed_balance()
    except AssertionError as e:
        print(f"\n✗ TEST 3 FAILED: {e}")
        blocking_issues.append(f"Test 3 (reversal/detailed-balance): {e}")
        tests_1_3_pass = False

    # Test 4
    try:
        conv_results = test_estimator_convergence()
        results["test_4_convergence"] = conv_results
        min_length = conv_results["min_length"]
        verdict = conv_results["verdict"]
    except Exception as e:
        print(f"\n✗ TEST 4 ERROR: {e}")
        blocking_issues.append(f"Test 4 (convergence): {e}")
        min_length = -1
        verdict = "inconclusive"

    # Test 5
    try:
        results["test_5_subsampling"] = test_subsampling_robustness()
    except AssertionError as e:
        print(f"\n✗ TEST 5 FAILED: {e}")
        blocking_issues.append(f"Test 5 (subsampling): {e}")

    # Summary
    print("\n" + "=" * 70)
    print("MECHANISM TESTS SUMMARY")
    print("=" * 70)
    print(f"Tests 1–3 (implementation check): {'✓ PASS' if tests_1_3_pass else '✗ FAIL'}")
    print(f"Min trajectory length (test 4): {min_length}")
    print(f"Convergence verdict: {verdict}")
    print(f"Blocking issues: {len(blocking_issues)}")
    if blocking_issues:
        for issue in blocking_issues:
            print(f"  - {issue}")

    return {
        "tests_1_3_pass": tests_1_3_pass,
        "test_results": results,
        "min_trajectory_length": min_length,
        "convergence_verdict": verdict,
        "blocking_issues": blocking_issues,
    }


if __name__ == "__main__":
    summary = run_all_tests()
