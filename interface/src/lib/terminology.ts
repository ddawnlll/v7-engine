import type { TerminologyMode } from './runtimeSettings'

export const terminologyMap = {
  net_r: {
    simplified: 'Total Profit Score',
    advanced: 'Net R',
    developer: 'net_r',
  },
  win_rate: {
    simplified: 'Trades Won (%)',
    advanced: 'Win Rate',
    developer: 'win_rate',
  },
  max_drawdown: {
    simplified: 'Biggest Loss Streak',
    advanced: 'Maximum Drawdown',
    developer: 'max_drawdown',
  },
  profit_factor: {
    simplified: 'Profit vs Loss Ratio',
    advanced: 'Profit Factor',
    developer: 'profit_factor',
  },
  realized_r: {
    simplified: 'Money Made/Lost on Trade',
    advanced: 'Realized R',
    developer: 'realized_r',
  },
  engine_thread: {
    simplified: 'Bot Running Status',
    advanced: 'Engine Thread',
    developer: 'thread_alive',
  },
  regime: {
    simplified: 'Market Condition',
    advanced: 'Market Regime',
    developer: 'snapshot.regime',
  },
  pending: {
    simplified: 'Waiting Jobs',
    advanced: 'Pending',
    developer: 'job_queue.pending',
  },
  running: {
    simplified: 'Active Jobs',
    advanced: 'Running',
    developer: 'job_queue.running',
  },
  completed: {
    simplified: 'Finished Jobs',
    advanced: 'Completed',
    developer: 'job_queue.completed',
  },
  failed: {
    simplified: 'Failed Jobs',
    advanced: 'Failed',
    developer: 'job_queue.failed',
  },
  open_positions: {
    simplified: 'Live Trades',
    advanced: 'Open Positions',
    developer: 'open_orders',
  },
  trades_shown: {
    simplified: 'Trades Shown',
    advanced: 'Trades Shown',
    developer: 'filtered_trades.length',
  },
  avg_hold: {
    simplified: 'Average Hold Time',
    advanced: 'Avg Hold',
    developer: 'avg_hold_minutes',
  },
  hold: {
    simplified: 'Hold Time',
    advanced: 'Hold',
    developer: 'holding_minutes',
  },
  queue: {
    simplified: 'Job Queue',
    advanced: 'Queue',
    developer: 'job_queue',
  },
  alerts: {
    simplified: 'Attention Items',
    advanced: 'Alerts',
    developer: 'derived_alerts',
  },
  generated_at: {
    simplified: 'Last Updated',
    advanced: 'Generated',
    developer: 'generated_at',
  },
} as const

export type TermKey = keyof typeof terminologyMap

export function resolveTerm(key: TermKey, mode: TerminologyMode) {
  if (!terminologyMap[key]) {
    return key
  }
  return terminologyMap[key][mode]
}
