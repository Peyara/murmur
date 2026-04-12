/** AuthMesh — Organic dot field visualization.
 *
 * Soft, round dots scattered naturally across the canvas.
 * Zone positions attract nearby dots (gravity wells).
 * Authorized connections: warm gray dot-trails flowing between zones (dense, calm).
 * Unauthorized connections: colored dot-trails materializing (the murmur).
 * Feels like stippling / pointillism — organic, breathing, natural.
 */

import { useRef, useEffect } from 'react'
import { timer, type Timer, interpolateRgb } from 'd3'
import { riskToColor, COLORS } from '../lib/colors'
import { ZONE_POSITIONS, ZONE_ORDER, type ZoneName } from '../lib/constants'
import type { ZonesResponse, ZoneConnection } from '../api/types'

interface Props {
  data: ZonesResponse
  width: number
  height: number
  onClickZone?: (zone: string) => void
  onClickConnection?: (conn: ZoneConnection) => void
}

interface Dot {
  x: number
  y: number
  baseRadius: number
  radius: number
  targetRadius: number
  color: string
  targetColor: string
  alpha: number
  targetAlpha: number
  phase: number       // individual pulse offset
  breathSpeed: number // subtle animation speed
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function dist(x1: number, y1: number, x2: number, y2: number): number {
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
}

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  if (len2 === 0) return dist(px, py, ax, ay)
  let t = ((px - ax) * dx + (py - ay) * dy) / len2
  t = Math.max(0, Math.min(1, t))
  return dist(px, py, ax + t * dx, ay + t * dy)
}

