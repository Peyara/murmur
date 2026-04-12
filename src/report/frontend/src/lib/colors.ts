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

// Palette — tuned for light background
export const COLORS = {
  bg: '#f8f9fb',
  navy: '#0d1b2a',
  steel: '#e2e5ea',
  slate: '#94a3b8',
  teal: '#0d9488',
  blue: '#3b82f6',
  blueSoft: '#93c5fd',
  amber: '#d97706',
  copper: '#c2410c',
  coral: '#dc2626',
  red: '#b91c1c',
} as const

// Tier -> color
export const TIER_COLORS: Record<AlertTier, string> = {
  NORMAL: COLORS.teal,
  WATCH: COLORS.amber,
  MEDIUM: COLORS.copper,
  HIGH: COLORS.coral,
}

// Continuous risk -> color interpolation (saturated for light bg)
const riskScale = [
  { t: 0, color: '#3b82f6' },        // calm blue
  { t: TIER_THRESHOLDS.WATCH, color: '#d97706' },  // amber
  { t: TIER_THRESHOLDS.MEDIUM, color: '#ea580c' },  // deep orange
  { t: TIER_THRESHOLDS.HIGH, color: '#dc2626' },    // red
  { t: 1.0, color: '#991b1b' },       // dark red
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
