"""Sprint 2 methodological cleanup — attack trajectories embedded in benign baseline.

Companion to src/validation/robustness.py. The Sprint 2 attack-only harness
produced 0% fire rates for sigma_coarse, delta_f, closure_gap, and
orphaned_priv across the 50-trajectory grid. Three competing causes existed:

1. Methodological — physics signals require benign baseline to compute variance.
2. Architectural — signals genuinely don't activate on attack patterns.
3. Harness gap — robustness.py never called create_watch / try_close_watch.

This module addresses (1) by embedding each attack in benign worker +
scheduled-job traffic generated via TrajectoryComposer. It addresses (3) by
explicitly wiring create_watch / try_close_watch on every inserted event,
mirroring the production fetch_and_ingest path. With (1) and (3) controlled,
remaining 0% fire rates are attributable to (2).

Attack actor IDs are namespaced (`attack-{email}`) so attack and benign actor
pools are guaranteed disjoint. This sacrifices identity-reuse evasion testing
in exchange for clean attribution.
"""

from __future__ import annotations

import dataclasses
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb

from config.settings import SETTINGS
from src.ingest.dedup import insert_event
from src.ingest.parser import parse_audit_log
from src.ingest.provenance_ingest import enrich_provenance
from src.provenance.patterns import list_patterns
from src.provenance.residual import compute_residual_risk
from src.schema import CanonicalEvent
from src.score.closure import (
    create_watch,
    mine_candidate_pairs,
    promote_candidates,
    seed_pairs,
    try_close_watch,
)
from src.score.fusion import compute_fusion
from src.synthetic.composer import TrajectoryComposer
from src.validation.attack_generator import AttackParams, generate_attack
from src.validation.robustness import (
    SIGNAL_NAMES,
    TrajectoryResult,
    _classify,
    _gate_verdict,
    _per_axis_table,
    edge_cases,
    param_grid,
)
from src.world.graph import compute_zone_flux
from src.world.window import compute_actor_windows, compute_edges

SCHEMA_PATH = Path(__file__).parent.parent.parent / "sql" / "schema.sql"


# ---------------------------------------------------------------------------
# Benign baseline — composed once, parsed to CanonicalEvents, reused per run
# ---------------------------------------------------------------------------


def _generate_benign_canonical_events(
    seed: int,
    n_actors: int = 10,
    n_windows: int = 20,
) -> list[CanonicalEvent]:
    """Compose benign trajectory and parse to CanonicalEvents.

    attack_ratio=0 — pure benign workers + scheduler + background noise.
    Returns parsed + provenance-enriched CanonicalEvents ready for insert_event.
    """
    composer = TrajectoryComposer(
        actors=n_actors, windows=n_windows, attack_ratio=0.0, seed=seed,
    )
    raw_events = composer.compose()
    known = SETTINGS.load_known_initiators()
    out: list[CanonicalEvent] = []
    for raw in raw_events:
        try:
            event = parse_audit_log(raw)
            event = enrich_provenance(event, known)
            out.append(event)
        except (KeyError, ValueError):
            # Malformed synthetic events should never happen, but the parser
            # contract says they raise — skip rather than crash a 50-grid run.
            continue
    return out


