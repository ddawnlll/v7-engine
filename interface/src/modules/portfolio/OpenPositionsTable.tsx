import { DataTable } from '../../components/data/DataTable'
import { resolveTradeExecutionIdentity } from '../../lib/executionIdentity'
import { formatNumber, formatPercent, formatTime } from '../../lib/format'
import type { JsonRecord, OrderRow } from '../../lib/types'

export function OpenPositionsTable({ rows }: { rows: JsonRecord[] }) {
  return (
    <DataTable
      rows={rows}
      emptyMessage="No open positions are available for the selected profile scope right now."
      columns={[
        { key: 'symbol', header: 'Symbol' },
        { key: 'direction', header: 'Side' },
        {
          key: 'profile_id',
          header: 'Profile',
          cell: (_value, row) => String(resolveTradeExecutionIdentity(row as OrderRow).profile_id),
        },
        {
          key: 'execution_mode',
          header: 'Execution',
          cell: (_value, row) => {
            const identity = resolveTradeExecutionIdentity(row as OrderRow)
            return `${identity.execution_mode} · ${identity.origin}`
          },
        },
        {
          key: 'entry',
          header: 'Levels',
          cell: (_value, row) => (
            <span className="font-mono text-sm text-stone-700">
              {formatNumber(row.entry, 4)} / {formatNumber(row.sl, 4)} / {formatNumber(row.tp, 4)}
            </span>
          ),
        },
        {
          key: 'confidence',
          header: 'Confidence',
          cell: (value) => formatPercent(value, 0),
        },
        {
          key: 'open_timestamp',
          header: 'Opened',
          cell: (value) => formatTime(value),
        },
        {
          key: 'venue',
          header: 'Venue',
          cell: (_value, row) => String(resolveTradeExecutionIdentity(row as OrderRow).venue),
        },
      ]}
    />
  )
}
