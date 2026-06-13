import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { CellContext } from '@tanstack/react-table'
import type { ReactNode } from 'react'

type ColumnSpec<T extends object> = {
  key: keyof T
  header: string
  cell?: (value: T[keyof T], row: T) => ReactNode
}

export function DataTable<T extends object>({
  rows,
  columns,
  emptyMessage,
}: {
  rows: T[]
  columns: ColumnSpec<T>[]
  emptyMessage: string
}) {
  const helper = createColumnHelper<T>()
  const table = useReactTable({
    data: rows,
    columns: columns.map((column) =>
      helper.accessor((row) => row[column.key], {
        id: String(column.key),
        header: () => column.header,
        cell: (info: CellContext<T, T[keyof T]>) =>
          column.cell
            ? column.cell(info.getValue() as T[keyof T], info.row.original)
            : String(info.getValue() ?? '--'),
      }),
    ),
    getCoreRowModel: getCoreRowModel(),
  })

  if (!rows.length) {
    return <div className="rounded-2xl border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500">{emptyMessage}</div>
  }

  return (
    <div className="grid gap-3">
      <div
        className="hidden gap-3 px-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500 lg:grid"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
      >
        {table.getHeaderGroups().map((headerGroup) =>
          headerGroup.headers.map((header) => (
            <span key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</span>
          )),
        )}
      </div>
      {table.getRowModel().rows.map((row) => (
        <div
          key={row.id}
          className="grid gap-3 rounded-2xl bg-white/80 px-4 py-4 text-sm text-stone-700 shadow-[0_12px_24px_rgba(71,53,29,0.05)] lg:grid-cols-1"
          style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
        >
          {row.getVisibleCells().map((cell) => (
            <span key={cell.id} className="min-w-0">
              {flexRender(cell.column.columnDef.cell, cell.getContext())}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}
