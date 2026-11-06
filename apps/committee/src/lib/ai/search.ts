import ZAI from 'z-ai-web-dev-sdk'
import type { NewsItem } from '@/lib/types'
import { companyNewsSymbol, fetchCompanyNews } from '@/lib/data/company-news'

/**
 * 公司资讯与可选网络检索 — News & Sentiment Agent 的数据来源
 * 规则：检索结果原样传入 Agent，不得由 LLM 编造。
 */

let zaiCached: Awaited<ReturnType<typeof ZAI.create>> | null = null

async function getZAI() {
  if (!zaiCached) zaiCached = await ZAI.create()
  return zaiCached
}

export interface RawSearchItem {
  url: string
  name: string
  snippet: string
  host_name: string
  rank: number
  date: string
}

export async function searchNews(query: string, num = 8, recencyDays = 30): Promise<RawSearchItem[]> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const zai = await getZAI()
    const results = (await Promise.race([
      zai.functions.invoke('web_search', { query, num, recency_days: recencyDays }),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('SEARCH_TIMEOUT')), 20_000) }),
    ])) as RawSearchItem[]
    if (!Array.isArray(results)) throw new Error('SEARCH_RESPONSE_INVALID')
    return results.filter((r) => r && r.name)
  } finally {
    if (timer) clearTimeout(timer)
  }
}

export function toNewsItems(items: RawSearchItem[]): NewsItem[] {
  return items.slice(0, 8).map((r) => ({
    title: r.name,
    source: r.host_name,
    date: r.date || undefined,
    url: r.url,
    summary: (r.snippet || '').slice(0, 180),
  }))
}

/** A-share public feed first; optional legacy web-search fallback for other markets. */
export async function collectCompanyNews(stockName: string, stockCode: string): Promise<NewsItem[]> {
  let providerSucceeded = false
  if (companyNewsSymbol(stockCode)) {
    try {
      const news = await fetchCompanyNews(stockCode)
      providerSucceeded = true
      if (news.length) return news
    } catch { /* A configured search provider may still supply a fallback. */ }
  }
  try {
  const r1 = await searchNews(`${stockName} ${stockCode} 股票 最新消息`, 8, 30)
  await new Promise((r) => setTimeout(r, 800))
  const r2 = r1.length >= 4 ? [] : await searchNews(`${stockName} 业绩 三季报 利润`, 6, 90)
  const seen = new Set<string>()
  const merged: RawSearchItem[] = []
  for (const item of [...r1, ...r2]) {
    const key = item.name.slice(0, 40)
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(item)
  }
  return toNewsItems(merged)
  } catch {
    if (providerSucceeded) return []
    throw new Error('NEWS_PROVIDERS_UNAVAILABLE')
  }
}

/**
 * 财务线索检索（快照库未收录标的专用）：
 * 通过真实 web_search 检索营收/利润/估值等财务线索，让 limited-data 标的
 * 获得接近快照库标的的数据支撑（数字必须来自检索结果并标注来源，禁止 LLM 编造）。
 */
export async function collectFinancialClues(stockName: string, stockCode: string): Promise<NewsItem[]> {
  const queries = [
    `${stockName} ${stockCode} 2025 营收 净利润 财报 数据`,
    `${stockName} revenue net profit latest quarterly results PE`,
  ]
  const seen = new Set<string>()
  const merged: RawSearchItem[] = []
  for (const q of queries) {
    const items = await searchNews(q, 6, 180)
    for (const item of items) {
      const key = item.name.slice(0, 40)
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(item)
    }
    if (merged.length >= 6) break
    await new Promise((r) => setTimeout(r, 800))
  }
  return toNewsItems(merged.slice(0, 6))
}
