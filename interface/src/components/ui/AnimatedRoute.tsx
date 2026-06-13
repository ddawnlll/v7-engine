import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

export function AnimatedRoute({ children }: { children: ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 18, filter: 'blur(10px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: -18, filter: 'blur(8px)' }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="grid"
    >
      {children}
    </motion.section>
  )
}
