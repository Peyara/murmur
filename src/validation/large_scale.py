"""Large-scale validation harness.

Generates N trajectories with varying parameters, runs each through the
full Murmur pipeline (generate → ingest → window → score), and collects
discrimination metrics. Each trajectory runs in an isolated in-memory DuckDB.
"""

import json
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb

from config.settings import SETTINGS
from src.ingest.fetch import SingleFileFetcher, fetch_and_ingest
from src.provenance.patterns import list_patterns
from src.provenance.residual import compute_residual_risk
from src.score.closure import mine_candidate_pairs, promote_candidates
from src.score.fusion import compute_fusion
from src.synthetic import generate_trajectory
from src.world.graph import compute_zone_flux
from src.world.window import compute_actor_windows, compute_edges

SCHEMA_PATH = Path(__file__).parent.parent.parent / "sql" / "schema.sql"


@dataclass
class RunMetrics:
    """Metrics extracted from a single trajectory run."""

    seed: int
    actors: int
    windows: int
    attack_ratio: float
    event_count: int
    attacker_count: int
    worker_count: int
    attacker_mean_residual: float
    worker_mean_residual: float
    gap_ratio: float  # percentage: (att - wrk) / wrk * 100
    fp_rate: float  # fraction of worker windows at MEDIUM+
    fn_rate: float  # fraction of attacker windows at NORMAL/WATCH
    alert_dist: dict[str, int]
    signal_activations: dict[str, float]


@dataclass
class SweepConfig:
    """Configuration for the parameter sweep."""

    seeds: range = field(default_factory=lambda: range(1, 101))
    actor_counts: list[int] = field(default_factory=lambda: [10, 20, 30])
    attack_ratios: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3])
    windows: int = 20

    def param_grid(self) -> list[dict]:
        grid = []
        for seed in self.seeds:
            for actors in self.actor_counts:
                for ratio in self.attack_ratios:
                    grid.append({
                        "seed": seed,
                        "actors": actors,
                        "windows": self.windows,
                        "attack_ratio": ratio,
                    })
        return grid


