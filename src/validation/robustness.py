"""Sprint 2 robustness harness — score attack trajectories from the strategy grid.

Mirrors src/validation/large_scale.py:_run_pipeline shape but:
- Uses generate_attack (CanonicalEvent direct injection) per sprint spec line 85,
  instead of generate_trajectory (raw audit log dicts via parser).
- Skips the role-discrimination (gap_ratio) metric — Sprint 2 measures
  detection_rate on attack-only trajectories, not attacker-vs-worker gap.
- Aggregates by attack-strategy axes (speed/spread/zone_path/evasion/closure/objective)
  instead of seeds/actors/ratios.

Per CLAUDE.md R&D discipline: this duplicates the per-trajectory pipeline
shared with large_scale.py. DRY refactor is deferred to a follow-up PR
after the gate verdict — refactoring while validating a hypothesis muddles
attribution.
"""

from __future__ import annotations

import itertools
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb

from config.settings import SETTINGS
from src.ingest.dedup import insert_event
from src.provenance.patterns import list_patterns
from src.provenance.residual import compute_residual_risk
from src.score.closure import mine_candidate_pairs, promote_candidates
from src.score.fusion import compute_fusion
from src.validation.attack_generator import (
    CLOSURES,
    EVASIONS,
    OBJECTIVES,
    SPEEDS,
    SPREADS,
    ZONE_PATHS,
    AttackParams,
    generate_attack,
)
from src.world.graph import compute_zone_flux
from src.world.window import compute_actor_windows, compute_edges

SCHEMA_PATH = Path(__file__).parent.parent.parent / "sql" / "schema.sql"

# Names we report on. These map to columns in risk_scores (closure_gap is
# derived as 1 - closure_ratio).
SIGNAL_NAMES: tuple[str, ...] = (
    "inv_score",
    "novelty_score",
    "sigma_coarse",
    "bridge_new",
    "delta_f",
    "closure_gap",
    "orphaned_priv",
)


@dataclass
class TrajectoryResult:
    params: AttackParams
    seed: int
    label: str
    n_events: int
    n_windows: int
    fusion_raw_max: float
    residual_risk_max: float
    detected: bool
    alert_tier: str  # NORMAL / WATCH / MEDIUM / HIGH
    signal_max: dict[str, float]
    signal_fired: dict[str, bool]
    expected_signals: list[str]


