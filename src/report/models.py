"""Pydantic response models for the Murmur API.

These models define the API contract. TypeScript types in the frontend
mirror these 1:1. Fat response models minimize round-trips — each view
loads from a single endpoint.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AlertTier = Literal["NORMAL", "WATCH", "MEDIUM", "HIGH"]

ZONE_ORDER = ["CONTROL", "IDENTITY", "SECRET", "DATA", "COMPUTE", "EXFIL_RISK"]


# --- Shared sub-models ---


class TrendPoint(BaseModel):
    window_start: datetime
    avg_residual: float
    max_residual: float
    actor_count: int


class ActorSummary(BaseModel):
    actor_id: str
    residual_risk: float
    fusion_raw: float
    inv_score: float
    fired_invariants: list[str]
    explanation: str
    event_count: int
    provenance_level: str
    zone_sequence: list[str]


# --- /api/pulse ---


class PulseResponse(BaseModel):
    status: AlertTier
    window_start: datetime | None
    sigma_coarse: float
    bridge_count: int
    flux_matrix: list[list[float]]
    tier_counts: dict[str, int]
    avg_residual: float
    max_residual: float
    trend: list[TrendPoint]
    top_actors: list[ActorSummary]
    zone_names: list[str]


# --- /api/zones ---


class ZoneNode(BaseModel):
    id: str
    event_count: int
    max_residual: float


class ZoneConnection(BaseModel):
    source: str
    target: str
    flux: float
    actors: list[str]
    has_new_edge: bool
    authorized: bool              # all contributing actors have provenance
    provenance_level: str         # strongest provenance of contributing actors
    pattern_match_avg: float      # avg pattern match score across actors


class ZonesResponse(BaseModel):
    window_start: datetime | None
    sigma_coarse: float
    nodes: list[ZoneNode]
    connections: list[ZoneConnection]
    flux_matrix: list[list[float]]
    zone_order: list[str]


# --- /api/actors ---


class ActorDetail(BaseModel):
    actor_id: str
    window_start: datetime
    residual_risk: float
    fusion_raw: float
    inv_score: float
    inv_count: int
    sigma_coarse: float
    novelty_score: float
    bridge_new: int
    delta_f: float
    fired_invariants: list[str]
    explanation: str
    event_count: int
    provenance_level: str
    pattern_match_score: float
    zone_sequence: list[str]
    alert_tier: AlertTier


class ActorsResponse(BaseModel):
    window_start: datetime | None
    actors: list[ActorDetail]


# --- /api/alerts ---


class AlertItem(BaseModel):
    window_start: datetime
    actor_id: str
    residual_risk: float
    fusion_raw: float
    fired_invariants: list[str]
    explanation: str
    event_count: int
    provenance_level: str
    zone_sequence: list[str]
    alert_tier: AlertTier


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
    total: int


# --- /api/timeline ---


class TimelinePoint(BaseModel):
    window_start: datetime
    actor_id: str
    residual_risk: float
    fusion_raw: float
    sigma_coarse: float


class TimelineResponse(BaseModel):
    points: list[TimelinePoint]
    hours: int


# --- /api/waterfall ---


class WaterfallEvent(BaseModel):
    event_id: str
    ts: datetime
    actor_id: str
    action_type: str
    target_zone: str
    target_id: str
    trigger_ref: str | None
    provenance_level: str
    provenance_source: str


class WaterfallLane(BaseModel):
    actor_id: str
    provenance_level: str
    pattern_match_score: float
    residual_risk: float
    fired_invariants: list[str]
    events: list[WaterfallEvent]


class WaterfallResponse(BaseModel):
    window_start: datetime | None
    lanes: list[WaterfallLane]
