import { useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

/** Fades + lifts page content on route change for a smooth, app-like feel. */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation()
  return (
    <motion.div
      key={location.pathname}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      className="mx-auto w-full max-w-[1400px]"
    >
      {children}
    </motion.div>
  )
}
