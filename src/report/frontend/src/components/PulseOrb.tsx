/** PulseOrb — D3 Canvas particle flow visualization.
 *
 * Particles flow between zones along bezier paths, driven by the flux matrix.
 * Color maps from residual_risk (teal -> amber -> coral).
 * Turbulence (sigma_coarse) displaces particles from their paths.
 * Provenance-explained flows are ghosted (low opacity).
 */

import { useRef, useEffect } from 'react'
import { timer, type Timer } from 'd3'
import { riskToColor, COLORS } from '../lib/colors'
import { ZONE_POSITIONS, ZONE_ORDER, type ZoneName } from '../lib/constants'
import type { PulseResponse } from '../api/types'

interface Props {
  data: PulseResponse
  width: number
  height: number
}

interface Particle {
  // Path
  sx: number; sy: number  // source
  tx: number; ty: number  // target
  cx: number; cy: number  // control point (bezier)
  // State
  t: number               // progress [0, 1]
  speed: number           // progress per frame
  color: string
  opacity: number
  radius: number
}

// Simplified noise — fast, good enough for ambient feel
function noise(x: number, y: number, seed: number): number {
  return Math.sin(x * 12.9898 + y * 78.233 + seed) * 0.5
}

export default function PulseOrb({ data, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const timerRef = useRef<Timer | null>(null)
  const frameRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Scale for retina
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)

    const particles = particlesRef.current

    // Build zone risk map for coloring
    const zoneRisk: Record<string, number> = {}
    for (const actor of data.top_actors) {
      for (const zone of actor.zone_sequence) {
        zoneRisk[zone] = Math.max(zoneRisk[zone] ?? 0, actor.residual_risk)
      }
    }

    // Spawn particles from flux matrix
    const spawnParticles = () => {
      const matrix = data.flux_matrix
      for (let si = 0; si < ZONE_ORDER.length; si++) {
        for (let ti = 0; ti < ZONE_ORDER.length; ti++) {
          if (si === ti) continue
          const flux = matrix[si]?.[ti] ?? 0
          if (flux <= 0) continue

          // Spawn rate proportional to flux, capped
          const count = Math.min(Math.ceil(flux * 0.5), 5)
          const srcZone = ZONE_ORDER[si]!
          const tgtZone = ZONE_ORDER[ti]!
          const srcPos = ZONE_POSITIONS[srcZone as ZoneName]
          const tgtPos = ZONE_POSITIONS[tgtZone as ZoneName]
          if (!srcPos || !tgtPos) continue

          const risk = Math.max(zoneRisk[srcZone] ?? 0, zoneRisk[tgtZone] ?? 0)

          for (let p = 0; p < count; p++) {
            const sx = srcPos.x * width
            const sy = srcPos.y * height
            const tx = tgtPos.x * width
            const ty = tgtPos.y * height
            // Control point — offset perpendicular to line for curve
            const mx = (sx + tx) / 2
            const my = (sy + ty) / 2
            const dx = tx - sx
            const dy = ty - sy
            const offset = (Math.random() - 0.5) * 60
            const cx = mx - dy * 0.3 + offset
            const cy = my + dx * 0.3 + offset

            particles.push({
              sx, sy, tx, ty, cx, cy,
              t: Math.random(), // stagger start positions
              speed: 0.003 + Math.random() * 0.004,
              color: riskToColor(risk),
              opacity: risk > 0.1 ? 0.7 + risk * 0.3 : 0.35, // dimmed but visible in calm
              radius: 2 + risk * 2.5,
            })
          }
        }
      }
    }

    // Initial spawn
    particles.length = 0
    spawnParticles()

    // Ambient particles — always present so the system feels alive
    if (particles.length < 20) {
      for (let i = 0; i < 6; i++) {
        const src = ZONE_ORDER[i]!
        const tgt = ZONE_ORDER[(i + 1) % 6]!
        const srcPos = ZONE_POSITIONS[src as ZoneName]
        const tgtPos = ZONE_POSITIONS[tgt as ZoneName]
        if (!srcPos || !tgtPos) continue
        const sx = srcPos.x * width
        const sy = srcPos.y * height
        const tx = tgtPos.x * width
        const ty = tgtPos.y * height
        for (let p = 0; p < 3; p++) {
          const mx = (sx + tx) / 2
          const my = (sy + ty) / 2
          const offset = (Math.random() - 0.5) * 40
          particles.push({
            sx, sy, tx, ty,
            cx: mx + offset, cy: my + offset,
            t: Math.random(),
            speed: 0.001 + Math.random() * 0.002,
            color: COLORS.teal,
            opacity: 0.25,
            radius: 1.5,
          })
        }
      }
    }

    // Turbulence amplitude from sigma_coarse
    const turbulence = Math.min(data.sigma_coarse * 5, 20)

    // Animation loop
    timerRef.current = timer(() => {
      frameRef.current++
      const frame = frameRef.current

      ctx.clearRect(0, 0, width, height)

      // Draw zone labels
      ctx.font = '12px Inter, sans-serif'
      ctx.textAlign = 'center'
      for (const zone of ZONE_ORDER) {
        const pos = ZONE_POSITIONS[zone as ZoneName]
        if (!pos) continue
        const zr = zoneRisk[zone] ?? 0
        ctx.fillStyle = zr > 0.3 ? riskToColor(zr) : COLORS.teal
        ctx.globalAlpha = 0.7
        ctx.fillText(zone.replace('_', ' '), pos.x * width, pos.y * height + 4)
      }

      // Update and draw particles
      ctx.globalAlpha = 1
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i]!
        p.t += p.speed

        if (p.t >= 1) {
          // Respawn at start
          p.t = 0
          continue
        }

        // Quadratic bezier position
        const t = p.t
        const mt = 1 - t
        let x = mt * mt * p.sx + 2 * mt * t * p.cx + t * t * p.tx
        let y = mt * mt * p.sy + 2 * mt * t * p.cy + t * t * p.ty

        // Turbulence displacement
        if (turbulence > 0.5) {
          x += noise(x * 0.01, frame * 0.02, i) * turbulence
          y += noise(y * 0.01 + 100, frame * 0.02, i + 1000) * turbulence
        }

        // Draw
        ctx.beginPath()
        ctx.arc(x, y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = p.color
        ctx.globalAlpha = p.opacity * (0.8 + 0.2 * Math.sin(frame * 0.03 + i)) // subtle pulse
        ctx.fill()
      }

      // Global pulse rings — radius, speed, opacity, and color all driven by risk + sigma
      const risk = data.max_residual
      const sigma = data.sigma_coarse
      const ringColor = riskToColor(risk)

      // Calm: small, slow, dim. Attack: large, fast, bright.
      const baseRadius = 60 + risk * 80          // 60px calm -> 140px at max risk
      const breathAmp = 10 + sigma * 8            // 10px calm -> 50px+ at high sigma
      const pulseSpeed = 0.015 + risk * 0.04      // slow calm -> fast attack
      const baseAlpha = 0.1 + risk * 0.3          // dim calm -> bright attack
      const lineWidth = 1.5 + risk * 3            // thin calm -> thick attack

      // Outer ring
      const pulseR = baseRadius + breathAmp * Math.sin(frame * pulseSpeed)
      ctx.globalAlpha = baseAlpha + 0.08 * Math.sin(frame * pulseSpeed)
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, pulseR, 0, Math.PI * 2)
      ctx.strokeStyle = ringColor
      ctx.lineWidth = lineWidth
      ctx.stroke()

      // Inner ring — slightly offset phase for "breathing" effect
      const innerR = pulseR * (0.5 + risk * 0.15)
      ctx.globalAlpha = (baseAlpha * 0.6) + 0.04 * Math.sin(frame * pulseSpeed * 1.3 + 1)
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, innerR, 0, Math.PI * 2)
      ctx.lineWidth = lineWidth * 0.7
      ctx.stroke()

      // Third ring at high risk — alarm pulse
      if (risk > 0.5) {
        const alarmR = pulseR * 1.3 + 20 * Math.sin(frame * pulseSpeed * 2)
        ctx.globalAlpha = (risk - 0.5) * 0.4 * (0.5 + 0.5 * Math.sin(frame * pulseSpeed * 2.5))
        ctx.beginPath()
        ctx.arc(width / 2, height / 2, alarmR, 0, Math.PI * 2)
        ctx.lineWidth = 1
        ctx.stroke()
      }

      ctx.globalAlpha = 1
    })

    return () => {
      timerRef.current?.stop()
    }
  }, [data, width, height])

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      className="block"
    />
  )
}
