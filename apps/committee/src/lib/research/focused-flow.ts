/** Narrow task routing keeps source verification separate from investment decisions. */
export function selectResearchPath(query: string): 'focused_source' | 'committee' {
  if(/(?:买入|卖出|仓位|目标价|值得投资|值得买|投资建议|股价|策略)/.test(query))return 'committee'
  return /(?:核对|查明|查阅|计算|列出|是多少|多少)/.test(query) && /(?:财报|年报|报表|净利润|营业收入|经营现金|经营活动.*现金|资产负债率|每股收益)/.test(query)
    ? 'focused_source' : 'committee'
}
export async function executeFocusedSource<P,R>(packet:P,analyst:(p:P)=>Promise<R>):Promise<{analysis:R;skippedRoles:string[]}> {
  return {analysis:await analyst(packet),skippedRoles:['industry','macro','sentiment','debating','risk_review','voting','decision']}
}

