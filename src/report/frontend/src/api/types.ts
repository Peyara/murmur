/** API response types — mirrors Pydantic models in src/report/models.py */

export type AlertTier = 'NORMAL' | 'WATCH' | 'MEDIUM' | 'HIGH'

export interface TrendPoint {
  window_start: string
  avg_residual: number
  max_residual: number
  actor_count: number
}

export interface ActorSummary {
  actor_id: string
  residual_risk: number
  fusion_raw: number
  inv_score: number
  fired_invariants: string[]
  explanation: string
  event_count: number
  provenance_level: string
  zone_sequence: string[]
}

export interface PulseResponse {
  status: AlertTier
  window_start: string | null
  sigma_coarse: number
  bridge_count: number
  flux_matrix: number[][]
  tier_counts: Record<string, number>
  avg_residual: number
  max_residual: number
  trend: TrendPoint[]
  top_actors: ActorSummary[]
  zone_names: string[]
}

export interface ZoneNode {
  id: string
  event_count: number
  max_residual: number
}

export interface ZoneConnection {
  source: string
  target: string
  flux: number
  actors: string[]
  has_new_edge: boolean
}

export interface ZonesResponse {
  window_start: string | null
  sigma_coarse: number
  nodes: ZoneNode[]
  connections: ZoneConnection[]
  flux_matrix: number[][]
  zone_order: string[]
}

export interface ActorDetail {
  actor_id: string
  window_start: string
  residual_risk: number
  fusion_raw: number
  inv_score: number
  inv_count: number
  sigma_coarse: number
  novelty_score: number
  bridge_new: number
  delta_f: number
  fired_invariants: string[]
  explanation: string
  event_count: number
  provenance_level: string
  pattern_match_score: number
  zone_sequence: string[]
  alert_tier: AlertTier
}

export interface ActorsResponse {
  window_start: string | null
  actors: ActorDetail[]
}

export interface AlertItem {
  window_start: string
  actor_id: string
  residual_risk: number
  fusion_raw: number
  fired_invariants: string[]
  explanation: string
  event_count: number
  provenance_level: string
  zone_sequence: string[]
  alert_tier: AlertTier
}

export interface AlertsResponse {
  alerts: AlertItem[]
  total: number
}

export interface TimelinePoint {
  window_start: string
  actor_id: string
  residual_risk: number
  fusion_raw: number
  sigma_coarse: number
}

export interface TimelineResponse {
  points: TimelinePoint[]
  hours: number
}
