import { matchSlang } from '@/lib/data/slang-dictionary'
import { STOCKS } from '@/lib/data/stocks'
import { GLOBAL_STOCKS } from '@/lib/data/global-stocks'
import { matchHotTerms } from '@/lib/data/hot-terms'
import { stockMentionPosition } from '@/lib/data/stock-mention'
import { matchUniverseStocks } from '@/lib/data/universe'
import { classifyQuery, type QueryTarget } from './query-intent'

export async function resolveQuery(query: unknown) {
  // Validate before any catalog/database work.
  classifyQuery(query)
  const q=(query as string).trim()
  const terms=matchSlang(q).map(t=>({term:t.term,meaning:t.meaning,note:t.note}))
  const targets=new Map<string,QueryTarget>()
  for(const s of [...STOCKS,...GLOBAL_STOCKS])
    if([s.code,s.name,...s.alias].some(k=>k.length>=2 && stockMentionPosition(q,k)!==-1)) targets.set(s.code,{code:s.code,name:s.name})
  const hot=matchHotTerms(q)
  for(const h of hot) for(const s of h.term.stocks) targets.set(s.code,{code:s.code,name:s.name})
  // Resolve every deterministic identity catalog before classifying an explanation.
  // Database-only companies must retain the same research route as local stocks.
  if(!targets.size) {
    // The verified identity catalog contains no live valuation assumptions.
    const matches=await matchUniverseStocks(q,6)
    for(const h of matches) targets.set(h.stock.code,{code:h.stock.code,name:h.stock.name})
  }
  return classifyQuery(q,{terms,targets:[...targets.values()],ambiguous:hot.some(h=>h.term.stocks.length>2)})
}