@dataclass
class RobustnessReport:
    results: list[TrajectoryResult]
    detection_rate_overall: float
    detection_rate_by_speed: dict[str, float]
    detection_rate_by_spread: dict[str, float]
    detection_rate_by_zone_path: dict[str, float]
    detection_rate_by_evasion: dict[str, float]
    detection_rate_by_closure: dict[str, float]
    detection_rate_by_objective: dict[str, float]
    signal_fire_rate: dict[str, float]
    signal_mean_max: dict[str, float]
    blind_spots: list[TrajectoryResult]
    prediction_divergence: dict[str, dict[str, int]]
    edge_cases: list[TrajectoryResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# Sprint 2 — Attack-Strategy Robustness Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        n_grid = len(self.results)
        n_edge = len(self.edge_cases)
        lines.append(f"\nGrid trajectories: **{n_grid}**  |  Edge cases: **{n_edge}**")
        lines.append(
            f"Thresholds (residual_risk): HIGH ≥ {SETTINGS.alert_high_threshold/10:.2f}, "
            f"MEDIUM ≥ {SETTINGS.alert_med_threshold/10:.2f}, "
            f"WATCH ≥ {SETTINGS.watch_threshold/10:.2f} "
            f"(scaled from settings.py [0,10] config)."
        )

        lines.append("\n## Gate Summary\n")
        lines.append(f"- **Overall detection rate:** {self.detection_rate_overall*100:.1f}%")
        lines.append(f"- **Blind-spot count (residual_risk < WATCH):** {len(self.blind_spots)}")
        verdict = _gate_verdict(self.detection_rate_overall, self)
        lines.append(f"- **Provisional gate verdict:** {verdict}")

        lines.append("\n## Detection Rate by Parameter\n")
        lines.append(_per_axis_table("speed", self.detection_rate_by_speed))
        lines.append(_per_axis_table("spread", self.detection_rate_by_spread))
        lines.append(_per_axis_table("zone_path", self.detection_rate_by_zone_path))
        lines.append(_per_axis_table("evasion", self.detection_rate_by_evasion))
        lines.append(_per_axis_table("closure", self.detection_rate_by_closure))
        lines.append(_per_axis_table("objective", self.detection_rate_by_objective))

        lines.append("\n## Signal Fire Rate (across grid)\n")
        lines.append("| Signal | Fire rate | Mean max activation |")
        lines.append("|--------|-----------|---------------------|")
        for s in SIGNAL_NAMES:
            fr = self.signal_fire_rate.get(s, 0.0)
            mm = self.signal_mean_max.get(s, 0.0)
            lines.append(f"| {s} | {fr*100:.1f}% | {mm:.3f} |")

        lines.append("\n## Prediction Divergence (confirmation-bias guard)\n")
        lines.append(
            "Per signal: how predictions in `expected_signals` lined up with what fired. "
            "Divergence is the finding — predictions were committed before observation."
        )
        lines.append(
            "\n| Signal | Predicted+Fired | Predicted+Silent | Unpredicted+Fired | Unpredicted+Silent |"
        )
        lines.append("|--------|------------------|-------------------|--------------------|---------------------|")
        for s in SIGNAL_NAMES:
            d = self.prediction_divergence.get(s, {})
            lines.append(
                f"| {s} | {d.get('pred_fired_actually_fired', 0)} | "
                f"{d.get('pred_fired_actually_silent', 0)} | "
                f"{d.get('pred_silent_actually_fired', 0)} | "
                f"{d.get('pred_silent_actually_silent', 0)} |"
            )

        if self.blind_spots:
            lines.append("\n## Blind Spots — Trajectories Not Detected\n")
            lines.append("| Label | speed | spread | zone_path | evasion | closure | objective | residual_risk_max |")
            lines.append("|-------|-------|--------|-----------|---------|---------|-----------|--------------------|")
            for r in self.blind_spots[:30]:
                p = r.params
                lines.append(
                    f"| {r.label} | {p.speed} | {p.spread} | {p.zone_path} | "
                    f"{p.evasion} | {p.closure} | {p.objective} | {r.residual_risk_max:.3f} |"
                )
            if len(self.blind_spots) > 30:
                lines.append(f"\n_(... {len(self.blind_spots) - 30} more blind spots truncated)_")

        if self.edge_cases:
            lines.append("\n## Edge Cases (hand-crafted blind-spot probes)\n")
            lines.append("| Label | residual_risk_max | tier | n_events | n_windows | signals fired |")
            lines.append("|-------|--------------------|------|----------|------------|----------------|")
            for r in self.edge_cases:
                fired = ",".join(s for s in SIGNAL_NAMES if r.signal_fired[s]) or "(none)"
                lines.append(
                    f"| {r.label} | {r.residual_risk_max:.3f} | {r.alert_tier} | "
                    f"{r.n_events} | {r.n_windows} | {fired} |"
                )

        lines.append("")
        return "\n".join(lines)


def _per_axis_table(axis: str, rates: dict[str, float]) -> str:
    out = [f"\n### By {axis}\n"]
    out.append(f"| {axis} | n | detection rate |")
    out.append("|---|---|---|")
    # Count by axis derived from results — passed through rates dict
    for k in sorted(rates):
        out.append(f"| {k} | — | {rates[k]*100:.1f}% |")
    return "\n".join(out)


def _gate_verdict(rate: float, report: RobustnessReport) -> str:
    """Apply the Sprint 2 gate decision table.

    PASS:    >=80% AND no class with 0%
    BORDERLINE: 60-80%
    FAIL:    <60%
    CLASS-WIPE: any single param class at 0% (overrides PASS, but not FAIL)
    """
    classes = (
        report.detection_rate_by_speed,
        report.detection_rate_by_spread,
        report.detection_rate_by_zone_path,
        report.detection_rate_by_evasion,
        report.detection_rate_by_closure,
        report.detection_rate_by_objective,
    )
    has_zero_class = any(any(v == 0.0 for v in d.values()) for d in classes)
    if rate >= 0.80 and not has_zero_class:
        return "PASS"
    if rate >= 0.80 and has_zero_class:
        return "CLASS-WIPE (≥80% overall but a parameter class is 0%)"
    if rate >= 0.60:
        return "BORDERLINE"
    return "FAIL"


def _classify(r: float) -> str:
    if r >= SETTINGS.alert_high_threshold / 10.0:
        return "HIGH"
    if r >= SETTINGS.alert_med_threshold / 10.0:
        return "MEDIUM"
    if r >= SETTINGS.watch_threshold / 10.0:
        return "WATCH"
    return "NORMAL"


def run_trajectory(params: AttackParams, seed: int, label: str = "") -> TrajectoryResult:
    """Generate one trajectory and score it through the full pipeline."""
    traj = generate_attack(params, seed)
    db = duckdb.connect(":memory:")
    try:
        db.execute(SCHEMA_PATH.read_text())
        for e in traj.events:
            insert_event(db, e)

        ws_rows = db.execute(
            "SELECT DISTINCT window_start FROM events ORDER BY window_start"
        ).fetchall()
        for (ws,) in ws_rows:
            compute_actor_windows(db, ws)
            compute_edges(db, ws)
            compute_zone_flux(db, ws)

        mine_candidate_pairs(db)
        promote_candidates(db)

        known = SETTINGS.load_known_initiators()
        cached_patterns = list_patterns(db, include_inactive=False)
        pairs = db.execute(
            "SELECT window_start, actor_id FROM actor_windows ORDER BY window_start"
        ).fetchall()

        max_fusion = 0.0
        max_residual = 0.0
        for ws, actor_id in pairs:
            fusion_raw = compute_fusion(db, ws, actor_id, known)
            residual = compute_residual_risk(
                db, ws, actor_id, fusion_raw, known, SETTINGS,
                cached_patterns=cached_patterns,
            )
            max_fusion = max(max_fusion, fusion_raw)
            max_residual = max(max_residual, residual)

        rs_rows = db.execute(
            "SELECT inv_score, novelty_score, sigma_coarse, bridge_new, delta_f, "
            "closure_ratio, orphaned_privilege FROM risk_scores"
        ).fetchall()
        signal_max = {s: 0.0 for s in SIGNAL_NAMES}
        for inv, nov, sig, bri, dF, clr, orp in rs_rows:
            signal_max["inv_score"] = max(signal_max["inv_score"], inv or 0.0)
            signal_max["novelty_score"] = max(signal_max["novelty_score"], nov or 0.0)
            signal_max["sigma_coarse"] = max(signal_max["sigma_coarse"], sig or 0.0)
            signal_max["bridge_new"] = max(signal_max["bridge_new"], float(bri or 0))
            signal_max["delta_f"] = max(signal_max["delta_f"], dF or 0.0)
            if clr is not None and clr < 1.0:
                signal_max["closure_gap"] = max(signal_max["closure_gap"], 1.0 - clr)
            signal_max["orphaned_priv"] = max(signal_max["orphaned_priv"], orp or 0.0)

        signal_fired = {k: v > 0 for k, v in signal_max.items()}

        return TrajectoryResult(
            params=params,
            seed=seed,
            label=label or f"seed={seed}",
            n_events=len(traj.events),
            n_windows=len(ws_rows),
            fusion_raw_max=max_fusion,
            residual_risk_max=max_residual,
            detected=max_residual >= SETTINGS.watch_threshold / 10.0,
            alert_tier=_classify(max_residual),
            signal_max=signal_max,
            signal_fired=signal_fired,
            expected_signals=traj.expected_signals,
        )
    finally:
        db.close()


def param_grid(grid_size: int = 50, seed: int = 0) -> list[tuple[AttackParams, int]]:
    """Stratified sample of the (speed × spread × zone_path × evasion) base grid.

    The 72 base combinations come from spec line 52. closure and objective
    are NOT in the base grid — randomized per sample for diversity.

    Stratification: every (speed, evasion) cell gets ≥1 sample (12 cells),
    remaining slots filled randomly. This guarantees no entire (speed, evasion)
    class is uncovered, satisfying the "no 0% class" requirement of the gate.
    """
    rng = random.Random(seed)  # noqa: S311  # nosec B311
    base = list(itertools.product(SPEEDS, SPREADS, ZONE_PATHS, EVASIONS))

    by_cell: dict[tuple[str, str], list[tuple[str, str, str, str]]] = defaultdict(list)
    for combo in base:
        by_cell[(combo[0], combo[3])].append(combo)

    sampled: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    # Pass 1: one per (speed, evasion) cell.
    for cell, combos in by_cell.items():
        c = rng.choice(combos)
        sampled.append(c)
        seen.add(c)

    # Pass 2: fill randomly to grid_size.
    remaining = [c for c in base if c not in seen]
    rng.shuffle(remaining)
    while len(sampled) < grid_size and remaining:
        sampled.append(remaining.pop())

    out: list[tuple[AttackParams, int]] = []
    for i, (spd, spr, zp, ev) in enumerate(sampled[:grid_size]):
        closure = rng.choice(list(CLOSURES))
        objective = rng.choice(list(OBJECTIVES))
        params = AttackParams(spd, spr, zp, ev, closure, objective)  # type: ignore[arg-type]
        out.append((params, seed + i + 1))
    return out


def edge_cases() -> list[tuple[AttackParams, int, str]]:
    """5 hand-crafted blind-spot probes from sprint spec lines 53-58."""
    return [
        (
            AttackParams("slow", "single_actor", "full_chain", "split_actions", "none", "key_exfil"),
            1001,
            "edge:slow_ratchet",
        ),
        (
            AttackParams("fast", "multi_actor", "indirect", "none", "none", "secret_access"),
            1002,
            "edge:multi_actor_convergence",
        ),
        (
            # full_chain + secret_access path skips EXFIL_RISK by template design.
            AttackParams("medium", "single_actor", "full_chain", "none", "none", "secret_access"),
            1003,
            "edge:exfil_avoiding",
        ),
        (
            AttackParams("medium", "single_actor", "indirect", "pattern_mimicry", "full", "secret_access"),
            1004,
            "edge:perfect_mimicry",
        ),
        (
            # Generator minimum is 2 events. Direct + secret_access is the closest
            # we get to the spec's "single-event attack" probe.
            AttackParams("fast", "single_actor", "direct", "none", "none", "secret_access"),
            1005,
            "edge:minimal_direct",
        ),
    ]


def run_grid(
    params_list: list[tuple[AttackParams, int]],
    parallel: int = 1,
    label_prefix: str = "grid",
) -> list[TrajectoryResult]:
    """Run all (params, seed) pairs and return per-trajectory results."""
    results: list[TrajectoryResult] = []
    if parallel > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(run_trajectory, p, s, f"{label_prefix}:{i}"): i
                for i, (p, s) in enumerate(params_list)
            }
            for f in as_completed(futures):
                try:
                    results.append(f.result())
                except Exception as e:  # pragma: no cover — pipeline error path
                    print(f"  trajectory failed: {e}")
    else:
        for i, (p, s) in enumerate(params_list):
            try:
                results.append(run_trajectory(p, s, f"{label_prefix}:{i}"))
            except Exception as e:  # pragma: no cover
                print(f"  trajectory {i} failed: {e}")
    return results


