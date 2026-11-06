import type { NewsItem } from '../types'

/** Public company-news feed, independent of the language-model provider. */
export function companyNewsSymbol(code: string): string | null {
  const normalized = code.trim().toUpperCase()
  if (/^(SH|SZ|BJ)\d{6}$/.test(normalized)) return normalized
  if (!/^\d{6}$/.test(normalized)) return null
  return (/^6/.test(normalized) ? 'SH' : /^[489]/.test(normalized) ? 'BJ' : 'SZ') + normalized
}
function text(value: unknown): string {
  return typeof value === 'string' ? value.replace(/<[^>]*>/g, '').replace(/&(?:nbsp|amp|quot|lt|gt);/g,
    entity => ({ '&nbsp;': ' ', '&amp;': '&', '&quot;': '"', '&lt;': '<', '&gt;': '>' })[entity] ?? entity).trim() : ''
}
function articleUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname.endsWith('.eastmoney.com') || url.username || url.password) return null
    if (!/^\/(a|news)\//.test(url.pathname)) return null
    url.protocol = 'https:'
    return url.toString()
  } catch { return null }
}
export function normalizeCompanyNews(payload: unknown, now = Date.now()): NewsItem[] {
  const feed = (payload as { gszx?: { code?: number; data?: { items?: unknown } } })?.gszx
  if (feed?.code !== 0 || !Array.isArray(feed.data?.items)) throw new Error('NEWS_RESPONSE_INVALID')
  const seen = new Set<string>()
  const items: NewsItem[] = []
  for (const row of feed.data.items) {
    if (!row || typeof row !== 'object') continue
    const title = text(row.title), url = articleUrl(row.uniqueUrl ?? row.url)
    const time = Number(row.showDateTime)
    if (!title || !url || !Number.isFinite(time) || time <= 0 || time > now || now - time > 90 * 86400000) continue
    if (seen.has(url) || seen.has(title)) continue
    seen.add(url); seen.add(title)
    items.push({ title: title.slice(0, 240), source: '东方财富资讯', date: new Date(time).toISOString(), url, summary: text(row.summary).slice(0, 180) })
  }
  return items.sort((a, b) => Date.parse(b.date!) - Date.parse(a.date!)).slice(0, 8)
}
export async function fetchCompanyNews(code: string, options: { now?: number; fetcher?: typeof fetch } = {}): Promise<NewsItem[]> {
  const symbol = companyNewsSymbol(code)
  if (!symbol) return []
  const response = await (options.fetcher ?? fetch)(`https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/PageAjax?code=${symbol}`, {
    cache: 'no-store', signal: AbortSignal.timeout(12000), headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`NEWS_HTTP_${response.status}`)
  return normalizeCompanyNews(await response.json(), options.now ?? Date.now())
}
