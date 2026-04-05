"""Murmur API — FastAPI server for the dashboard.

Read-only access to DuckDB. All endpoints return fat JSON responses
optimized for the dashboard views (Pulse, Flow Map).
"""

import json
from datetime import UTC, datetime, timedelta

import duckdb
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from config.settings import SETTINGS
from src.report.db import get_db, lifespan
from src.report.models import (
    ZONE_ORDER,
    ActorDetail,
    ActorsResponse,
    ActorSummary,
    AlertItem,
    AlertsResponse,
    AlertTier,
    PulseResponse,
    TimelinePoint,
    TimelineResponse,
    TrendPoint,
    ZoneConnection,
    ZoneNode,
    ZonesResponse,
)


def create_app(db_path: str | None = None) -> FastAPI:
    """Factory — allows tests to inject a custom db_path."""
    app = FastAPI(title="Murmur API", version="0.1.0", lifespan=lifespan)
    app.state.db_path = db_path or SETTINGS.db_path

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(_router)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Convert from fusion_raw scale (0-10) to residual_risk scale (0-1).
# Must stay in sync with frontend TIER_THRESHOLDS in lib/constants.ts.
_THRESHOLDS = {
    "HIGH": SETTINGS.alert_high_threshold / 10.0,
    "MEDIUM": SETTINGS.alert_med_threshold / 10.0,
    "WATCH": SETTINGS.watch_threshold / 10.0,
}


def _classify_tier(residual_risk: float) -> AlertTier:
    if residual_risk >= _THRESHOLDS["HIGH"]:
        return "HIGH"
    if residual_risk >= _THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    if residual_risk >= _THRESHOLDS["WATCH"]:
        return "WATCH"
    return "NORMAL"


def _parse_json(val: str | None, default=None):
    """Safely parse JSON VARCHAR columns from DuckDB."""
    if val is None:
        return default if default is not None else []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def _empty_flux() -> list[list[float]]:
    return [[0.0] * 6 for _ in range(6)]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_router = APIRouter(prefix="/api")


