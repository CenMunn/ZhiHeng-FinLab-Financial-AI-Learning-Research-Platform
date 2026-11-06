export interface QueryTerm { term: string; meaning: string; note?: string }
export interface QueryTarget { code: string; name: string }
export interface QueryResolution {
  kind: 'explanation' | 'clarification' | 'research'; query: string; answer: string | null
  terms: QueryTerm[]; targets: QueryTarget[]; suggestedQuestions: string[]; researchAllowed: boolean
}
const CONCEPTS = [
  { re: /市盈率|\bPE\b/i, text: '市盈率用于观察价格相对盈利的水平，常用公式为股价÷同口径基本每股收益，或总市值÷归母净利润。低市盈率可能对应低增长、盈利周期高点或较高风险；亏损时通常不宜机械使用。应明确静态、滚动或预测口径，并结合盈利质量与同行比较。' },
  { re: /市净率|\bPB\b/i, text: '市净率是价格相对净资产的指标，常用公式为总市值÷同口径归属于普通股股东的净资产。数值较低不自动代表低估，还需关注资产质量、盈利能力和行业特点。' },
  { re: /ROE|净资产收益率/i, text: '净资产收益率用于观察股东资本的盈利效率，需注明加权平均或期末口径以及是否扣除非经常性损益。较高ROE可能来自盈利能力，也可能受到杠杆或资本变化影响，不能单独据此判断投资价值。' },
  { re: /净利润.*归母|归母.*净利润/, text: '合并净利润、归母净利润和母公司单体净利润属于不同口径。合并净利润按归属分为归母净利润与少数股东损益；母公司单体利润不包含与合并范围一致的全部经营结果。定义不同不意味着某期金额必然不同，必须核对同年度完整报表。' },
  { re: /现金流.*利润|利润.*现金流/, text: '利润按权责发生制确认，现金流反映现金收支，两者不必在同一期间相等。经营现金流应按原报表分类，并关注应收款、存货、预收或合同负债等变化。合并经营现金流与归母净利润的归属范围不同，直接相除只宜作为辅助观察。' },
  { re: /护城河/, text: '护城河是对企业竞争优势的概括，常见来源包括品牌、成本、渠道、转换成本和网络效应。判断其是否存在及能否持续，需要竞争数据和经营证据；它不是保证未来盈利或股价上涨的术语。' },
]
/** Deterministic routing with explicitly supplied catalog hits; never guesses a security. */
export function classifyQuery(query: unknown, context: {terms: QueryTerm[]; targets: QueryTarget[]; ambiguous?: boolean} = {terms:[],targets:[]}): QueryResolution {
  if(typeof query!=='string' || !query.trim()) throw new Error('请输入研究问题或需要解释的金融术语')
  const q=query.trim()
  if(q.length>200) throw new Error('输入不超过200字，请精简后重试')
  const terms=context.terms.slice(0,10), targets=context.targets.slice(0,6)
  const result=(kind:QueryResolution['kind'],answer:string|null,suggestedQuestions:string[]=[]):QueryResolution=>
    ({kind,query:q,answer,terms,targets,suggestedQuestions,researchAllowed:kind==='research'})
  const meaning=/什么意思|什么是|是什么意思|怎么理解|解释(?:一下)?|黑话.*(?:含义|意思)|翻译/.test(q)
  const concept=CONCEPTS.find(x=>x.re.test(q))
  if(meaning || (!targets.length && concept && /是不是|一定|越低|越高|区别|为什么|怎么|如何/.test(q))) {
    if(concept) return result('explanation',concept.text)
    if(terms.length) return result('explanation',terms.map(t=>`「${t.term}」：${t.meaning}${t.note ? `。补充：${t.note}`:''}`).join('\n\n')+'\n\n这些是市场描述性用语，不代表经过验证的事实或必然的交易信号。')
    if(targets.length===1) return result('explanation',`目录识别到${targets[0].name}（${targets[0].code}）。若需解释昵称，请补充出现该词的句子；若需投资研究，请明确报告期或研究问题。`)
    return result('clarification','该表述尚未收录或含义存在歧义。请补充原句、市场或具体上下文，我会先确认含义。')
  }
  if(context.ambiguous || targets.length>2)
    return result('clarification',`这个称呼可能对应多个标的：${targets.map(t=>`${t.name}（${t.code}）`).join('、')}。请选择具体公司或明确需要对比的两家。`,targets.map(t=>`分析${t.name}的经营与风险`))
  if(!targets.length)
    return result('clarification','请补充股票名称或标准代码，以及你关注的报告期或持有周期。仅凭“上车”“抄底”等用语，无法确定研究标的或判断买卖时机。',['核对贵州茅台2025年度经营现金流','比较贵州茅台与五粮液2025年度财务数据'])
  return result('research',null)
}
