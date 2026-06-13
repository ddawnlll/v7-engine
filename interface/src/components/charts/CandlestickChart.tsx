import { useMemo, useState } from 'react'

import { formatNumber } from '../../lib/format'
import type { JsonRecord } from '../../lib/types'

type CandlePoint = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

function parsePoint(point: JsonRecord, index: number): CandlePoint | null {
  const open = Number(point.open)
  const high = Number(point.high)
  const low = Number(point.low)
  const close = Number(point.close)
  if (![open, high, low, close].every(Number.isFinite)) return null

  return {
    time: String(point.open_time ?? point.timestamp ?? point.time ?? index),
    open,
    high,
    low,
    close,
    volume: Number(point.volume) || 0,
  }
}

export function CandlestickChart({
  rows,
  title,
  height = 360,
  theme = 'light',
  levels,
}: {
  rows: JsonRecord[]
  title: string
  height?: number
  theme?: 'light' | 'dark'
  levels?: {
    entry?: number | null
    zoneLow?: number | null
    zoneHigh?: number | null
    stopLoss?: number | null
    takeProfit?: number | null
  }
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const data = useMemo(() => rows.map(parsePoint).filter((item): item is CandlePoint => Boolean(item)), [rows])

  if (!data.length) {
    return (
      <div className="flex h-full min-h-[340px] items-center justify-center rounded-[1.5rem] bg-stone-950/[0.03] text-sm text-stone-500">
        Candle data will appear here once klines are available.
      </div>
    )
  }

  const width = 1000
  const svgHeight = Math.max(height + 60, 420)
  const left = 34
  const right = 22
  const top = 24
  const volumeHeight = Math.max(Math.round(height * 0.2), 72)
  const priceHeight = Math.max(height - volumeHeight - 34, 240)
  const volumeTop = top + priceHeight + 24
  const innerWidth = width - left - right
  const levelValues = [
    levels?.entry,
    levels?.zoneLow,
    levels?.zoneHigh,
    levels?.stopLoss,
    levels?.takeProfit,
  ].filter((value): value is number => Number.isFinite(value as number))
  const minLow = Math.min(...data.map((item) => item.low), ...(levelValues.length ? levelValues : [Number.POSITIVE_INFINITY]))
  const maxHigh = Math.max(...data.map((item) => item.high), ...(levelValues.length ? levelValues : [Number.NEGATIVE_INFINITY]))
  const maxVolume = Math.max(...data.map((item) => item.volume), 1)
  const priceRange = Math.max(maxHigh - minLow, 0.00001)
  const candleGap = innerWidth / data.length
  const candleWidth = Math.max(Math.min(candleGap * 0.62, 12), 4)
  const activeCandle = activeIndex == null ? data[data.length - 1] : data[activeIndex]
  const activeLabel = activeIndex == null ? 'Latest' : `Candle ${activeIndex + 1}`
  const dark = theme === 'dark'
  const gridStroke = dark ? 'rgba(255,255,255,0.10)' : 'rgba(87,83,78,0.12)'
  const axisText = dark ? '#d6d3d1' : '#78716c'
  const chartBg = dark
    ? 'bg-[linear-gradient(180deg,rgba(21,19,17,0.96),rgba(14,12,11,1))]'
    : 'bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(244,240,232,0.92))]'
  const panelBg = dark ? 'bg-white/4' : 'bg-stone-950/[0.03]'
  const chipBg = dark ? 'border-white/10 bg-white/6 text-stone-200' : 'border-stone-900/8 bg-white text-stone-700'

  const yForPrice = (price: number) => top + ((maxHigh - price) / priceRange) * priceHeight
  const yForVolume = (volume: number) => volumeTop + volumeHeight - (volume / maxVolume) * volumeHeight
  const levelRows = [
    { label: 'Zone Low', value: levels?.zoneLow, stroke: dark ? 'rgba(245,158,11,0.6)' : 'rgba(217,119,6,0.55)', dashed: true },
    { label: 'Zone High', value: levels?.zoneHigh, stroke: dark ? 'rgba(245,158,11,0.6)' : 'rgba(217,119,6,0.55)', dashed: true },
    { label: 'Entry', value: levels?.entry, stroke: dark ? 'rgba(226,232,240,0.75)' : 'rgba(41,37,36,0.55)', dashed: false },
    { label: 'Take Profit', value: levels?.takeProfit, stroke: dark ? 'rgba(45,212,191,0.75)' : 'rgba(13,148,136,0.65)', dashed: false },
    { label: 'Stop Loss', value: levels?.stopLoss, stroke: dark ? 'rgba(251,113,133,0.75)' : 'rgba(225,29,72,0.62)', dashed: false },
  ].filter((row) => Number.isFinite(row.value as number))

  return (
    <div className={`grid h-full min-h-[420px] gap-3 rounded-[1.6rem] p-3 ${panelBg}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <p className={`text-[0.72rem] font-semibold uppercase tracking-[0.18em] ${dark ? 'text-stone-400' : 'text-stone-500'}`}>{title}</p>
          <p className={`text-sm ${dark ? 'text-stone-300' : 'text-stone-600'}`}>{activeLabel}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            ['O', activeCandle.open],
            ['H', activeCandle.high],
            ['L', activeCandle.low],
            ['C', activeCandle.close],
          ].map(([label, value]) => (
            <div key={label} className={`rounded-full border px-3 py-1.5 text-sm font-medium ${chipBg}`}>
              <span className={`mr-2 ${dark ? 'text-stone-400' : 'text-stone-500'}`}>{label}</span>
              <span className="font-mono">{formatNumber(value, 4)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={`relative w-full overflow-hidden rounded-[1.4rem] ${chartBg}`} style={{ height: `${height}px` }}>
        <svg
          className="h-full w-full"
          viewBox={`0 0 ${width} ${svgHeight}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={title}
          onMouseLeave={() => setActiveIndex(null)}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, index) => {
            const y = top + priceHeight * ratio
            const value = maxHigh - priceRange * ratio
            return (
              <g key={index}>
                <line x1={left} y1={y} x2={width - right} y2={y} stroke={gridStroke} strokeDasharray="4 6" />
                <text x={width - right + 4} y={y + 4} fontSize="11" fill={axisText}>
                  {formatNumber(value, 4)}
                </text>
              </g>
            )
          })}

          <line x1={left} y1={volumeTop} x2={width - right} y2={volumeTop} stroke={dark ? 'rgba(255,255,255,0.15)' : 'rgba(87,83,78,0.16)'} />

          {levelRows.map((row) => {
            const y = yForPrice(Number(row.value))
            return (
              <g key={row.label}>
                <line
                  x1={left}
                  y1={y}
                  x2={width - right}
                  y2={y}
                  stroke={row.stroke}
                  strokeWidth={1.2}
                  strokeDasharray={row.dashed ? '6 6' : '0'}
                />
                <text x={left + 6} y={y - 6} fontSize="11" fill={row.stroke}>
                  {row.label} {formatNumber(row.value, 4)}
                </text>
              </g>
            )
          })}

          {data.map((item, index) => {
            const x = left + index * candleGap + candleGap / 2
            const openY = yForPrice(item.open)
            const closeY = yForPrice(item.close)
            const highY = yForPrice(item.high)
            const lowY = yForPrice(item.low)
            const bodyY = Math.min(openY, closeY)
            const bodyHeight = Math.max(Math.abs(closeY - openY), 2)
            const bullish = item.close >= item.open
            const color = bullish ? '#145c56' : '#be123c'
            const volumeY = yForVolume(item.volume)
            const isActive = activeIndex === index

            return (
              <g key={`${item.time}-${index}`} onMouseEnter={() => setActiveIndex(index)} className="cursor-crosshair">
                <rect
                  x={x - candleGap / 2 + 1}
                  y={volumeY}
                  width={Math.max(candleGap - 2, 2)}
                  height={volumeTop + volumeHeight - volumeY}
                  fill={bullish ? 'rgba(20,92,86,0.18)' : 'rgba(190,24,60,0.16)'}
                />
                <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth={1.5} />
                <rect
                  x={x - candleWidth / 2}
                  y={bodyY}
                  width={candleWidth}
                  height={bodyHeight}
                  fill={bullish ? 'rgba(20,92,86,0.22)' : 'rgba(190,24,60,0.2)'}
                  stroke={color}
                  strokeWidth={1.5}
                  rx={1.5}
                />
                {isActive ? (
                  <rect
                    x={x - candleGap / 2}
                    y={top}
                    width={candleGap}
                    height={priceHeight + volumeHeight + 24}
                    fill={dark ? 'rgba(255,255,255,0.05)' : 'rgba(20,92,86,0.04)'}
                    stroke={dark ? 'rgba(255,255,255,0.12)' : 'rgba(20,92,86,0.12)'}
                  />
                ) : null}
              </g>
            )
          })}

          {data.filter((_, index) => index % Math.max(Math.floor(data.length / 6), 1) === 0).map((item, index) => {
            const dataIndex = data.findIndex((candidate) => candidate.time === item.time)
            const x = left + dataIndex * candleGap + candleGap / 2
            return (
              <text key={`${item.time}-${index}`} x={x} y={svgHeight - 10} textAnchor="middle" fontSize="11" fill={axisText}>
                {String(item.time).slice(5, 16).replace('T', ' ')}
              </text>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
