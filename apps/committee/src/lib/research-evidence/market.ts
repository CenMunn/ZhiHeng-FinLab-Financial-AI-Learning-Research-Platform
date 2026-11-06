import type { KlineBar, LiveQuote } from '@/lib/data/quotes'
import type { EvidenceRecord } from './engine'

type MarketSource = LiveQuote['source']

export interface QuantitativeReadiness {
  ready: boolean
  reasons: string[]
  records: EvidenceRecord[]
  sampleCount: number
  firstDate: string | null
  lastDate: string | null
}

// These values derive only from the registered daily-bar series. Valuation and
// PEG combine snapshot fields elsewhere in the pipeline, so they must not be
// promoted to source-checked calculation evidence here.
const DAILY_BAR_METRICS = new Set(['momentum', 'rsi14', 'ma20', 'ma60', 'ma120'])

export function marketQuoteSourceUrl(quote: Pick<LiveQuote, 'source' | 'symbol'>): string {
  return quote.source === 'yahoo'
    ? `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(quote.symbol)}`
    : `https://qt.gtimg.cn/q=${encodeURIComponent(quote.symbol)}`
}

export function marketKlineSourceUrl(source: MarketSource, symbol: string, days: number): string {
  return source === 'yahoo'
    ? `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=${Math.max(1, Math.ceil(days / 21))}mo&interval=1d`
    : `https://web.ifzq.gtimg.cn/ifzqgtimg/appstock/fqkline/get?param=${encodeURIComponent(symbol)},day,,,${Math.min(days, 800)},qfq`
}

function iso(value: string | null | undefined): string | null {
  if (!value) return null
  const time = Date.parse(value)
  return Number.isFinite(time) ? new Date(time).toISOString() : null
}

function addDays(value: string, days: number): string {
  const time = Date.parse(value)
  return new Date(time + days * 24 * 60 * 60 * 1000).toISOString()
}

function baseRecord(input: {
  id: string; stockCode: string; kind: EvidenceRecord['kind']; metric: string; label: string
  value: number; unit: string; currency: string; period: string; publishedAt: string | null
  capturedAt: string; validUntil: string; source: string; sourceUrl: string; locator: string; excerpt: string
  reviewNote?: string
}): EvidenceRecord {
  return {
    ...input,
    verification: 'source_checked',
  }
}

function klineDates(kline: KlineBar[]): { dates: string[]; invalid: boolean; duplicate: boolean } {
  const dates = kline.map((bar) => bar.date)
  const parsed = dates.map((date) => Date.parse(date))
  return {
    dates,
    invalid: parsed.some((time) => !Number.isFinite(time)) || kline.some((bar) =>
      ![bar.open, bar.high, bar.low, bar.close, bar.volume].every((value) => Number.isFinite(value) && value >= 0)),
    duplicate: new Set(dates).size !== dates.length,
  }
}