// Pseudo-random but deterministic placement
function seededRandom(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

const LERP_SPEED = 0.035
const BG_COLOR = '#f0f2f5'
const BASE_DOT_COLOR = '#d1d5db'
const AUTHORIZED_COLOR = '#94a3b8'

export default function AuthMesh({ data, width, height, onClickZone, onClickConnection }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const timerRef = useRef<Timer | null>(null)
  const dotsRef = useRef<Dot[]>([])
  const frameRef = useRef(0)
  const dataRef = useRef(data)

  // Update data without rebuilding dots
  useEffect(() => {
    dataRef.current = data
    updateDotTargets()
  }, [data])

  // Build dot field when size changes
  useEffect(() => {
    if (width === 0 || height === 0) return
    buildDots()
    updateDotTargets()
  }, [width, height])

  function buildDots() {
    const dots: Dot[] = []
    const count = Math.floor((width * height) / 280) // density: ~1 dot per 280px²

    for (let i = 0; i < count; i++) {
      // Organic placement with slight clustering
      const x = seededRandom(i * 2) * width
      const y = seededRandom(i * 2 + 1) * height
      const baseRadius = 1.5 + seededRandom(i * 3) * 1.5

      dots.push({
        x, y,
        baseRadius,
        radius: baseRadius,
        targetRadius: baseRadius,
        color: BASE_DOT_COLOR,
        targetColor: BASE_DOT_COLOR,
        alpha: 0.15 + seededRandom(i * 5) * 0.15,
        targetAlpha: 0.15,
        phase: seededRandom(i * 7) * Math.PI * 2,
        breathSpeed: 0.008 + seededRandom(i * 11) * 0.008,
      })
    }

    dotsRef.current = dots
  }

  function updateDotTargets() {
    const d = dataRef.current
    const dots = dotsRef.current
    if (dots.length === 0) return

    // Reset all dots to subtle background state
    for (const dot of dots) {
      dot.targetColor = BASE_DOT_COLOR
      dot.targetAlpha = 0.12 + seededRandom(dots.indexOf(dot) * 13) * 0.1
      dot.targetRadius = dot.baseRadius
    }

    // Zone gravity wells — dots near zones get brighter
    for (const zone of ZONE_ORDER) {
      const pos = ZONE_POSITIONS[zone as ZoneName]
      if (!pos) continue
      const zx = pos.x * width
      const zy = pos.y * height
      const node = d.nodes.find(n => n.id === zone)
      const active = node ? node.event_count > 0 : false

      for (const dot of dots) {
        const dd = dist(dot.x, dot.y, zx, zy)
        if (dd < 55) {
          const intensity = 1 - dd / 55
          if (active) {
            dot.targetColor = AUTHORIZED_COLOR
            dot.targetAlpha = Math.max(dot.targetAlpha, 0.25 + intensity * 0.45)
            dot.targetRadius = dot.baseRadius + intensity * 1.5
          } else {
            dot.targetAlpha = Math.max(dot.targetAlpha, 0.15 + intensity * 0.2)
          }
        }
      }
    }

    // Connection paths — dots along paths light up
    for (const conn of d.connections) {
      const srcPos = ZONE_POSITIONS[conn.source as ZoneName]
      const tgtPos = ZONE_POSITIONS[conn.target as ZoneName]
      if (!srcPos || !tgtPos) continue

      const sx = srcPos.x * width
      const sy = srcPos.y * height
      const tx = tgtPos.x * width
      const ty = tgtPos.y * height

      const pathRadius = conn.authorized ? 25 : 30
      const connColor = conn.authorized
        ? AUTHORIZED_COLOR
        : riskToColor(Math.min(1, conn.flux / 8))
      const baseAlpha = conn.authorized
        ? 0.25 + Math.min(0.35, conn.flux * 0.015)
        : 0.5 + Math.min(0.4, conn.flux * 0.025)

      for (const dot of dots) {
        const dd = distToSegment(dot.x, dot.y, sx, sy, tx, ty)
        if (dd < pathRadius) {
          const intensity = 1 - dd / pathRadius
          const newAlpha = baseAlpha * intensity

          if (newAlpha > dot.targetAlpha) {
            dot.targetColor = connColor
            dot.targetAlpha = newAlpha
            dot.targetRadius = dot.baseRadius + (conn.authorized ? 0.5 : 1.5) * intensity

            // Unauthorized: faster breathing (subtle agitation)
            if (!conn.authorized) {
              dot.breathSpeed = 0.025 + seededRandom(dots.indexOf(dot) * 17) * 0.02
            }
          }
        }
      }
    }
  }

  // Animation loop
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
      const dots = dotsRef.current
      const d = dataRef.current

      // Background
      ctx.fillStyle = BG_COLOR
      ctx.fillRect(0, 0, width, height)

      // Draw dots
      for (const dot of dots) {
        // Lerp toward targets
        dot.alpha = lerp(dot.alpha, dot.targetAlpha, LERP_SPEED)
        dot.radius = lerp(dot.radius, dot.targetRadius, LERP_SPEED)
        dot.color = interpolateRgb(dot.color, dot.targetColor)(LERP_SPEED)

        // Breathing animation
        const breath = 0.85 + 0.15 * Math.sin(frame * dot.breathSpeed + dot.phase)
        const alpha = dot.alpha * breath

        if (alpha < 0.03) continue

        ctx.beginPath()
        ctx.arc(dot.x, dot.y, dot.radius * breath, 0, Math.PI * 2)
        ctx.fillStyle = dot.color
        ctx.globalAlpha = alpha
        ctx.fill()
      }

      // Zone labels
      ctx.globalAlpha = 1
      for (const zone of ZONE_ORDER) {
        const pos = ZONE_POSITIONS[zone as ZoneName]
        if (!pos) continue
        const node = d.nodes.find(n => n.id === zone)
        const hasUnauth = d.connections.some(
          c => (c.source === zone || c.target === zone) && !c.authorized
        )
        const zx = pos.x * width
        const zy = pos.y * height

        // White circle backdrop
        ctx.beginPath()
        ctx.arc(zx, zy, 30, 0, Math.PI * 2)
        ctx.fillStyle = 'white'
        ctx.globalAlpha = 0.92
        ctx.fill()
        ctx.globalAlpha = 1
        ctx.strokeStyle = hasUnauth ? COLORS.coral : '#cbd5e1'
        ctx.lineWidth = hasUnauth ? 2 : 1
        ctx.stroke()

        // Zone name
        ctx.fillStyle = hasUnauth ? COLORS.coral : '#334155'
        ctx.font = '500 10px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(zone.replace('_', ' '), zx, zy - 2)

        // Event count
        if (node && node.event_count > 0) {
          ctx.fillStyle = '#94a3b8'
          ctx.font = '9px Inter, sans-serif'
          ctx.fillText(`${node.event_count} events`, zx, zy + 11)
        }
      }

      // Novel edge diamonds
      for (const conn of d.connections) {
        if (!conn.has_new_edge) continue
        const srcPos = ZONE_POSITIONS[conn.source as ZoneName]
        const tgtPos = ZONE_POSITIONS[conn.target as ZoneName]
        if (!srcPos || !tgtPos) continue

        const mx = (srcPos.x + tgtPos.x) / 2 * width
        const my = (srcPos.y + tgtPos.y) / 2 * height
        const size = 4 + 1.5 * Math.sin(frame * 0.04)

        ctx.globalAlpha = 0.85
        ctx.fillStyle = COLORS.coral
        ctx.beginPath()
        ctx.moveTo(mx, my - size)
        ctx.lineTo(mx + size, my)
        ctx.lineTo(mx, my + size)
        ctx.lineTo(mx - size, my)
        ctx.closePath()
        ctx.fill()
      }

      ctx.globalAlpha = 1
    })

    return () => { timerRef.current?.stop() }
  }, [width, height])

  // Click handling
  function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const d = dataRef.current

    for (const zone of ZONE_ORDER) {
      const pos = ZONE_POSITIONS[zone as ZoneName]
      if (!pos) continue
      if (dist(x, y, pos.x * width, pos.y * height) < 35) {
        onClickZone?.(zone)
        return
      }
    }

    for (const conn of d.connections) {
      const srcPos = ZONE_POSITIONS[conn.source as ZoneName]
      const tgtPos = ZONE_POSITIONS[conn.target as ZoneName]
      if (!srcPos || !tgtPos) continue
      if (distToSegment(x, y, srcPos.x * width, srcPos.y * height, tgtPos.x * width, tgtPos.y * height) < 25) {
        onClickConnection?.(conn)
        return
      }
    }
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height, cursor: 'pointer' }}
      className="block"
      onClick={handleClick}
    />
  )
}
