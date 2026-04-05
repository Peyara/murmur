/** Typed fetch functions for all Murmur API endpoints. */

import type {
  PulseResponse,
  ZonesResponse,
  ActorsResponse,
  AlertsResponse,
  TimelineResponse,
} from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json() as Promise<T>
}

export function fetchPulse(window?: string): Promise<PulseResponse> {
  const params = window ? `?window=${encodeURIComponent(window)}` : ''
  return get(`/pulse${params}`)
}

export function fetchZones(window?: string): Promise<ZonesResponse> {
  const params = window ? `?window=${encodeURIComponent(window)}` : ''
  return get(`/zones${params}`)
}

export function fetchActors(window?: string, zone?: string): Promise<ActorsResponse> {
  const p = new URLSearchParams()
  if (window) p.set('window', window)
  if (zone) p.set('zone', zone)
  const qs = p.toString()
  return get(`/actors${qs ? `?${qs}` : ''}`)
}

export function fetchAlerts(hours = 24): Promise<AlertsResponse> {
  return get(`/alerts?hours=${hours}`)
}

export function fetchTimeline(hours = 24, actor?: string): Promise<TimelineResponse> {
  const p = new URLSearchParams({ hours: String(hours) })
  if (actor) p.set('actor', actor)
  return get(`/timeline?${p.toString()}`)
}
