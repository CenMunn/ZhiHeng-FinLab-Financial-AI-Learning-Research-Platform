import facts from '../data/verified-facts.json'
import contexts from '../data/filing-context.json'
import type { NewsItem, StockProfile } from '../types'
import type { LiveQuote } from '../data/quotes'
import type { EvidenceRecord, FilingContext } from './engine'

export function collectFilingContexts(stockCodes: string[], now: string): FilingContext[] {
  const codes=new Set(stockCodes)
  return (contexts as FilingContext[]).filter(r=>codes.has(r.stockCode)
    && r.verification==='source_checked' && Date.parse(r.publishedAt)<=Date.parse(now)
    && Date.parse(r.validUntil)>=Date.parse(now)).map(r=>({...r}))
}

export function collectEvidence(input: {
  stockCode: string | null; stock: StockProfile | null; news: NewsItem[]; financialClues: NewsItem[]
  quote: LiveQuote | null; capturedAt: string; peerStockCodes?: string[]
}): EvidenceRecord[] {
  const requestedCodes=new Set([input.stockCode,...(input.peerStockCodes??[])])
  const records = (facts as EvidenceRecord[]).filter(r => requestedCodes.has(r.stockCode)).map(r=>({...r}))
  if (input.stock) {
    for (const metric of ['revenue','netProfit','ocf'] as const) {
      records.push({id:`demo:${input.stockCode}:${metric}`,stockCode:input.stockCode ?? '',kind:'demo',metric,
        label:`初赛快照 ${metric}`,value:input.stock.financials[metric],unit:'亿元',currency:'CNY',period:'初赛演示快照，报告期未独立核对',
        publishedAt:null,capturedAt:input.capturedAt,validUntil:null,source:'内置演示近似数据',sourceUrl:null,
        locator:'src/lib/data/stocks.ts 或 global-stocks.ts',excerpt:'仅保留用于披露初赛数据来源，不作为核验通过的依据',verification:'demo'})
    }
  }
  for (const [i,n] of [...input.news,...input.financialClues].entries()) {
    records.push({id:`search:${input.stockCode ?? 'unknown'}:${i+1}`,stockCode:input.stockCode ?? '',kind:'search',metric:'news',label:n.title,
      value:null,unit:'',currency:'',period:n.date ?? '日期未知',publishedAt:n.date ?? null,capturedAt:input.capturedAt,validUntil:null,
      source:n.source,sourceUrl:n.url ?? null,locator:'检索摘要，未核对全文',excerpt:n.summary ?? n.title,verification:'unverified'})
  }
  if (input.quote) {
    const q=input.quote
    records.push({id:`quote:${input.stockCode}:price`,stockCode:input.stockCode ?? '',kind:'quote',metric:'price',label:'行情价格',
      value:q.price,unit:'元/股或指数点',currency:q.currency,period:q.time,publishedAt:null,capturedAt:input.capturedAt,validUntil:null,
      source:q.source,sourceUrl:null,locator:`行情接口 ${q.symbol}`,excerpt:`行情时间 ${q.time}，价格 ${q.price}`,
      verification:'unverified',reviewNote:'接口采集记录；尚未进行时间有效性与复权口径独立校验，不提升为已核对财务证据'})
  }
  return records
}
