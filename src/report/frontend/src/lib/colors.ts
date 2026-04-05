/** Color mapping — residual_risk to hex, tier to hex.
 *
 * Color semantics (from concept doc):
 *   Cool blue/teal = normal, authorized
 *   Amber/copper = elevated, warrants attention
 *   Coral/red = high alert
 *   Ghosted (low opacity) = provenance-explained
 */

import { interpolateRgb } from 'd3'
import { TIER_THRESHOLDS } from './constants'
import type { AlertTier } from '../api/types'

// Palette
export const COLORS = {
  bg: '#0a0e17',
  navy: '#0d1b2a',
  steel: '#1b2838',
  slate: '#2a3a4a',
  teal: '#2a8a7a',
  blue: '#4a9aca',
  blueSoft: '#1a3a5c',
  amber: '#d4a574',
  copper: '#c47a4a',
  coral: '#e85d5d',
  red: '#ff4444',
} as const

// Tier -> color
export const TIER_COLORS: Record<AlertTier, string> = {
  NORMAL: COLORS.teal,
  WATCH: COLORS.amber,
  MEDIUM: COLORS.copper,
  HIGH: COLORS.coral,
}

// Continuous risk -> color interpolation
const riskScale = [
  { t: 0, color: COLORS.teal },
  { t: TIER_THRESHOLDS.WATCH, color: COLORS.amber },
  { t: TIER_THRESHOLDS.MEDIUM, color: COLORS.copper },
  { t: TIER_THRESHOLDS.HIGH, color: COLORS.coral },
  { t: 1.0, color: COLORS.red },
]

export function riskToColor(risk: number): string {
  const clamped = Math.max(0, Math.min(1, risk))
  for (let i = 1; i < riskScale.length; i++) {
    const prev = riskScale[i - 1]!
    const curr = riskScale[i]!
    if (clamped <= curr.t) {
      const t = (clamped - prev.t) / (curr.t - prev.t)
      return interpolateRgb(prev.color, curr.color)(t)
    }
  }
  return COLORS.red
}
