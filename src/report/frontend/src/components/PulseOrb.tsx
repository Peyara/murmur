/** PulseOrb — D3 Canvas particle flow visualization.
 *
 * Particles flow between zones along bezier paths, driven by the flux matrix.
 * Color maps from residual_risk (teal -> amber -> coral).
 * Turbulence (sigma_coarse) displaces particles from their paths.
 * Transitions between windows are smoothly interpolated (~500ms lerp).
 */

import { useRef, useEffect } from 'react'
import { timer, type Timer, interpolateRgb } from 'd3'
import { riskToColor, COLORS } from '../lib/colors'
import { ZONE_POSITIONS, ZONE_ORDER, type ZoneName } from '../lib/constants'
import type { PulseResponse } from '../api/types'

interface Props {
  data: PulseResponse
  width: number
  height: number
}

interface Particle {
  sx: number; sy: number
  tx: number; ty: number
  cx: number; cy: number
  t: number
  speed: number
  color: string
  targetColor: string
  opacity: number
  targetOpacity: number
  radius: number
  targetRadius: number
}

// Animated state that lerps toward target values
interface AnimState {
  turbulence: number
  targetTurbulence: number
  risk: number
  targetRisk: number
  sigma: number
  targetSigma: number
  ringColor: string
  targetRingColor: string
  zoneRisk: Record<string, number>
  targetZoneRisk: Record<string, number>
}

function noise(x: number, y: number, seed: number): number {
  return Math.sin(x * 12.9898 + y * 78.233 + seed) * 0.5
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

const LERP_SPEED = 0.06 // ~30 frames to converge = ~500ms at 60fps

export default function PulseOrb({ data, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const timerRef = useRef<Timer | null>(null)
  const frameRef = useRef(0)
  const animRef = useRef<AnimState | null>(null)

  // Update targets when data changes — don't rebuild, just steer
  useEffect(() => {
    const zoneRisk: Record<string, number> = {}
    for (const actor of data.top_actors) {
      for (const zone of actor.zone_sequence) {
        zoneRisk[zone] = Math.max(zoneRisk[zone] ?? 0, actor.residual_risk)
      }
    }

    const targetTurbulence = Math.min(data.sigma_coarse * 5, 20)
    const targetRisk = data.max_residual
    const targetSigma = data.sigma_coarse
    const targetRingColor = riskToColor(targetRisk)

    if (!animRef.current) {
      // First mount — snap to values, no lerp
      animRef.current = {
        turbulence: targetTurbulence,
        targetTurbulence,
        risk: targetRisk,
        targetRisk,
        sigma: targetSigma,
        targetSigma,
        ringColor: targetRingColor,
        targetRingColor,
        zoneRisk: { ...zoneRisk },
        targetZoneRisk: zoneRisk,
      }
    } else {
      // Subsequent updates — set targets, let animation loop lerp
      animRef.current.targetTurbulence = targetTurbulence
      animRef.current.targetRisk = targetRisk
      animRef.current.targetSigma = targetSigma
      animRef.current.targetRingColor = targetRingColor
      animRef.current.targetZoneRisk = zoneRisk
    }

    // Update particle targets (color, opacity, radius lerp toward new values)
    const particles = particlesRef.current
    // Rebuild particles if flux matrix changed significantly
    rebuildParticles(particles, data, zoneRisk, width, height)

  }, [data, width, height])

  // Animation loop — recreated when size changes, reads animRef for smooth data transitions
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || width === 0 || height === 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    timerRef.current?.stop()

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)

    timerRef.current = timer(() => {
      frameRef.current++
      const frame = frameRef.current
      const anim = animRef.current
      if (!anim) return

      // Resize if needed
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr
        canvas.height = height * dpr
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.scale(dpr, dpr)
      }

      // Lerp animated state toward targets
      anim.turbulence = lerp(anim.turbulence, anim.targetTurbulence, LERP_SPEED)
      anim.risk = lerp(anim.risk, anim.targetRisk, LERP_SPEED)
      anim.sigma = lerp(anim.sigma, anim.targetSigma, LERP_SPEED)
      anim.ringColor = interpolateRgb(anim.ringColor, anim.targetRingColor)(LERP_SPEED)

      // Lerp zone risks
      for (const zone of ZONE_ORDER) {
        const target = anim.targetZoneRisk[zone] ?? 0
        const current = anim.zoneRisk[zone] ?? 0
        anim.zoneRisk[zone] = lerp(current, target, LERP_SPEED)
      }

      // Light background fill
      ctx.fillStyle = '#f0f2f5'
      ctx.fillRect(0, 0, width, height)

      // Zone labels — dark text on light bg
      ctx.font = '11px Inter, sans-serif'
      ctx.textAlign = 'center'
      for (const zone of ZONE_ORDER) {
        const pos = ZONE_POSITIONS[zone as ZoneName]
        if (!pos) continue
        const zr = anim.zoneRisk[zone] ?? 0
        ctx.fillStyle = zr > 0.3 ? riskToColor(zr) : '#94a3b8'
        ctx.globalAlpha = 0.9
        ctx.fillText(zone.replace('_', ' '), pos.x * width, pos.y * height + 4)
      }

      // Particles — lerp their visual properties
      const particles = particlesRef.current
      ctx.globalAlpha = 1
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i]!

        // Lerp color, opacity, radius toward targets
        p.color = interpolateRgb(p.color, p.targetColor)(LERP_SPEED)
        p.opacity = lerp(p.opacity, p.targetOpacity, LERP_SPEED)
        p.radius = lerp(p.radius, p.targetRadius, LERP_SPEED)

        p.t += p.speed
        if (p.t >= 1) { p.t = 0; continue }

        const t = p.t
        const mt = 1 - t
        let x = mt * mt * p.sx + 2 * mt * t * p.cx + t * t * p.tx
        let y = mt * mt * p.sy + 2 * mt * t * p.cy + t * t * p.ty

        if (anim.turbulence > 0.5) {
          x += noise(x * 0.01, frame * 0.02, i) * anim.turbulence
          y += noise(y * 0.01 + 100, frame * 0.02, i + 1000) * anim.turbulence
        }

        ctx.beginPath()
        ctx.arc(x, y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = p.color
        ctx.globalAlpha = p.opacity * (0.8 + 0.2 * Math.sin(frame * 0.03 + i))
        ctx.fill()
      }

      // Pulse rings — all driven by lerped values
      const { risk, sigma } = anim
      const baseRadius = 60 + risk * 80
      const breathAmp = 10 + sigma * 8
      const pulseSpeed = 0.015 + risk * 0.04
      const baseAlpha = 0.1 + risk * 0.3
      const lineW = 1.5 + risk * 3

      const pulseR = baseRadius + breathAmp * Math.sin(frame * pulseSpeed)
      ctx.globalAlpha = baseAlpha + 0.08 * Math.sin(frame * pulseSpeed)
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, pulseR, 0, Math.PI * 2)
      ctx.strokeStyle = anim.ringColor
      ctx.lineWidth = lineW
      ctx.stroke()

      const innerR = pulseR * (0.5 + risk * 0.15)
      ctx.globalAlpha = (baseAlpha * 0.6) + 0.04 * Math.sin(frame * pulseSpeed * 1.3 + 1)
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, innerR, 0, Math.PI * 2)
      ctx.lineWidth = lineW * 0.7
      ctx.stroke()

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

    return () => { timerRef.current?.stop() }
  }, [width, height])

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      className="block"
    />
  )
}

