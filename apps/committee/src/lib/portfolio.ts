import { findStock } from '@/lib/data/stocks'
import type { HoldingInput, PortfolioResult, StockProfile } from '@/lib/types'

/** Resolve exact identifiers only. Never infer accounting identity from a substring. */
function portfolioStock(name: string): StockProfile | null {
  const exact = findStock(name, { exact: true })
  if (exact) return exact
  const label = name.match(/^(.+?)\s*[(（]([^()（）]+)[)）]$/)
  if (label) {
    const stock = portfolioStock(label[2].trim())
    const named = findStock(label[1].trim(), { exact: true })
    return stock && named && stock.code === named.code && stock.market === named.market ? stock : null
  }
  const prefix = name.match(/^(SH|SZ|HK|US)[.:]?([a-z0-9.]+)$/i)
  const suffix = name.match(/^([a-z0-9.]+)\.(SH|SZ|HK|US)$/i)
  const code = prefix?.[2] ?? suffix?.[1]
  const market = (prefix?.[1] ?? suffix?.[2])?.toUpperCase()
  if (!code) return null
  const stock = findStock(code, { exact: true })
  return stock?.code.toLowerCase() === code.toLowerCase() && stock.market === market ? stock : null
}

export function normalizePortfolioHoldings(holdings: HoldingInput[]) {
  const valid = holdings.filter(h => h.name.trim() && Number.isFinite(h.weight) && h.weight > 0)
  if (!valid.length) return []
  // Scale before addition to avoid overflow from otherwise finite positive weights.
  const scale = Math.max(...valid.map(h => h.weight))
  const groups = new Map<string, { name: string; stock: StockProfile | null; weights: number[] }>()
  for (const h of valid) {
    const name = h.name.trim(), stock = portfolioStock(name)
    // Unknowns merge only on the identical trimmed label; do not guess names/markets.
    const key = stock ? `stock:${stock.market}:${stock.code}` : `unknown:${name}`
    const group = groups.get(key) ?? { name: stock?.name ?? name, stock, weights: [] }
    group.weights.push(h.weight / scale)
    groups.set(key, group)
  }
  // Stable order and stable addition make suggestions and statistics independent of row order.
  const merged = [...groups.entries()].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([, h]) => ({ name: h.name, stock: h.stock, weight: h.weights.sort((a, b) => a - b).reduce((s, w) => s + w, 0) }))
  const total = merged.reduce((s, h) => s + h.weight, 0)
  // Remove arithmetic noise (e.g. 30.000000000000004%) before strict risk thresholds.
  // Fifteen significant digits retain far more precision than the displayed 0.1%.
  return merged.map(h => ({ ...h, weight: Number(((h.weight / total) * 100).toPrecision(15)) }))
}

export function portfolioRiskLevel(hhi: number, maxSingle: number): PortfolioResult['riskLevel'] {
  return hhi >= 4500 || maxSingle > 40 ? 'Very High' : hhi >= 3000 || maxSingle > 30 ? 'High' : hhi >= 1800 ? 'Medium' : 'Low'
}
