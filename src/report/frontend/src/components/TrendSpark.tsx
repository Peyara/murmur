/** Tiny sparkline showing recent risk trend (8 windows = 2 hours). */

import { useRef, useEffect } from 'react'
import { line, curveMonotoneX, scaleLinear } from 'd3'
import { riskToColor } from '../lib/colors'
import type { TrendPoint } from '../api/types'

interface Props {
  trend: TrendPoint[]
  maxRisk: number
  width?: number
  height?: number
}

export default function TrendSpark({ trend, maxRisk, width = 120, height = 32 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || trend.length < 2) return

    const svg = svgRef.current
    // Clear
    while (svg.firstChild) svg.removeChild(svg.firstChild)

    const x = scaleLinear().domain([0, trend.length - 1]).range([2, width - 2])
    const y = scaleLinear().domain([0, Math.max(0.1, maxRisk * 1.2)]).range([height - 2, 2])

    const pathGen = line<TrendPoint>()
      .x((_, i) => x(i))
      .y((d) => y(d.max_residual))
      .curve(curveMonotoneX)

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    path.setAttribute('d', pathGen(trend) ?? '')
    path.setAttribute('fill', 'none')
    path.setAttribute('stroke', riskToColor(maxRisk))
    path.setAttribute('stroke-width', '1.5')
    path.setAttribute('stroke-opacity', '0.7')
    svg.appendChild(path)

    // Dot on latest point
    const last = trend[trend.length - 1]!
    const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
    dot.setAttribute('cx', String(x(trend.length - 1)))
    dot.setAttribute('cy', String(y(last.max_residual)))
    dot.setAttribute('r', '2.5')
    dot.setAttribute('fill', riskToColor(maxRisk))
    svg.appendChild(dot)
  }, [trend, maxRisk, width, height])

  if (trend.length < 2) return null

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="opacity-60 hover:opacity-100 transition-opacity"
    />
  )
}