@dataclass
class ValidationReport:
    """Aggregated report across all runs."""

    total_runs: int
    total_events: int
    mean_gap: float
    std_gap: float
    worst_gap: float  # minimum gap = weakest discrimination
    best_gap: float
    median_gap: float
    mean_fp: float
    mean_fn: float
    gap_by_actors: dict[int, float]
    gap_by_attack_ratio: dict[float, float]
    signal_reliability: dict[str, float]
    signal_mean_activation: dict[str, float]
    runs: list[RunMetrics]

    def to_markdown(self) -> str:
        lines = []
        lines.append("# Large-Scale Validation Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("\n## Summary\n")
        lines.append(f"- **Total runs:** {self.total_runs}")
        lines.append(f"- **Total events processed:** {self.total_events:,}")
        lines.append(f"- **Mean gap:** {self.mean_gap:.1f}% (std: {self.std_gap:.1f}%)")
        lines.append(f"- **Median gap:** {self.median_gap:.1f}%")
        lines.append(f"- **Worst gap (min discrimination):** {self.worst_gap:.1f}%")
        lines.append(f"- **Best gap (max discrimination):** {self.best_gap:.1f}%")
        lines.append(f"- **Mean FP rate:** {self.mean_fp:.3f}")
        lines.append(f"- **Mean FN rate:** {self.mean_fn:.3f}")

        lines.append("\n## Parameter Sensitivity\n")
        lines.append("### By Actor Count\n")
        lines.append("| Actors | Mean Gap (%) |")
        lines.append("|--------|-------------|")
        for k in sorted(self.gap_by_actors):
            lines.append(f"| {k} | {self.gap_by_actors[k]:.1f} |")

        lines.append("\n### By Attack Ratio\n")
        lines.append("| Attack Ratio | Mean Gap (%) |")
        lines.append("|-------------|-------------|")
        for k in sorted(self.gap_by_attack_ratio):
            lines.append(f"| {k} | {self.gap_by_attack_ratio[k]:.1f} |")

        lines.append("\n## Signal Reliability\n")
        lines.append("Fraction of runs where each signal fires (activation > 0).\n")
        lines.append("| Signal | Reliability | Mean Activation |")
        lines.append("|--------|------------|-----------------|")
        for sig in sorted(self.signal_reliability):
            rel = self.signal_reliability[sig]
            act = self.signal_mean_activation.get(sig, 0.0)
            lines.append(f"| {sig} | {rel:.2f} | {act:.3f} |")

        lines.append("")
        return "\n".join(lines)


def _classify_alert(residual_risk: float) -> str:
    high_t = SETTINGS.alert_high_threshold / 10.0
    med_t = SETTINGS.alert_med_threshold / 10.0
    watch_t = SETTINGS.watch_threshold / 10.0
    if residual_risk >= high_t:
        return "HIGH"
    if residual_risk >= med_t:
        return "MEDIUM"
    if residual_risk >= watch_t:
        return "WATCH"
    return "NORMAL"


def _is_attacker(actor_id: str) -> bool:
    return actor_id.startswith("attacker-sa-")


def _is_worker(actor_id: str) -> bool:
    return actor_id.startswith("worker-sa-")


def run_single_trajectory(
    seed: int,
    actors: int,
    windows: int,
    attack_ratio: float,
) -> RunMetrics:
    """Generate one trajectory, run the full pipeline, extract metrics."""
    events = generate_trajectory(actors=actors, windows=windows, attack_ratio=attack_ratio, seed=seed)

    # Write to temp file for SingleFileFetcher
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")
        tmp_path = f.name

    try:
        return _run_pipeline(tmp_path, events, seed, actors, windows, attack_ratio)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _run_pipeline(
    jsonl_path: str,
    events: list[dict],
    seed: int,
    actors: int,
    windows: int,
    attack_ratio: float,
) -> RunMetrics:
    """Run the full pipeline in an isolated in-memory DB and extract metrics."""
    db = duckdb.connect(":memory:")
    db.execute(SCHEMA_PATH.read_text())

    try:
        # Ingest
        fetcher = SingleFileFetcher(jsonl_path)
        fetch_and_ingest(db, fetcher, source_id=f"validate:seed={seed}")

        # World model
        ws_rows = db.execute("SELECT DISTINCT window_start FROM events ORDER BY window_start").fetchall()
        for (ws,) in ws_rows:
            compute_actor_windows(db, ws)
            compute_edges(db, ws)
            compute_zone_flux(db, ws)

        # Closure discovery
        mine_candidate_pairs(db)
        promote_candidates(db)

        # Score
        known = SETTINGS.load_known_initiators()
        cached_patterns = list_patterns(db, include_inactive=False)
        pairs = db.execute("SELECT window_start, actor_id FROM actor_windows ORDER BY window_start").fetchall()

        residuals_by_actor: dict[str, list[float]] = defaultdict(list)
        alert_dist = {"HIGH": 0, "MEDIUM": 0, "WATCH": 0, "NORMAL": 0}

        for ws, actor_id in pairs:
            fusion_raw = compute_fusion(db, ws, actor_id, known)
            residual = compute_residual_risk(
                db, ws, actor_id, fusion_raw, known, SETTINGS,
                cached_patterns=cached_patterns,
            )
            residuals_by_actor[actor_id].append(residual)
            tier = _classify_alert(residual)
            alert_dist[tier] += 1

        # Compute per-role means
        attacker_residuals = []
        worker_residuals = []
        for actor_id, vals in residuals_by_actor.items():
            mean_r = statistics.mean(vals)
            if _is_attacker(actor_id):
                attacker_residuals.append(mean_r)
            elif _is_worker(actor_id):
                worker_residuals.append(mean_r)

        attacker_mean = statistics.mean(attacker_residuals) if attacker_residuals else 0.0
        worker_mean = statistics.mean(worker_residuals) if worker_residuals else 0.0

        # Gap ratio: how much higher attacker mean is vs worker mean (%)
        if worker_mean > 0:
            gap_ratio = (attacker_mean - worker_mean) / worker_mean * 100.0
        else:
            gap_ratio = 100.0 if attacker_mean > 0 else 0.0

        # FP rate: fraction of worker (window, actor) pairs at MEDIUM+
        worker_fp = 0
        worker_total = 0
        attacker_fn = 0
        attacker_total = 0
        for actor_id, vals in residuals_by_actor.items():
            for r in vals:
                tier = _classify_alert(r)
                if _is_worker(actor_id):
                    worker_total += 1
                    if tier in ("MEDIUM", "HIGH"):
                        worker_fp += 1
                elif _is_attacker(actor_id):
                    attacker_total += 1
                    if tier in ("NORMAL", "WATCH"):
                        attacker_fn += 1

        fp_rate = worker_fp / worker_total if worker_total > 0 else 0.0
        fn_rate = attacker_fn / attacker_total if attacker_total > 0 else 0.0

        # Signal activations: fraction of scored pairs where each signal > 0
        signal_sums = _compute_signal_activations(db)

        return RunMetrics(
            seed=seed,
            actors=actors,
            windows=windows,
            attack_ratio=attack_ratio,
            event_count=len(events),
            attacker_count=len(attacker_residuals),
            worker_count=len(worker_residuals),
            attacker_mean_residual=attacker_mean,
            worker_mean_residual=worker_mean,
            gap_ratio=gap_ratio,
            fp_rate=fp_rate,
            fn_rate=fn_rate,
            alert_dist=alert_dist,
            signal_activations=signal_sums,
        )
    finally:
        db.close()


def _compute_signal_activations(db: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Compute fraction of scored pairs where each signal is active (> 0)."""
    rows = db.execute(
        "SELECT inv_score, novelty_score, bridge_new, "
        "closure_ratio, orphaned_privilege "
        "FROM risk_scores"
    ).fetchall()

    if not rows:
        return {
            "inv_score": 0.0, "novelty_score": 0.0, "bridge_new": 0.0,
            "closure_gap": 0.0, "orphaned_priv": 0.0, "trigger_resolved": 0.0,
        }

    n = len(rows)
    inv_active = sum(1 for r in rows if r[0] > 0)
    novelty_active = sum(1 for r in rows if r[1] > 0)
    bridge_active = sum(1 for r in rows if r[2] > 0)
    # closure_gap = 1 - closure_ratio; active when closure_ratio < 1 (i.e., some watches exist)
    closure_active = sum(1 for r in rows if r[3] is not None and r[3] < 1.0)
    orphaned_active = sum(1 for r in rows if r[4] is not None and r[4] > 0)

    # Trigger resolution: from actor_windows
    trigger_rows = db.execute(
        "SELECT trigger_chain_resolved FROM actor_windows "
        "WHERE trigger_chain_resolved IS NOT NULL"
    ).fetchall()
    trigger_resolved = sum(1 for r in trigger_rows if r[0]) if trigger_rows else 0
    trigger_total = len(trigger_rows) if trigger_rows else 1

    return {
        "inv_score": inv_active / n,
        "novelty_score": novelty_active / n,
        "bridge_new": bridge_active / n,
        "closure_gap": closure_active / n,
        "orphaned_priv": orphaned_active / n,
        "trigger_resolved": trigger_resolved / trigger_total,
    }


def aggregate_report(runs: list[RunMetrics]) -> ValidationReport:
    """Aggregate metrics across all runs into a report."""
    gaps = [r.gap_ratio for r in runs]
    fps = [r.fp_rate for r in runs]
    fns = [r.fn_rate for r in runs]

    # Per-parameter breakdowns
    gap_by_actors: dict[int, list[float]] = defaultdict(list)
    gap_by_ratio: dict[float, list[float]] = defaultdict(list)
    for r in runs:
        gap_by_actors[r.actors].append(r.gap_ratio)
        gap_by_ratio[r.attack_ratio].append(r.gap_ratio)

    # Signal reliability: fraction of runs where signal activation > 0
    signal_keys = runs[0].signal_activations.keys() if runs else []
    reliability = {}
    mean_activation = {}
    for sig in signal_keys:
        vals = [r.signal_activations[sig] for r in runs]
        reliability[sig] = sum(1 for v in vals if v > 0) / len(vals)
        mean_activation[sig] = statistics.mean(vals)

    return ValidationReport(
        total_runs=len(runs),
        total_events=sum(r.event_count for r in runs),
        mean_gap=statistics.mean(gaps),
        std_gap=statistics.stdev(gaps) if len(gaps) > 1 else 0.0,
        worst_gap=min(gaps),
        best_gap=max(gaps),
        median_gap=statistics.median(gaps),
        mean_fp=statistics.mean(fps),
        mean_fn=statistics.mean(fns),
        gap_by_actors={k: statistics.mean(v) for k, v in gap_by_actors.items()},
        gap_by_attack_ratio={k: statistics.mean(v) for k, v in gap_by_ratio.items()},
        signal_reliability=reliability,
        signal_mean_activation=mean_activation,
        runs=runs,
    )