@_router.get("/pulse", response_model=PulseResponse)
def get_pulse(
    window: datetime | None = Query(None, description="Window timestamp; defaults to latest"),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """System health summary — everything the Pulse view needs."""

    # 1. Zone flux window (specific or latest)
    if window:
        zf = db.execute(
            "SELECT window_start, sigma_coarse, flux_matrix, bridge_count "
            "FROM zone_flux_windows WHERE window_start = ?",
            [window],
        ).fetchone()
    else:
        zf = db.execute(
            "SELECT window_start, sigma_coarse, flux_matrix, bridge_count "
            "FROM zone_flux_windows ORDER BY window_start DESC LIMIT 1"
        ).fetchone()

    if zf is None:
        return PulseResponse(
            status="NORMAL", window_start=None, sigma_coarse=0.0,
            bridge_count=0, flux_matrix=_empty_flux(),
            tier_counts={"HIGH": 0, "MEDIUM": 0, "WATCH": 0, "NORMAL": 0},
            avg_residual=0.0, max_residual=0.0, trend=[], top_actors=[],
            zone_names=ZONE_ORDER,
        )

    window_start, sigma_coarse, flux_json, bridge_count = zf
    flux_matrix = _parse_json(flux_json, _empty_flux())

    # 2. Tier counts for latest window
    tier_row = db.execute(
        "SELECT "
        "  COUNT(*) FILTER (WHERE residual_risk >= ?) as high_count, "
        "  COUNT(*) FILTER (WHERE residual_risk >= ? AND residual_risk < ?) as med_count, "
        "  COUNT(*) FILTER (WHERE residual_risk >= ? AND residual_risk < ?) as watch_count, "
        "  COUNT(*) FILTER (WHERE residual_risk < ?) as normal_count, "
        "  COALESCE(AVG(residual_risk), 0) as avg_risk, "
        "  COALESCE(MAX(residual_risk), 0) as max_risk "
        "FROM risk_scores WHERE window_start = ?",
        [
            _THRESHOLDS["HIGH"],
            _THRESHOLDS["MEDIUM"], _THRESHOLDS["HIGH"],
            _THRESHOLDS["WATCH"], _THRESHOLDS["MEDIUM"],
            _THRESHOLDS["WATCH"],
            window_start,
        ],
    ).fetchone()

    tier_counts = {
        "HIGH": tier_row[0], "MEDIUM": tier_row[1],
        "WATCH": tier_row[2], "NORMAL": tier_row[3],
    }
    avg_residual = float(tier_row[4])
    max_residual = float(tier_row[5])
    status = _classify_tier(max_residual)

    # 3. Trend — last 8 windows (2 hours)
    trend_cutoff = window_start - timedelta(hours=2)
    trend_rows = db.execute(
        "SELECT window_start, "
        "  COALESCE(AVG(residual_risk), 0), "
        "  COALESCE(MAX(residual_risk), 0), "
        "  COUNT(*) "
        "FROM risk_scores WHERE window_start >= ? "
        "GROUP BY window_start ORDER BY window_start",
        [trend_cutoff],
    ).fetchall()

    trend = [
        TrendPoint(
            window_start=r[0], avg_residual=float(r[1]),
            max_residual=float(r[2]), actor_count=r[3],
        )
        for r in trend_rows
    ]

    # 4. Top 10 actors in latest window
    actor_rows = db.execute(
        "SELECT rs.actor_id, rs.residual_risk, rs.fusion_raw, rs.inv_score, "
        "  rs.fired_invariants, rs.explanation, "
        "  aw.event_count, aw.provenance_level, aw.zone_sequence "
        "FROM risk_scores rs "
        "JOIN actor_windows aw "
        "  ON rs.window_start = aw.window_start AND rs.actor_id = aw.actor_id "
        "WHERE rs.window_start = ? "
        "ORDER BY rs.residual_risk DESC LIMIT 10",
        [window_start],
    ).fetchall()

    top_actors = [
        ActorSummary(
            actor_id=r[0], residual_risk=float(r[1]), fusion_raw=float(r[2]),
            inv_score=float(r[3]), fired_invariants=_parse_json(r[4]),
            explanation=r[5] or "", event_count=r[6],
            provenance_level=r[7] or "NONE", zone_sequence=_parse_json(r[8]),
        )
        for r in actor_rows
    ]

    return PulseResponse(
        status=status, window_start=window_start,
        sigma_coarse=float(sigma_coarse), bridge_count=bridge_count,
        flux_matrix=flux_matrix, tier_counts=tier_counts,
        avg_residual=avg_residual, max_residual=max_residual,
        trend=trend, top_actors=top_actors, zone_names=ZONE_ORDER,
    )


@_router.get("/zones", response_model=ZonesResponse)
def get_zones(
    window: datetime | None = Query(None, description="Window timestamp; defaults to latest"),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Zone topology — everything the Flow Map view needs."""

    # Resolve window
    if window is None:
        row = db.execute(
            "SELECT window_start FROM zone_flux_windows ORDER BY window_start DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return ZonesResponse(
                window_start=None, sigma_coarse=0.0, nodes=[], connections=[],
                flux_matrix=_empty_flux(), zone_order=ZONE_ORDER,
            )
        window = row[0]

    # Flux matrix
    zf = db.execute(
        "SELECT sigma_coarse, flux_matrix FROM zone_flux_windows WHERE window_start = ?",
        [window],
    ).fetchone()
    sigma_coarse = float(zf[0]) if zf else 0.0
    flux_matrix = _parse_json(zf[1], _empty_flux()) if zf else _empty_flux()

    # Per-zone event counts + max residual
    zone_rows = db.execute(
        "SELECT e.target_zone, COUNT(*) as cnt, "
        "  COALESCE(MAX(rs.residual_risk), 0) as max_risk "
        "FROM events e "
        "LEFT JOIN risk_scores rs "
        "  ON e.window_start = rs.window_start AND e.actor_id = rs.actor_id "
        "WHERE e.window_start = ? "
        "GROUP BY e.target_zone",
        [window],
    ).fetchall()

    zone_map = {r[0]: (r[1], float(r[2])) for r in zone_rows}
    nodes = [
        ZoneNode(id=z, event_count=zone_map.get(z, (0, 0.0))[0],
                 max_residual=zone_map.get(z, (0, 0.0))[1])
        for z in ZONE_ORDER
    ]

    # Connections — aggregate edges_window by (source, target)
    edge_rows = db.execute(
        "SELECT source_zone, target_zone, "
        "  LIST(DISTINCT actor_id) as actors, "
        "  SUM(edge_count) as total_flow, "
        "  MAX(is_new_30d::INT) as has_new "
        "FROM edges_window WHERE window_start = ? "
        "GROUP BY source_zone, target_zone",
        [window],
    ).fetchall()

    connections = [
        ZoneConnection(
            source=r[0], target=r[1],
            flux=float(r[3]), actors=r[2],
            has_new_edge=bool(r[4]),
        )
        for r in edge_rows
    ]

    return ZonesResponse(
        window_start=window, sigma_coarse=sigma_coarse,
        nodes=nodes, connections=connections,
        flux_matrix=flux_matrix, zone_order=ZONE_ORDER,
    )


@_router.get("/actors", response_model=ActorsResponse)
def get_actors(
    window: datetime | None = Query(None, description="Window timestamp; defaults to latest"),
    zone: str | None = Query(None, description="Filter by zone name"),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """All scored actors for a window, optionally filtered by zone."""

    # Resolve window
    if window is None:
        row = db.execute(
            "SELECT MAX(window_start) FROM risk_scores"
        ).fetchone()
        if row is None or row[0] is None:
            return ActorsResponse(window_start=None, actors=[])
        window = row[0]

    query = (
        "SELECT rs.actor_id, rs.window_start, rs.residual_risk, rs.fusion_raw, "
        "  rs.inv_score, rs.inv_count, rs.sigma_coarse, rs.novelty_score, "
        "  rs.bridge_new, rs.delta_f, rs.fired_invariants, rs.explanation, "
        "  aw.event_count, aw.provenance_level, aw.pattern_match_score, aw.zone_sequence "
        "FROM risk_scores rs "
        "JOIN actor_windows aw "
        "  ON rs.window_start = aw.window_start AND rs.actor_id = aw.actor_id "
        "WHERE rs.window_start = ? "
    )
    params: list = [window]

    if zone:
        query += "AND aw.zone_sequence LIKE ? "
        params.append(f'%"{zone}"%')

    query += "ORDER BY rs.residual_risk DESC LIMIT 100"

    rows = db.execute(query, params).fetchall()

    actors = [
        ActorDetail(
            actor_id=r[0], window_start=r[1], residual_risk=float(r[2]),
            fusion_raw=float(r[3]), inv_score=float(r[4]), inv_count=int(r[5]),
            sigma_coarse=float(r[6]), novelty_score=float(r[7]),
            bridge_new=int(r[8]), delta_f=float(r[9]),
            fired_invariants=_parse_json(r[10]), explanation=r[11] or "",
            event_count=r[12], provenance_level=r[13] or "NONE",
            pattern_match_score=float(r[14]), zone_sequence=_parse_json(r[15]),
            alert_tier=_classify_tier(float(r[2])),
        )
        for r in rows
    ]

    return ActorsResponse(window_start=window, actors=actors)


@_router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    hours: int = Query(24, ge=1, le=168, description="Lookback hours"),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Active alerts (residual_risk >= WATCH threshold) within lookback window."""

    # Use latest window as reference (data may have future timestamps from sandbox)
    ref = db.execute("SELECT MAX(window_start) FROM risk_scores").fetchone()
    ref_time = ref[0] if ref and ref[0] else datetime.now(tz=UTC)
    cutoff = ref_time - timedelta(hours=hours)

    rows = db.execute(
        "SELECT rs.window_start, rs.actor_id, rs.residual_risk, rs.fusion_raw, "
        "  rs.fired_invariants, rs.explanation, "
        "  aw.event_count, aw.provenance_level, aw.zone_sequence "
        "FROM risk_scores rs "
        "JOIN actor_windows aw "
        "  ON rs.window_start = aw.window_start AND rs.actor_id = aw.actor_id "
        "WHERE rs.residual_risk >= ? AND rs.window_start >= ? "
        "ORDER BY rs.residual_risk DESC, rs.window_start DESC "
        "LIMIT 500",
        [_THRESHOLDS["WATCH"], cutoff],
    ).fetchall()

    alerts = [
        AlertItem(
            window_start=r[0], actor_id=r[1], residual_risk=float(r[2]),
            fusion_raw=float(r[3]), fired_invariants=_parse_json(r[4]),
            explanation=r[5] or "", event_count=r[6],
            provenance_level=r[7] or "NONE", zone_sequence=_parse_json(r[8]),
            alert_tier=_classify_tier(float(r[2])),
        )
        for r in rows
    ]

    return AlertsResponse(alerts=alerts, total=len(alerts))


@_router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    hours: int = Query(24, ge=1, le=720, description="Lookback hours"),
    actor: str | None = Query(None, description="Filter by actor_id"),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Historical risk scores for time-lapse replay."""

    # Use latest window as reference (data may have future timestamps from sandbox)
    ref = db.execute("SELECT MAX(window_start) FROM risk_scores").fetchone()
    ref_time = ref[0] if ref and ref[0] else datetime.now(tz=UTC)
    cutoff = ref_time - timedelta(hours=hours)

    query = (
        "SELECT window_start, actor_id, residual_risk, fusion_raw, sigma_coarse "
        "FROM risk_scores WHERE window_start >= ? "
    )
    params: list = [cutoff]

    if actor:
        query += "AND actor_id = ? "
        params.append(actor)

    query += "ORDER BY window_start, actor_id LIMIT 2000"

    rows = db.execute(query, params).fetchall()

    points = [
        TimelinePoint(
            window_start=r[0], actor_id=r[1], residual_risk=float(r[2]),
            fusion_raw=float(r[3]), sigma_coarse=float(r[4]),
        )
        for r in rows
    ]

    return TimelineResponse(points=points, hours=hours)


@_router.get("/windows")
def get_windows(db: duckdb.DuckDBPyConnection = Depends(get_db)):
    """Lightweight list of available window timestamps for the scrubber."""
    rows = db.execute(
        "SELECT DISTINCT window_start FROM zone_flux_windows ORDER BY window_start"
    ).fetchall()
    return {"windows": [r[0].isoformat() for r in rows]}

