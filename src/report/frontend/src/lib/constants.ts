/** Zone order, positions, and tier thresholds. */

export const ZONE_ORDER = ['CONTROL', 'IDENTITY', 'SECRET', 'DATA', 'COMPUTE', 'EXFIL_RISK'] as const
export type ZoneName = (typeof ZONE_ORDER)[number]

/** Fixed zone positions for the topology layout (normalized 0-1 coordinates). */
export const ZONE_POSITIONS: Record<ZoneName, { x: number; y: number }> = {
  CONTROL:    { x: 0.5, y: 0.08 },
  IDENTITY:   { x: 0.25, y: 0.35 },
  COMPUTE:    { x: 0.75, y: 0.35 },
  SECRET:     { x: 0.25, y: 0.65 },
  DATA:       { x: 0.75, y: 0.65 },
  EXFIL_RISK: { x: 0.5, y: 0.92 },
}

export const TIER_THRESHOLDS = {
  HIGH: 0.8,
  MEDIUM: 0.5,
  WATCH: 0.3,
} as const
