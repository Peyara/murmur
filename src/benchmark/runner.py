"""Benchmark runner — runs attack/benign scenarios through the full Murmur pipeline.

Each scenario runs in an isolated in-memory DuckDB. Results include per-(window, actor)
scores, fired invariants, and alert tier classifications.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb

from config.settings import SETTINGS
from src.ingest.fetch import SingleFileFetcher, fetch_and_ingest
from src.provenance.patterns import register_pattern
from src.provenance.residual import compute_residual_risk
from src.score.fusion import compute_fusion
from src.world.graph import compute_zone_flux
from src.world.window import compute_actor_windows, compute_edges

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent.parent / "sql" / "schema.sql"


@dataclass
class ActorResult:
    """Scoring result for a single (window, actor) pair."""

    window_start: datetime
    actor_id: str
    fusion_raw: float
    residual_risk: float
    inv_score: float
    fired_invariants: list[str]
    explanation: str
    sigma_coarse: float
    novelty_score: float
    bridge_new: int
    burst_per_min: float
    breadth_entropy: float
    zone_sequence: list[str]
    pattern_match_score: float
    alert_tier: str


@dataclass
class BenchmarkResult:
    """Full benchmark result for a scenario."""

    scenario_path: str
    actor_results: list[ActorResult] = field(default_factory=list)
    ingest_stats: dict = field(default_factory=dict)

    @property
    def max_residual(self) -> float:
        return max((r.residual_risk for r in self.actor_results), default=0.0)

    @property
    def mean_residual(self) -> float:
        if not self.actor_results:
            return 0.0
        return sum(r.residual_risk for r in self.actor_results) / len(self.actor_results)

    @property
    def all_fired_invariants(self) -> set[str]:
        result = set()
        for r in self.actor_results:
            result.update(r.fired_invariants)
        return result

    @property
    def max_alert_tier(self) -> str:
        tier_rank = {"NORMAL": 0, "WATCH": 1, "MEDIUM": 2, "HIGH": 3}
        if not self.actor_results:
            return "NORMAL"
        return max(self.actor_results, key=lambda r: tier_rank.get(r.alert_tier, 0)).alert_tier


def _classify_alert(residual_risk: float) -> str:
    """Classify residual_risk into alert tier using settings thresholds."""
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


def _create_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with all tables from schema.sql."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_PATH.read_text())
    return conn


def run_scenario(
    scenario_path: str,
    history_path: str | None = None,
    patterns: list[dict] | None = None,
    known_initiators: set[str] | None = None,
) -> BenchmarkResult:
    """Run a scenario JSONL through the full pipeline and return results.

    Args:
        scenario_path: Path to scenario JSONL file.
        history_path: Optional path to history JSONL (seeded before scenario for
                      invariants that need 30-day lookback).
        patterns: Optional list of pattern dicts to register. Each dict has keys:
                  name, description, initiator_type, expected_actors, expected_zones,
                  expected_window, rate_min, rate_max, expected_duration.
        known_initiators: Override known initiators set. Defaults to settings.
    """
    if known_initiators is None:
        known_initiators = SETTINGS.load_known_initiators()

    db = _create_db()
    try:
        # Seed history if provided (for invariants with 30-day lookback)
        if history_path:
            fetcher = SingleFileFetcher(history_path)
            fetch_and_ingest(db, fetcher, source_id="benchmark:history")
            # Window and score history so invariants can query it
            _window_all(db)

        # Register sanctioned patterns
        if patterns:
            for p in patterns:
                register_pattern(
                    db,
                    name=p["name"],
                    description=p.get("description", ""),
                    initiator_type=p.get("initiator_type", "SCHEDULED"),
                    expected_actors=p["expected_actors"],
                    expected_zones=p["expected_zones"],
                    expected_window=p.get("expected_window"),
                    rate_min=p.get("rate_min", 0),
                    rate_max=p.get("rate_max", 100),
                    expected_duration=p.get("expected_duration", 15),
                )

        # Record pre-scenario windows (history only) so we can filter results
        pre_windows = set()
        if history_path:
            pre_windows = {
                row[0]
                for row in db.execute("SELECT DISTINCT window_start FROM events").fetchall()
            }

        # Ingest scenario
        fetcher = SingleFileFetcher(scenario_path)
        ingest_stats = fetch_and_ingest(db, fetcher, source_id="benchmark:scenario")

        # Window all events (re-windows history too, but idempotent via ON CONFLICT)
        _window_all(db)

        # Score all (window, actor) pairs
        from src.provenance.patterns import list_patterns
        cached_patterns = list_patterns(db, include_inactive=False)

        pairs = db.execute(
            "SELECT window_start, actor_id FROM actor_windows ORDER BY window_start, actor_id"
        ).fetchall()

        actor_results = []
        for ws, actor_id in pairs:
            # Skip history-only windows when reporting results
            if ws in pre_windows:
                # Still score history so invariant lookback works
                compute_fusion(db, ws, actor_id, known_initiators)
                compute_residual_risk(
                    db, ws, actor_id, 0.0, known_initiators, SETTINGS,
                    cached_patterns=cached_patterns,
                )
                continue

            fusion_raw = compute_fusion(db, ws, actor_id, known_initiators)
            residual = compute_residual_risk(
                db, ws, actor_id, fusion_raw, known_initiators, SETTINGS,
                cached_patterns=cached_patterns,
            )

            # Read back full results
            row = db.execute(
                "SELECT inv_score, fired_invariants, explanation, "
                "sigma_coarse, novelty_score, bridge_new "
                "FROM risk_scores WHERE window_start = ? AND actor_id = ?",
                [ws, actor_id],
            ).fetchone()

            aw_row = db.execute(
                "SELECT burst_per_min, breadth_entropy, zone_sequence, "
                "pattern_match_score "
                "FROM actor_windows WHERE window_start = ? AND actor_id = ?",
                [ws, actor_id],
            ).fetchone()

            fired_raw = json.loads(row[1]) if row and row[1] else []
            fired_names = fired_raw if isinstance(fired_raw, list) else []

            actor_results.append(ActorResult(
                window_start=ws,
                actor_id=actor_id,
                fusion_raw=fusion_raw,
                residual_risk=residual,
                inv_score=row[0] if row else 0.0,
                fired_invariants=fired_names,
                explanation=row[2] if row else "",
                sigma_coarse=row[3] if row else 0.0,
                novelty_score=row[4] if row else 0.0,
                bridge_new=row[5] if row else 0,
                burst_per_min=aw_row[0] if aw_row else 0.0,
                breadth_entropy=aw_row[1] if aw_row else 0.0,
                zone_sequence=json.loads(aw_row[2]) if aw_row and aw_row[2] else [],
                pattern_match_score=aw_row[3] if aw_row and aw_row[3] else 0.0,
                alert_tier=_classify_alert(residual),
            ))

        return BenchmarkResult(
            scenario_path=scenario_path,
            actor_results=actor_results,
            ingest_stats=ingest_stats,
        )
    finally:
        db.close()


def _window_all(db: duckdb.DuckDBPyConnection) -> None:
    """Compute world model for all windows in the database."""
    windows = db.execute(
        "SELECT DISTINCT window_start FROM events ORDER BY window_start"
    ).fetchall()
    for (ws,) in windows:
        compute_actor_windows(db, ws)
        compute_edges(db, ws)
        compute_zone_flux(db, ws)


