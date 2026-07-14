import { useEffect, useRef, useState } from 'react'

export interface CountUpProps {
  value: number
  /** Animation duration in ms. */
  duration?: number
  /** Decimal places to render. */
  decimals?: number
  prefix?: string
  suffix?: string
  /** Use locale grouping (e.g. 1,234,567). */
  locale?: boolean
  className?: string
}

/**
 * Animates a number from 0 → value on mount (and whenever value changes) with
 * an ease-out curve. Respects prefers-reduced-motion by snapping to the value.
 */
export function CountUp({
  value,
  duration = 900,
  decimals = 0,
  prefix = '',
  suffix = '',
  locale = true,
  className,
}: CountUpProps) {
  const [display, setDisplay] = useState(0)
  const fromRef = useRef(0)
  const rafRef = useRef<number>()

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setDisplay(value)
      return
    }
    const from = fromRef.current
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const current = from + (value - from) * eased
      setDisplay(current)
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
      else fromRef.current = value
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      fromRef.current = value
    }
  }, [value, duration])

  const formatted = locale
    ? display.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : display.toFixed(decimals)

  return (
    <span className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  )
}