def _namespace_attack_actors(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
    """Prefix attack actor_ids with `attack-` to guarantee disjoint pools."""
    return [
        dataclasses.replace(e, actor_id=f"attack-{e.actor_id}") for e in events
    ]


# ---------------------------------------------------------------------------
# Per-trajectory pipeline (attack embedded in baseline)
# ---------------------------------------------------------------------------


def run_trajectory_in_baseline(
    params: AttackParams,
    seed: int,
    baseline_events: list[CanonicalEvent],
    label: str = "",
) -> TrajectoryResult:
    """Score one attack trajectory embedded in pre-generated benign baseline.

    Caller supplies parsed baseline events (typically generated once and
    reused across the grid for cross-trajectory comparability).
    """
    attack_traj = generate_attack(params, seed)
    attack_events = _namespace_attack_actors(attack_traj.events)
    attack_actor_ids = {e.actor_id for e in attack_events}

    db = duckdb.connect(":memory:")
    try:
        db.execute(SCHEMA_PATH.read_text())
        seed_pairs(db)

        # Insert benign baseline first — establishes history, edges, watches.
        for e in baseline_events:
            if insert_event(db, e):
                create_watch(db, e)
                try_close_watch(db, e)

        # Insert attack events on top.
        for e in attack_events:
            if insert_event(db, e):
                create_watch(db, e)
                try_close_watch(db, e)

        # World model — score all windows that now exist (benign + attack).
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

        # Score everything; track attack-actor max separately.
        max_fusion = 0.0
        max_residual = 0.0
        for ws, actor_id in pairs:
            fusion_raw = compute_fusion(db, ws, actor_id, known)
            residual = compute_residual_risk(
                db, ws, actor_id, fusion_raw, known, SETTINGS,
                cached_patterns=cached_patterns,
            )
            if actor_id in attack_actor_ids:
                max_fusion = max(max_fusion, fusion_raw)
                max_residual = max(max_residual, residual)

        # Signal max per attack-actor windows only.
        if attack_actor_ids:
            placeholders = ",".join(["?"] * len(attack_actor_ids))
            rs_rows = db.execute(
                f"SELECT inv_score, novelty_score, sigma_coarse, bridge_new, "  # noqa: S608  # nosec B608
                f"delta_f, closure_ratio, orphaned_privilege "
                f"FROM risk_scores WHERE actor_id IN ({placeholders})",
                list(attack_actor_ids),
            ).fetchall()
        else:
            rs_rows = []

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
            n_events=len(attack_events),  # attack events only — that's the trajectory
            n_windows=len(ws_rows),
            fusion_raw_max=max_fusion,
            residual_risk_max=max_residual,
            detected=max_residual >= SETTINGS.watch_threshold / 10.0,
            alert_tier=_classify(max_residual),
            signal_max=signal_max,
            signal_fired=signal_fired,
            expected_signals=attack_traj.expected_signals,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Benign-only run for the false-positive floor
# ---------------------------------------------------------------------------


@dataclass
class BenignFloorResult:
    """Distribution of residual_risk across benign-only (window, actor) pairs.

    Used to bound recalibrated thresholds: WATCH must not sit below benign P95
    or recalibration trades FN for FP.
    """
    n_pairs: int
    residuals: list[float]
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    max_residual: float
    signal_fire_rate: dict[str, float]


def run_benign_only(seed: int) -> BenignFloorResult:
    """Score a benign-only run; return the residual_risk distribution."""
    baseline_events = _generate_benign_canonical_events(seed)
    db = duckdb.connect(":memory:")
    try:
        db.execute(SCHEMA_PATH.read_text())
        seed_pairs(db)
        for e in baseline_events:
            if insert_event(db, e):
                create_watch(db, e)
                try_close_watch(db, e)

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
        residuals: list[float] = []
        for ws, actor_id in pairs:
            fusion_raw = compute_fusion(db, ws, actor_id, known)
            residual = compute_residual_risk(
                db, ws, actor_id, fusion_raw, known, SETTINGS,
                cached_patterns=cached_patterns,
            )
            residuals.append(residual)

        rs_rows = db.execute(
            "SELECT inv_score, novelty_score, sigma_coarse, bridge_new, "
            "delta_f, closure_ratio, orphaned_privilege FROM risk_scores"
        ).fetchall()
        n = max(1, len(rs_rows))
        signal_fire = {
            "inv_score": sum(1 for r in rs_rows if (r[0] or 0) > 0) / n,
            "novelty_score": sum(1 for r in rs_rows if (r[1] or 0) > 0) / n,
            "sigma_coarse": sum(1 for r in rs_rows if (r[2] or 0) > 0) / n,
            "bridge_new": sum(1 for r in rs_rows if (r[3] or 0) > 0) / n,
            "delta_f": sum(1 for r in rs_rows if (r[4] or 0) > 0) / n,
            "closure_gap": sum(1 for r in rs_rows if r[5] is not None and r[5] < 1.0) / n,
            "orphaned_priv": sum(1 for r in rs_rows if (r[6] or 0) > 0) / n,
        }

        sorted_r = sorted(residuals) if residuals else [0.0]

        def pct(p: float) -> float:
            if not sorted_r:
                return 0.0
            idx = min(len(sorted_r) - 1, int(round((len(sorted_r) - 1) * p)))
            return sorted_r[idx]

        return BenignFloorResult(
            n_pairs=len(residuals),
            residuals=residuals,
            p50=pct(0.50),
            p75=pct(0.75),
            p90=pct(0.90),
            p95=pct(0.95),
            p99=pct(0.99),
            max_residual=max(sorted_r) if sorted_r else 0.0,
            signal_fire_rate=signal_fire,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Grid runner & recalibration
# ---------------------------------------------------------------------------


def run_grid_in_baseline(
    params_list: list[tuple[AttackParams, int]],
    baseline_seed: int,
    label_prefix: str = "grid",
) -> list[TrajectoryResult]:
    """Run all (params, seed) pairs against a fixed benign baseline.

    The same baseline_seed is used for every trajectory, eliminating
    baseline-variance as a confound in cross-trajectory comparison.
    """
    baseline_events = _generate_benign_canonical_events(baseline_seed)
    results: list[TrajectoryResult] = []
    for i, (p, s) in enumerate(params_list):
        try:
            results.append(
                run_trajectory_in_baseline(p, s, baseline_events, f"{label_prefix}:{i}")
            )
        except Exception as e:  # pragma: no cover — pipeline error path
            print(f"  trajectory {i} failed: {e}")
    return results


def run_edges_in_baseline(
    edges: list[tuple[AttackParams, int, str]],
    baseline_seed: int,
) -> list[TrajectoryResult]:
    """Same as run_grid_in_baseline but for the 5 hand-crafted edge cases."""
    baseline_events = _generate_benign_canonical_events(baseline_seed)
    results: list[TrajectoryResult] = []
    for p, s, lbl in edges:
        try:
            results.append(run_trajectory_in_baseline(p, s, baseline_events, lbl))
        except Exception as e:  # pragma: no cover
            print(f"  edge {lbl} failed: {e}")
    return results


@dataclass
class RecalibratedThresholds:
    """Thresholds derived from observed distributions, with safety bounds."""
    watch: float
    medium: float
    high: float
    source: str  # human-readable provenance string
    benign_p95: float  # the safety floor — WATCH must be >= this


def recalibrate_thresholds(
    grid_results: list[TrajectoryResult],
    benign_floor: BenignFloorResult,
) -> RecalibratedThresholds:
    """Compute WATCH/MEDIUM/HIGH from observed attack-in-benign distribution.

    WATCH = max(grid P75, benign P95) — must not sit below benign noise floor.
    MEDIUM = grid P90.
    HIGH = grid P95.

    If recalibrated WATCH equals benign_p95, the calibration is bound from
    below by FP risk and the report should flag this.
    """
    attack_residuals = sorted(r.residual_risk_max for r in grid_results)

    def pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, int(round((len(values) - 1) * p)))
        return values[idx]

    grid_p75 = pct(attack_residuals, 0.75)
    grid_p90 = pct(attack_residuals, 0.90)
    grid_p95 = pct(attack_residuals, 0.95)

    watch = max(grid_p75, benign_floor.p95)
    source = f"grid_p75={grid_p75:.3f}, benign_p95={benign_floor.p95:.3f}"
    return RecalibratedThresholds(
        watch=watch, medium=grid_p90, high=grid_p95,
        source=source, benign_p95=benign_floor.p95,
    )


# ---------------------------------------------------------------------------
# Aggregation & reporting
# ---------------------------------------------------------------------------


@dataclass
class BaselineRobustnessReport:
    """Combined report across mode A reproduction, mode B baseline, and recalibration."""
    grid_results_in_baseline: list[TrajectoryResult]
    edge_results_in_baseline: list[TrajectoryResult]
    benign_floor: BenignFloorResult
    recalibrated: RecalibratedThresholds
    detection_rate_in_baseline: float
    detection_rate_recalibrated: float
    blind_spots_in_baseline: list[TrajectoryResult]
    blind_spots_recalibrated: list[TrajectoryResult]
    rates_by_axis_in_baseline: dict[str, dict[str, float]] = field(default_factory=dict)
    rates_by_axis_recalibrated: dict[str, dict[str, float]] = field(default_factory=dict)
    signal_fire_rate_in_baseline: dict[str, float] = field(default_factory=dict)
    signal_mean_max_in_baseline: dict[str, float] = field(default_factory=dict)
    prediction_divergence: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# Sprint 2 — Baseline Embedding & Threshold Recalibration (run output)")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        n_grid = len(self.grid_results_in_baseline)
        n_edge = len(self.edge_results_in_baseline)
        lines.append(
            f"\nGrid trajectories (in baseline): **{n_grid}**  |  Edge cases (in baseline): **{n_edge}**"
        )
        lines.append(
            f"\nCurrent thresholds (residual_risk): WATCH ≥ {SETTINGS.watch_threshold/10:.2f}, "
            f"MEDIUM ≥ {SETTINGS.alert_med_threshold/10:.2f}, "
            f"HIGH ≥ {SETTINGS.alert_high_threshold/10:.2f}"
        )
        lines.append(
            f"\nRecalibrated: WATCH ≥ {self.recalibrated.watch:.3f}, "
            f"MEDIUM ≥ {self.recalibrated.medium:.3f}, "
            f"HIGH ≥ {self.recalibrated.high:.3f}  "
            f"_(source: {self.recalibrated.source})_"
        )

        lines.append("\n## Gate Summary\n")
        lines.append(
            f"- **Detection rate (current thresholds, attack-in-benign):** "
            f"{self.detection_rate_in_baseline*100:.1f}%"
        )
        lines.append(
            f"- **Detection rate (recalibrated thresholds, attack-in-benign):** "
            f"{self.detection_rate_recalibrated*100:.1f}%"
        )
        lines.append(
            f"- **Blind-spot count (current):** {len(self.blind_spots_in_baseline)}"
        )
        lines.append(
            f"- **Blind-spot count (recalibrated):** {len(self.blind_spots_recalibrated)}"
        )
        lines.append(
            f"- **Benign FP floor (P95 residual_risk on benign-only run):** "
            f"{self.benign_floor.p95:.3f}  "
            f"_(WATCH bound: {self.recalibrated.benign_p95:.3f})_"
        )

        lines.append("\n## Detection Rate by Parameter (attack-in-benign + recalibrated)\n")
        for axis, rates in self.rates_by_axis_recalibrated.items():
            lines.append(_per_axis_table(axis, rates))

        lines.append("\n## Signal Fire Rate (attack-in-benign)\n")
        lines.append("| Signal | Fire rate | Mean max activation | Benign-only fire rate |")
        lines.append("|--------|-----------|---------------------|------------------------|")
        for s in SIGNAL_NAMES:
            fr = self.signal_fire_rate_in_baseline.get(s, 0.0)
            mm = self.signal_mean_max_in_baseline.get(s, 0.0)
            bfr = self.benign_floor.signal_fire_rate.get(s, 0.0)
            lines.append(f"| {s} | {fr*100:.1f}% | {mm:.3f} | {bfr*100:.1f}% |")

        lines.append("\n## Benign-Only Residual Distribution\n")
        lines.append(f"- n=({self.benign_floor.n_pairs} (window, actor) pairs)")
        lines.append(f"- P50: {self.benign_floor.p50:.3f}")
        lines.append(f"- P75: {self.benign_floor.p75:.3f}")
        lines.append(f"- P90: {self.benign_floor.p90:.3f}")
        lines.append(f"- P95: {self.benign_floor.p95:.3f}")
        lines.append(f"- P99: {self.benign_floor.p99:.3f}")
        lines.append(f"- max: {self.benign_floor.max_residual:.3f}")

        lines.append("\n## Prediction Divergence\n")
        lines.append("| Signal | Predicted+Fired | Predicted+Silent | Unpredicted+Fired | Unpredicted+Silent |")
        lines.append("|--------|------------------|-------------------|--------------------|---------------------|")
        for s in SIGNAL_NAMES:
            d = self.prediction_divergence.get(s, {})
            lines.append(
                f"| {s} | {d.get('pred_fired_actually_fired', 0)} | "
                f"{d.get('pred_fired_actually_silent', 0)} | "
                f"{d.get('pred_silent_actually_fired', 0)} | "
                f"{d.get('pred_silent_actually_silent', 0)} |"
            )

        if self.blind_spots_recalibrated:
            lines.append("\n## Blind Spots — Trajectories Not Detected (recalibrated)\n")
            lines.append(
                "| Label | speed | spread | zone_path | evasion | closure | "
                "objective | residual_risk_max |"
            )
            lines.append(
                "|-------|-------|--------|-----------|---------|---------|"
                "-----------|--------------------|"
            )
            for r in self.blind_spots_recalibrated[:30]:
                p = r.params
                lines.append(
                    f"| {r.label} | {p.speed} | {p.spread} | {p.zone_path} | "
                    f"{p.evasion} | {p.closure} | {p.objective} | "
                    f"{r.residual_risk_max:.3f} |"
                )
            if len(self.blind_spots_recalibrated) > 30:
                rem = len(self.blind_spots_recalibrated) - 30
                lines.append(f"\n_(... {rem} more blind spots truncated)_")

        if self.edge_results_in_baseline:
            lines.append("\n## Edge Cases (attack-in-benign)\n")
            lines.append(
                "| Label | residual_risk_max | tier (current) | tier (recal) | "
                "n_events | signals fired |"
            )
            lines.append(
                "|-------|--------------------|-----------------|---------------|"
                "----------|----------------|"
            )
            for r in self.edge_results_in_baseline:
                fired = ",".join(s for s in SIGNAL_NAMES if r.signal_fired[s]) or "(none)"
                tier_recal = _classify_recal(r.residual_risk_max, self.recalibrated)
                lines.append(
                    f"| {r.label} | {r.residual_risk_max:.3f} | {r.alert_tier} | "
                    f"{tier_recal} | {r.n_events} | {fired} |"
                )

        verdict = _gate_verdict_recalibrated(
            self.detection_rate_recalibrated, self.rates_by_axis_recalibrated,
        )
        lines.append(f"\n## Provisional Gate Verdict (recalibrated): **{verdict}**")
        lines.append("")
        return "\n".join(lines)


def _classify_recal(r: float, t: RecalibratedThresholds) -> str:
    if r >= t.high:
        return "HIGH"
    if r >= t.medium:
        return "MEDIUM"
    if r >= t.watch:
        return "WATCH"
    return "NORMAL"


def _gate_verdict_recalibrated(
    rate: float,
    rates_by_axis: dict[str, dict[str, float]],
) -> str:
    has_zero_class = any(
        any(v == 0.0 for v in d.values()) for d in rates_by_axis.values()
    )
    if rate >= 0.80 and not has_zero_class:
        return "PASS"
    if rate >= 0.80 and has_zero_class:
        return "CLASS-WIPE (≥80% overall but a parameter class is 0%)"
    if rate >= 0.60:
        return "BORDERLINE"
    return "FAIL"


def aggregate_baseline_report(
    grid_results: list[TrajectoryResult],
    edge_results: list[TrajectoryResult],
    benign_floor: BenignFloorResult,
) -> BaselineRobustnessReport:
    """Aggregate grid + edges + benign floor into a unified report."""
    recal = recalibrate_thresholds(grid_results, benign_floor)

    detection_in_baseline = (
        sum(1 for r in grid_results if r.detected) / len(grid_results)
        if grid_results else 0.0
    )
    detection_recal = (
        sum(1 for r in grid_results if r.residual_risk_max >= recal.watch)
        / len(grid_results)
        if grid_results else 0.0
    )

    by_axes_in: dict[str, dict[str, list[bool]]] = {
        "speed": defaultdict(list),
        "spread": defaultdict(list),
        "zone_path": defaultdict(list),
        "evasion": defaultdict(list),
        "closure": defaultdict(list),
        "objective": defaultdict(list),
    }
    by_axes_recal: dict[str, dict[str, list[bool]]] = {
        "speed": defaultdict(list),
        "spread": defaultdict(list),
        "zone_path": defaultdict(list),
        "evasion": defaultdict(list),
        "closure": defaultdict(list),
        "objective": defaultdict(list),
    }
    for r in grid_results:
        for axis_name in by_axes_in:
            by_axes_in[axis_name][getattr(r.params, axis_name)].append(r.detected)
            by_axes_recal[axis_name][getattr(r.params, axis_name)].append(
                r.residual_risk_max >= recal.watch
            )

    def _rates(d: dict[str, list[bool]]) -> dict[str, float]:
        return {k: sum(v) / len(v) for k, v in d.items()}

    rates_in = {axis: _rates(by_axes_in[axis]) for axis in by_axes_in}
    rates_recal = {axis: _rates(by_axes_recal[axis]) for axis in by_axes_recal}

    n = max(1, len(grid_results))
    signal_fire = {
        s: sum(1 for r in grid_results if r.signal_fired[s]) / n
        for s in SIGNAL_NAMES
    }
    signal_mean = {
        s: statistics.mean(r.signal_max[s] for r in grid_results)
        if grid_results else 0.0
        for s in SIGNAL_NAMES
    }

    blind_in = [r for r in grid_results if not r.detected]
    blind_recal = [r for r in grid_results if r.residual_risk_max < recal.watch]

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

    return BaselineRobustnessReport(
        grid_results_in_baseline=grid_results,
        edge_results_in_baseline=edge_results,
        benign_floor=benign_floor,
        recalibrated=recal,
        detection_rate_in_baseline=detection_in_baseline,
        detection_rate_recalibrated=detection_recal,
        blind_spots_in_baseline=blind_in,
        blind_spots_recalibrated=blind_recal,
        rates_by_axis_in_baseline=rates_in,
        rates_by_axis_recalibrated=rates_recal,
        signal_fire_rate_in_baseline=signal_fire,
        signal_mean_max_in_baseline=signal_mean,
        prediction_divergence=pred_div,
    )


# Re-export the param_grid + edge_cases helpers so callers (CLI) can import
# from one place.
__all__ = [
    "BaselineRobustnessReport",
    "BenignFloorResult",
    "RecalibratedThresholds",
    "aggregate_baseline_report",
    "edge_cases",
    "param_grid",
    "recalibrate_thresholds",
    "run_benign_only",
    "run_edges_in_baseline",
    "run_grid_in_baseline",
    "run_trajectory_in_baseline",
]