def aggregate(
    grid_results: list[TrajectoryResult],
    edge_results: list[TrajectoryResult] | None = None,
) -> RobustnessReport:
    """Aggregate per-trajectory results into a RobustnessReport."""
    edge_results = edge_results or []
    if not grid_results:
        return RobustnessReport(
            results=[],
            detection_rate_overall=0.0,
            detection_rate_by_speed={},
            detection_rate_by_spread={},
            detection_rate_by_zone_path={},
            detection_rate_by_evasion={},
            detection_rate_by_closure={},
            detection_rate_by_objective={},
            signal_fire_rate={},
            signal_mean_max={},
            blind_spots=[],
            prediction_divergence={},
            edge_cases=edge_results,
        )

    by_speed: dict[str, list[bool]] = defaultdict(list)
    by_spread: dict[str, list[bool]] = defaultdict(list)
    by_zone_path: dict[str, list[bool]] = defaultdict(list)
    by_evasion: dict[str, list[bool]] = defaultdict(list)
    by_closure: dict[str, list[bool]] = defaultdict(list)
    by_objective: dict[str, list[bool]] = defaultdict(list)

    for r in grid_results:
        by_speed[r.params.speed].append(r.detected)
        by_spread[r.params.spread].append(r.detected)
        by_zone_path[r.params.zone_path].append(r.detected)
        by_evasion[r.params.evasion].append(r.detected)
        by_closure[r.params.closure].append(r.detected)
        by_objective[r.params.objective].append(r.detected)

    def _rate(d: dict[str, list[bool]]) -> dict[str, float]:
        return {k: sum(v) / len(v) for k, v in d.items()}

    signal_fire = {
        s: sum(1 for r in grid_results if r.signal_fired[s]) / len(grid_results)
        for s in SIGNAL_NAMES
    }
    signal_mean_max = {
        s: statistics.mean(r.signal_max[s] for r in grid_results)
        for s in SIGNAL_NAMES
    }

    blind_spots = [r for r in grid_results if not r.detected]

    pred_div: dict[str, dict[str, int]] = {}
    for s in SIGNAL_NAMES:
        pf_af = sum(1 for r in grid_results if s in r.expected_signals and r.signal_fired[s])
        pf_as = sum(1 for r in grid_results if s in r.expected_signals and not r.signal_fired[s])
        ps_af = sum(1 for r in grid_results if s not in r.expected_signals and r.signal_fired[s])
        ps_as = sum(
            1 for r in grid_results if s not in r.expected_signals and not r.signal_fired[s]
        )
        pred_div[s] = {
            "pred_fired_actually_fired": pf_af,
            "pred_fired_actually_silent": pf_as,
            "pred_silent_actually_fired": ps_af,
            "pred_silent_actually_silent": ps_as,
        }

    return RobustnessReport(
        results=grid_results,
        detection_rate_overall=sum(1 for r in grid_results if r.detected) / len(grid_results),
        detection_rate_by_speed=_rate(by_speed),
        detection_rate_by_spread=_rate(by_spread),
        detection_rate_by_zone_path=_rate(by_zone_path),
        detection_rate_by_evasion=_rate(by_evasion),
        detection_rate_by_closure=_rate(by_closure),
        detection_rate_by_objective=_rate(by_objective),
        signal_fire_rate=signal_fire,
        signal_mean_max=signal_mean_max,
        blind_spots=blind_spots,
        prediction_divergence=pred_div,
        edge_cases=edge_results,
    )