export function assessQuantitativeReadiness(input: {
  stockCode: string; quote: LiveQuote | null; kline: KlineBar[]; capturedAt: string
}): QuantitativeReadiness {
  const reasons: string[] = []
  const records: EvidenceRecord[] = []
  const quoteTime = iso(input.quote?.time)
  const dates = klineDates(input.kline)
  const firstDate = dates.dates[0] ?? null
  const lastDate = dates.dates.at(-1) ?? null
  const klinePublishedAt = iso(lastDate)
  const quoteSource = input.quote ? marketQuoteSourceUrl(input.quote) : null
  const klineSource = input.quote ? marketKlineSourceUrl(input.quote.source, input.quote.symbol, input.kline.length || 300) : null

  if (!input.quote) reasons.push('行情快照缺失')
  if (input.quote && (!quoteTime || Date.parse(quoteTime) > Date.parse(input.capturedAt))) reasons.push('行情时间无效或晚于采集时间')
  if (input.quote && quoteTime && Date.parse(input.capturedAt) - Date.parse(quoteTime) > 7 * 24 * 60 * 60 * 1000) reasons.push('行情时间过期')
  if (input.kline.length < 60) reasons.push(`日线样本不足（${input.kline.length}/60）`)
  if (dates.invalid) reasons.push('日线存在无效数值或日期')
  if (dates.duplicate) reasons.push('日线日期重复')
  if (lastDate && (!klinePublishedAt || Date.parse(klinePublishedAt) > Date.parse(input.capturedAt))) reasons.push('日线最新日期晚于采集时间')

  if (input.quote && quoteSource && quoteTime && Number.isFinite(input.quote.price) && input.quote.price > 0) {
    records.push(baseRecord({
      id: `quote:${input.stockCode}:price`, stockCode: input.stockCode, kind: 'quote', metric: 'price', label: '行情价格',
      value: input.quote.price, unit: '元/股或指数点', currency: input.quote.currency, period: input.quote.time,
      publishedAt: quoteTime, capturedAt: input.capturedAt, validUntil: addDays(input.capturedAt, 1),
      source: input.quote.source === 'yahoo' ? 'Yahoo Finance行情接口' : '腾讯财经行情接口', sourceUrl: quoteSource,
      locator: `行情快照 ${input.quote.symbol}`, excerpt: `行情时间 ${input.quote.time}，价格 ${input.quote.price}`,
      reviewNote: '来源接口、行情时间和采集时间已登记；价格仅代表该快照时点。',
    }))
  }
  if (input.quote && klineSource && klinePublishedAt && input.kline.length > 0) {
    records.push(baseRecord({
      id: `kline:${input.stockCode}:sample`, stockCode: input.stockCode, kind: 'calculation', metric: 'kline_sample_count', label: '日线样本数',
      value: input.kline.length, unit: 'bars', currency: input.quote.currency, period: `${firstDate}—${lastDate}`,
      publishedAt: klinePublishedAt, capturedAt: input.capturedAt, validUntil: addDays(input.capturedAt, 7),
      source: input.quote.source === 'yahoo' ? 'Yahoo Finance日线接口' : '腾讯财经前复权日线接口', sourceUrl: klineSource,
      locator: `日线样本 ${firstDate}—${lastDate}`, excerpt: `共 ${input.kline.length} 条日线，最新收盘 ${input.kline.at(-1)?.close ?? 'N/A'}`,
      reviewNote: '指标计算只使用登记区间内的收盘价；复权口径由来源接口参数记录。',
    }))
  }

  return { ready: reasons.length === 0, reasons, records, sampleCount: input.kline.length, firstDate, lastDate }
}

export function buildQuantMetricEvidence(input: {
  stockCode: string; quote: LiveQuote; kline: KlineBar[]; metrics: Record<string, number | null>; capturedAt: string
}): EvidenceRecord[] {
  const lastDate = input.kline.at(-1)?.date ?? input.quote.time
  const firstDate = input.kline[0]?.date ?? lastDate
  const sourceUrl = marketKlineSourceUrl(input.quote.source, input.quote.symbol, input.kline.length || 300)
  const source = input.quote.source === 'yahoo' ? 'Yahoo Finance日线接口' : '腾讯财经前复权日线接口'
  return Object.entries(input.metrics)
    .filter((entry): entry is [string, number] => DAILY_BAR_METRICS.has(entry[0]) && typeof entry[1] === 'number' && Number.isFinite(entry[1]))
    .filter(([metric]) => input.kline.length >= ({momentum:127,rsi14:15,ma20:20,ma60:60,ma120:120}[metric] ?? Infinity))
    .map(([metric, value]) => {
      const priceLike = /^ma\d+$/i.test(metric)
      return baseRecord({
        id: `quant:${input.stockCode}:${metric}`, stockCode: input.stockCode, kind: 'calculation', metric,
        label: `代码量化指标 ${metric}`, value, unit: priceLike ? '元/股' : metric === 'rsi14' ? '分' : '分',
        currency: input.quote.currency, period: `${firstDate}—${lastDate}`, publishedAt: iso(lastDate),
        capturedAt: input.capturedAt, validUntil: addDays(input.capturedAt, 7), source, sourceUrl,
        locator: `量化引擎公式；输入日线样本=${input.kline.length}；收盘价区间=${firstDate}—${lastDate}`,
        excerpt: `${metric}=${value}，由代码按登记日线计算`, reviewNote: '该记录是可复算的代码结果，不是模型生成值。',
      })
    })
}
