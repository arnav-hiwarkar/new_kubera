import { useId } from 'react'
import { cn } from '@/lib/cn'

export interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  /** Stroke/fill color. Defaults to the current text color (use text-accent etc). */
  className?: string
  strokeWidth?: number
  /** Fill the area under the line with a soft gradient. */
  area?: boolean
}

/**
 * A tiny, dependency-free inline trend line. Colors follow `currentColor`, so
 * set a text color via className (e.g. text-accent). Renders nothing for <2 pts.
 */
export function Sparkline({
  data,
  width = 96,
  height = 28,
  className,
  strokeWidth = 2,
  area = true,
}: SparklineProps) {
  const id = useId()
  if (!data || data.length < 2) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const stepX = width / (data.length - 1)
  const pad = strokeWidth
  const usableH = height - pad * 2

  const points = data.map((d, i) => {
    const x = i * stepX
    const y = pad + usableH - ((d - min) / range) * usableH
    return [x, y] as const
  })

  const line = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const areaPath = `${line} L${width},${height} L0,${height} Z`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className={cn('overflow-visible text-accent', className)}
      preserveAspectRatio="none"
      aria-hidden
    >
      {area && (
        <>
          <defs>
            <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#spark-${id})`} />
        </>
      )}
      <path
        d={line}
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={strokeWidth} fill="currentColor" />
    </svg>
  )
}
