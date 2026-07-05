/** Split a CSV string into trimmed, non-empty parts. */
export function splitCsv(value: string | undefined): string[] {
  return String(value ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

/** Pick the larger of two symbol arrays — primary wins if it is at least as long. */
export function preferLargerSymbolUniverse(primary: string[] | undefined, fallback: string[]): string[] {
  const primaryList = Array.isArray(primary) ? primary.map((item) => String(item)) : []
  return primaryList.length >= fallback.length ? primaryList : fallback
}