/** Rebuild particle array from flux matrix, preserving positions where possible. */
function rebuildParticles(
  particles: Particle[],
  data: PulseResponse,
  zoneRisk: Record<string, number>,
  width: number,
  height: number,
) {
  const newParticles: Particle[] = []
  const matrix = data.flux_matrix

  for (let si = 0; si < ZONE_ORDER.length; si++) {
    for (let ti = 0; ti < ZONE_ORDER.length; ti++) {
      if (si === ti) continue
      const flux = matrix[si]?.[ti] ?? 0
      if (flux <= 0) continue

      const count = Math.min(Math.ceil(flux * 0.5), 5)
      const srcZone = ZONE_ORDER[si]!
      const tgtZone = ZONE_ORDER[ti]!
      const srcPos = ZONE_POSITIONS[srcZone as ZoneName]
      const tgtPos = ZONE_POSITIONS[tgtZone as ZoneName]
      if (!srcPos || !tgtPos) continue

      const risk = Math.max(zoneRisk[srcZone] ?? 0, zoneRisk[tgtZone] ?? 0)
      const targetColor = risk > 0.1 ? riskToColor(risk) : COLORS.blue
      const targetOpacity = risk > 0.1 ? 0.7 + risk * 0.3 : 0.6
      const targetRadius = risk > 0.1 ? 2 + risk * 2.5 : 2.5

      for (let p = 0; p < count; p++) {
        const sx = srcPos.x * width
        const sy = srcPos.y * height
        const tx = tgtPos.x * width
        const ty = tgtPos.y * height
        const mx = (sx + tx) / 2
        const my = (sy + ty) / 2
        const dx = tx - sx
        const dy = ty - sy
        const offset = (Math.random() - 0.5) * 60

        newParticles.push({
          sx, sy, tx, ty,
          cx: mx - dy * 0.3 + offset,
          cy: my + dx * 0.3 + offset,
          t: Math.random(),
          speed: 0.003 + Math.random() * 0.004,
          color: targetColor, // will lerp if reused
          targetColor,
          opacity: targetOpacity,
          targetOpacity,
          radius: targetRadius,
          targetRadius,
        })
      }
    }
  }

  // Ambient particles
  if (newParticles.length < 20) {
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
        newParticles.push({
          sx, sy, tx, ty,
          cx: mx + offset, cy: my + offset,
          t: Math.random(),
          speed: 0.001 + Math.random() * 0.002,
          color: COLORS.blue,
          targetColor: COLORS.blue,
          opacity: 0.5,
          targetOpacity: 0.5,
          radius: 2,
          targetRadius: 2,
        })
      }
    }
  }

  // Preserve existing particles' current visual state for smooth transition.
  // Reuse position/progress from old particles, set new targets.
  const minLen = Math.min(particles.length, newParticles.length)
  for (let i = 0; i < minLen; i++) {
    const old = particles[i]!
    const nw = newParticles[i]!
    // Keep current visual state, update paths and targets
    nw.t = old.t
    nw.color = old.color           // current color — will lerp to targetColor
    nw.opacity = old.opacity       // current opacity — will lerp
    nw.radius = old.radius         // current radius — will lerp
  }

  // Replace array contents
  particles.length = 0
  particles.push(...newParticles)
}
