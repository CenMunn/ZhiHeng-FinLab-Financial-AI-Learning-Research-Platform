/** Server-owned evidence provenance. A numeric match is NOT semantic entailment. */
export interface EvidenceRecord {
  id: string
  stockCode: string
  kind: 'filing' | 'quote' | 'search' | 'demo' | 'calculation'
  metric: string
  label: string
  value: number | null
  unit: string
  currency: string
  period: string
  scope?: 'consolidated' | 'parent_attributable' | 'parent_company' | 'segment' | 'unknown'
  reportingScope?: 'consolidated' | 'parent_company' | 'segment' | 'unknown'
  publishedAt: string | null
  capturedAt: string
  validUntil: string | null
  source: string
  sourceUrl: string | null
  locator: string
  excerpt: string
  verification: 'source_checked' | 'unverified' | 'demo'
  documentSha256?: string
  page?: number
  reviewNote?: string
}

export interface Citation {
  claim: string
  metric?: string
  evidenceId?: string
  value?: string
  unit?: string
  currency?: string
  period?: string
  reportingScope?: 'consolidated' | 'parent_company' | 'segment' | 'unknown'
  source?: string
  sourceUrl?: string
  confidence?: 'High' | 'Medium' | 'Low'
  verification?: 'matched' | 'unverified' | 'rejected'
  verificationNote?: string
  agentKey?: string
}

export interface DecisionGate {
  status: 'ready' | 'limited' | 'review_required'
  canPublishDecision: boolean
  reasons: string[]
  checkedAt: string
}

export interface ResearchAudit {
  version: 'evidence-v1'
  runId: string
  capturedAt: string
  records: EvidenceRecord[]
  claims: Citation[]
  decisionGate?: DecisionGate
  reportMd?: string
  researchConclusion?: import('../research/discussion').ResearchConclusion
  researchDiscussion?: import('../research/discussion').ResearchTurn[]
  stageDurationsMs: Record<string, number>
  failedAgents: string[]
  modelEvaluation: 'not_run' | 'live'
  financialComparison?: FinancialComparison
  skippedStages?: string[]
  reportReview?: {status:string;issues:unknown[];originalDraft?:string;completeSemanticVerification:false}
  scoreReviewRevision?:number
  scoreReviews?:(import('../research/score-review').ScoreReviewEntry&{reportBefore:string;agentBefore:import('../types').AgentDTO})[]
}

export function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

function dateValid(value: string | null): boolean {
  return !!value && Number.isFinite(Date.parse(value))
}

export function isUsableRecord(record: EvidenceRecord, now: string): boolean {
  return record.verification === 'source_checked'
    && Number.isFinite(record.value) && record.value !== null
    && !!safeSourceUrl(record.sourceUrl) && !!record.locator && !!record.excerpt
    && dateValid(record.publishedAt) && Date.parse(record.publishedAt!) <= Date.parse(now)
    && dateValid(record.validUntil) && Date.parse(record.validUntil!) >= Date.parse(now)
}

export function checkCitation(claim: Citation, records: EvidenceRecord[], now: string): Citation {
  // Never retain model supplied source URL or verification status.
  const clean: Citation = { claim: claim.claim, evidenceId: claim.evidenceId, value: claim.value,
    unit: claim.unit, currency: claim.currency, period: claim.period, metric:claim.metric, reportingScope:claim.reportingScope, agentKey: claim.agentKey }
  const found = records.filter(r => r.id === claim.evidenceId)
  if (found.length !== 1) return { ...clean, verification: 'rejected', verificationNote: '证据编号缺失、不存在或不唯一' }
  const record = found[0]
  const scope=record.reportingScope ?? (record.scope==='parent_attributable' ? 'consolidated' : record.scope) ?? (record.kind==='filing'?'unknown':undefined)
  if(scope==='unknown') return {...clean,verification:'unverified',verificationNote:'原始资料的报表范围未知，不能标为核验匹配'}
  if(claim.reportingScope && scope && claim.reportingScope!==scope)
    return {...clean,verification:'rejected',verificationNote:'报表范围与登记证据不一致：合并、母公司单体或分部不能互换'}
  const resolved = { ...clean, source: record.source, sourceUrl: safeSourceUrl(record.sourceUrl) ?? undefined }
  if (!isUsableRecord(record, now)) {
    return { ...resolved, verification: 'unverified', verificationNote: '来源未核对、非数值资料、演示数据或不在有效期内；不能据此确认主张' }
  }
  if(record.kind==='filing') {
    const text=claim.claim.replace(/\s/g,'')
    const aliases: [string,RegExp][]=[
      ['revenue',/营业收入|营收|\brevenue\b/i],
      ['adjustedNetProfit',/扣非|扣除非经常性损益/],
      ['operatingCashInflow',/经营(?:活动)?(?:产生的)?现金流?入/],
      ['operatingCashOutflow',/经营(?:活动)?(?:产生的)?现金流?出/],
      ['ocf',/经营(?:活动)?(?:产生的)?现金流(?:量)?(?:净额)?|\bocf\b/i],
      ['netProfit',/归母(?:净)?利(?:润)?|归属于(?:上市公司|母公司)(?:所有者|股东)?的?净利润/],
      ['basicEPS',/基本每股收益|\bbasicEPS\b/i],
    ]
    const metrics=aliases.filter(([,re])=>re.test(text)).map(([key])=>key)
    if(/净利润/.test(text)&&!metrics.includes('netProfit'))metrics.push('totalNetProfit')
    const expected=record.metric==='netProfit'&&record.scope!=='parent_attributable'?'totalNetProfit':record.metric
    if(claim.metric&&claim.metric!==record.metric||metrics.some(key=>key!==expected))
      return {...resolved,verification:'rejected',verificationNote:'引用指标或利润归属类别与登记记录不一致；金额相同不能替换科目'}
    if(!metrics.includes(expected)&&!text.includes(record.label.replace(/\s/g,'')))
      return {...resolved,verification:'unverified',verificationNote:'主张没有明确对应的财务指标，需人工确认科目语义'}
  }
  const text = (claim.value ?? '').trim().replaceAll(',', '')
  const value = /^-?\d+(?:\.\d+)?$/.test(text) ? Number(text) : NaN
  // Exact canonical values only. Unit conversions must become separate code-derived records.
  if (!Number.isFinite(value) || value !== record.value || claim.unit !== record.unit
    || claim.currency !== record.currency || claim.period !== record.period) {
    return { ...resolved, verification: 'rejected', verificationNote: '数值、单位、币种或报告期与登记记录不一致' }
  }
  return { ...resolved, verification: 'matched', verificationNote: '已识别指标、数值、单位、币种和报告期一致；完整论点语义仍需人工复核' }
}

export function evaluateGate(input: {
  records: EvidenceRecord[]; claims: Citation[]; riskStatus: 'ok' | 'failed' | 'invalid' | 'not_run'
  failedAgents: string[]; quantitativeReady: boolean; now: string
}): DecisionGate {
  const reasons: string[] = []
  let review = false
  if (input.riskStatus === 'not_run') reasons.push('本轮仅开展资料与来源分析，未执行投资风控审查，暂停评级与仓位建议')
  else if (input.riskStatus !== 'ok') { review = true; reasons.push('风控审查未有效完成，暂停评级与仓位建议') }
  if (input.failedAgents.length) { review = true; reasons.push(`分析环节未完成：${input.failedAgents.join('、')}`) }
  if (input.claims.some(c => c.verification === 'rejected')) { review = true; reasons.push('存在引用核验失败，需复核证据编号及数据口径') }
  const groups = new Map<string, Set<string>>()
  const values = new Map<string, number>()
  const ids=new Set<string>()
  for (const r of input.records) {
    if (ids.has(r.id)) {review=true;reasons.push(`证据编号重复：${r.id}`)}
    ids.add(r.id)
    if (r.kind !== 'filing' || !isUsableRecord(r, input.now)) continue
    const key = `${r.stockCode}|${r.period}|${r.currency}`
    const valueKey=`${key}|${r.metric}|${r.unit}|${r.scope ?? 'unknown'}`
    if(values.has(valueKey) && values.get(valueKey)!==r.value) {review=true;reasons.push(`同口径来源数值冲突：${r.label}`)}
    values.set(valueKey,r.value!)
    const metrics = groups.get(key) ?? new Set<string>()
    if((r.metric==='netProfit' && r.scope==='parent_attributable')
      || (['revenue','ocf'].includes(r.metric) && r.scope==='consolidated')) metrics.add(r.metric)
    groups.set(key, metrics)
  }
  if (![...groups.values()].some(g => ['revenue','netProfit','ocf'].every(m => g.has(m)))) {
    reasons.push('缺少同标的、同报告期、同币种的已核对营业收入、归母净利润和经营现金流')
  }
  if (!input.quantitativeReady) reasons.push('量化输入尚含演示快照或缺失数据，不能作为正式评分依据')
  if (!input.claims.length || input.claims.some(c => c.verification !== 'matched')) {
    reasons.push('部分分析主张尚未完成数值引用核验')
  }
  const status = review ? 'review_required' : reasons.length ? 'limited' : 'ready'
  return {status, canPublishDecision: status === 'ready', reasons, checkedAt: input.now}
}

export const GATE_LABELS = {ready:'可形成研究结论',limited:'有限分析',review_required:'需要人工复核'} as const

/** Preflight only: ready permits attempting risk/debate, never publishes a decision. */
export function canStartDecisionStages(input:{records:EvidenceRecord[];claims:Citation[];failedAgents:string[];quantitativeReady:boolean;now:string}):{ready:boolean;reasons:string[]} {
  const preflight=evaluateGate({...input,riskStatus:'ok'})
  return {ready:preflight.status==='ready',reasons:preflight.reasons}
}

export function isRiskPayloadValid(raw: unknown): boolean {
  if(!raw || typeof raw!=='object') return false
  const r=raw as Record<string,unknown>
  return ['Low','Medium','High','Very High'].includes(String(r.riskLevel))
    && typeof r.riskPenalty==='number' && Number.isFinite(r.riskPenalty) && r.riskPenalty>=0 && r.riskPenalty<=15
    && typeof r.score==='number' && Number.isFinite(r.score) && r.score>=0 && r.score<=100
}

const md = (text: string) => text.replace(/[\r\n|]/g, ' ').replace(/[<>]/g, '')

export function buildReviewReport(input: {
  runId: string; stockName: string; query: string; records: EvidenceRecord[]; gate: DecisionGate; claims: Citation[]
  analyses?: {name:string;summary:string}[]
}): string {
  const scopeLabel=(r:EvidenceRecord)=>r.scope==='parent_attributable' ? '合并报表中的归母指标'
    :r.scope==='consolidated' ? '合并口径':r.scope==='parent_company' ? '母公司单体口径':r.scope==='segment'?'分部口径':'报表范围待核对'
  const periods=[...new Set(input.records.filter(r=>isUsableRecord(r,input.gate.checkedAt)).map(r=>r.period))]
  const lines = [
    `# ${md(input.stockName)} 财务研究与证据核验报告`, '',
    `运行编号：${input.runId}`, `核验时间：${input.gate.checkedAt}`, `研究问题：${md(input.query)}`, '',
    '## 一、执行摘要','',`研究状态：${GATE_LABELS[input.gate.status]}`, '',
    input.gate.canPublishDecision ? '已达到本轮程序门槛；论点语义与投资判断仍需人工复核。' : '本轮不输出最终投资评级、置信度或仓位建议。', '',
    ...input.gate.reasons.map(r => `- ${r}`), '',
    '## 二、资料范围与分析方法','',
    `主要披露期间：${periods.map(md).join('、') || '尚无有效期间'}；研究时点：${input.gate.checkedAt}。`,
    '本报告基于登记来源与程序检查汇编。分别标识合并报表、母公司单体及归母指标；不得将母公司单体理解为控股股东的报表。原始金额与派生指标分开，资料缺失不填零。模型观察仍需人工语义复核。','',
    '## 三、已登记事实', '',
    ...(input.records.some(r=>r.value!==null) ? input.records.filter(r=>r.value !== null).map(r =>
      `- **${md(r.label)}**：${r.value} ${md(r.unit)} / ${md(r.currency)}；${md(r.period)}；${scopeLabel(r)}；编号 ${md(r.id)}；${isUsableRecord(r,input.gate.checkedAt) ? '原始来源已核对' : r.verification === 'demo' ? '演示近似值，不作决策依据' : '待核对或过期'}。`) : ['当前没有已登记的数值资料。']), '',
    '## 四、研究观察与资料缺口','',
    ...(input.analyses?.length ? input.analyses.map(a=>`- **${md(a.name)}（模型观察，待人工复核）**：${md(a.summary)}`):['本轮未提供足以形成完整研究判断的经核验分析。']), '',
    '## 五、来源与引用', '',
    ...input.records.map(r => `- ${md(r.id)}：${md(r.source)}；${md(r.locator)}；${safeSourceUrl(r.sourceUrl) ? `[原始来源](${safeSourceUrl(r.sourceUrl)})` : '无外部原始链接'}。采集时间：${r.capturedAt}。${md(r.reviewNote ?? '')}`), '',
    '### 数值引用检查', '',
    ...(input.claims.length ? input.claims.map(c => `- ${md(c.agentKey ?? '')} / ${md(c.evidenceId ?? '未提供编号')}：${c.verification ?? '未核验'}，${md(c.verificationNote ?? '')}`) : ['尚无模型引用核验结果。']), '',
    '## 六、局限与后续复核', '',
    '原始来源核对不代表投资结论正确；数值匹配不等于论点语义成立。搜索摘要及演示快照不视为经核验的财务披露。有效期是本项目复核策略，不表示期间不存在更新公告。',
  ]
  return lines.join('\n')
}

export function normalizeDebateTurn(content: unknown): {content: string; error?: string} {
  return typeof content === 'string' && content.trim()
    ? {content: content.trim()}
    : {content:'本轮生成失败或返回内容无效，未形成论证，需重试或人工复核。',error:'DEBATE_OUTPUT_UNAVAILABLE'}
}

export function isAgentPayloadValid(raw: unknown): boolean {
  if (!raw || typeof raw !== 'object') return false
  const r = raw as Record<string,unknown>
  return typeof r.summary === 'string' && !!r.summary.trim()
    && ['score','confidence'].every(k => r[k] == null || (typeof r[k] === 'number' && Number.isFinite(r[k]) && r[k] >= 0 && r[k] <= 100))
    && (r.vote == null || ['BUY','HOLD','SELL'].includes(String(r.vote).toUpperCase()))
}

/** Generation rules contain no case IDs, company values, or evaluation answers. */
export const FINANCIAL_SEMANTIC_RULE = `【年度、口径与推断检查】
年度比较：先写清目标期间A与基准期间B；相对变化=(A/B-1)×100%，分母为B。年报“本年比上年”列只支持本年相对上年；不能将同一变化率用于反向比较。反向比较需用两期原值另算。分母非正或期间/主体/业务范围/单位不一致时不机械报告增长率；百分比与百分点分开。问题只问原值时，避免附加无必要的跨期断言。
现金流口径：按原报表的经营/投资/筹资分类描述，不因财务子公司、存款或业务结构影响而自行重分类。“不等于单独主营回款”不表示“非经营性现金流”或“完全与主营无关”。缺少分部及内部抵销资料时不能通过减去单个项目制造精确剔除结果。
证据推断：净利润、归母净利润、扣非归母净利润、少数股东损益分别定位年度和报表范围；不同定义不意味着金额必然不同。非经常性损益中的少数股东影响额是局部项目，不能证明全年少数股东损益或合并净利润与归母净利润不相等。判断某期金额相等/不等，需要完整同口径利润表原值或完整关系证据；缺失时说明无法核验。以上检查适用于所有输出字段和附加说明，正确的主数值不抵消错误的额外断言。`

export interface FinancialSemanticIssue {
  code: 'ANNUAL_COMPARISON_MISMATCH' | 'ANNUAL_COMPARISON_UNDEFINED'
    | 'CASH_FLOW_RECLASSIFICATION' | 'PARTIAL_ITEM_PROFIT_INFERENCE' | 'UNIVERSAL_PROFIT_INEQUALITY'
  field: string
  excerpt: string
  message: string
  evidenceIds: string[]
}

/** Narrow contradiction checks, not an entailment oracle; never rewrites an answer. */
export function reviewFinancialSemantics(raw: Record<string, unknown>, input: {
  records: EvidenceRecord[]; contexts: FilingContext[]; now: string
}): { status: 'review_required' | 'no_issue_detected'; issues: FinancialSemanticIssue[]; completeSemanticVerification: false } {
  const issues: FinancialSemanticIssue[] = []
  const texts: {field:string;text:string}[]=[]
  const walk=(value:unknown,field:string)=>{
    if(typeof value==='string') texts.push({field,text:value})
    else if(Array.isArray(value)) value.forEach((v,i)=>walk(v,`${field}[${i}]`))
    else if(value && typeof value==='object') Object.entries(value).forEach(([k,v])=>walk(v,`${field}.${k}`))
  }
  // Inspect the complete response before display truncation, including extra claims.
  walk(raw,'output')
  const add=(code:FinancialSemanticIssue['code'],field:string,excerpt:string,message:string,evidenceIds:string[]=[])=>{
    issues.push({code,field,excerpt:excerpt.slice(0,500),message,evidenceIds})
  }
  const records=input.records.filter(r=>isUsableRecord(r,input.now))
  const contexts=input.contexts.filter(c=>c.verification==='source_checked' && !!safeSourceUrl(c.sourceUrl)
    && !!c.locator && !!c.excerpt && dateValid(c.publishedAt) && Date.parse(c.publishedAt)<=Date.parse(input.now)
    && dateValid(c.validUntil) && Date.parse(c.validUntil)>=Date.parse(input.now))
  const negated=(clause:string)=>/(?:不能|不可|不应|不得|不要|并非|不是|未必|无法|不意味着|不代表|不足以|不能仅)[^。；;!?！？]*$/.test(clause)
  const year=(r:EvidenceRecord)=>r.period.match(/^(\d{4})(?:年(?:度)?)?$/)?.[1]
  for(const {field,text} of texts){
    for(const match of text.matchAll(/((?:19|20)\d{2})年(?:度)?(?:较|相对|相比于?)((?:19|20)\d{2})年(?:度)?([^。；;!?！？]{0,65}?)([-+−]?\d+(?:\.\d+)?)\s*[%％]/g)){
      const prefix=text.slice(Math.max(0,match.index!-180),match.index)
      const precedingClause=prefix.split(/[，,。；;!?！？]/).at(-1) ?? ''
      if(negated(precedingClause)) continue
      const nearby=prefix+match[0]
      const pairs:{a:EvidenceRecord;b:EvidenceRecord}[]=[]
      for(const a of records.filter(r=>year(r)===match[1])){
        const label=a.label.replace(/(?:19|20)\d{2}年(?:度)?/g,'').trim()
        if(!label || !nearby.includes(label) || !a.documentSha256) continue
        const candidates=records.filter(b=>year(b)===match[2] && b.stockCode===a.stockCode && b.metric===a.metric
          && b.unit===a.unit && b.currency===a.currency && b.scope===a.scope && b.documentSha256===a.documentSha256)
        if(candidates.length===1 && records.filter(r=>year(r)===match[1] && r.stockCode===a.stockCode && r.metric===a.metric
          && r.unit===a.unit && r.currency===a.currency && r.scope===a.scope && r.documentSha256===a.documentSha256).length===1)
          pairs.push({a,b:candidates[0]})
      }
      // Multiple possible subjects/metrics cannot be resolved safely by substring matching.
      if(pairs.length!==1) continue
      const {a,b}=pairs[0]
      if(b.value!<=0){
        add('ANNUAL_COMPARISON_UNDEFINED',field,match[0],'比较分母非正，不适用普通相对增长率；需说明口径。',[a.id,b.id]);continue
      }
      let claimed=Number(match[4].replace('−','-'))
      if(!/^[-+−]/.test(match[4]) && /下降|减少|降低/.test(match[3])) claimed=-claimed
      const expected=(a.value!/b.value!-1)*100
      const directionWrong=(expected<0 && /上升|增长|增加/.test(match[3])) || (expected>0 && /下降|减少|降低/.test(match[3]))
      const decimalPlaces=match[4].split('.')[1]?.length ?? 0
      const roundingTolerance=0.5*10**(-decimalPlaces)+1e-9
      if(Math.abs(claimed-expected)>roundingTolerance || directionWrong)
        add('ANNUAL_COMPARISON_MISMATCH',field,match[0],`年度方向或变化率与登记原值不符：${match[1]}相对${match[2]}应以${match[2]}为分母，推算${expected.toFixed(2)}%。`,[a.id,b.id])
    }
    for(const sentence of text.split(/[。；;!?！？\n]/)){
      for(const match of sentence.matchAll(/(?:属于|归为|归类为|列为|属|是)\s*非经营(?:性|活动)(?:因素|现金流)?/g)){
        const before=sentence.slice(0,match.index)
        const clause=before.split(/[，,]/).at(-1) ?? ''
        if(negated(clause)) continue
        // Keep local subject context: a separate dividend sentence is not a deposit claim.
        const separateSubject=/现金分红|股利|购建固定资产/.test(clause)
          && !/财务(?:子)?公司|财务有限公司|成员单位存款|同业存款|客户存款/.test(clause)
        const component=separateSubject ? clause : before.slice(-180)
        const deposit=/财务(?:子)?公司|财务有限公司|成员单位存款|同业存款|客户存款/.test(component)
        const supporting=contexts.filter(c=>/经营(?:活动.*)?现金流|经营活动产生的现金流量净额/.test(c.excerpt)
          && /存款|财务(?:子)?公司|财务有限公司/.test(c.excerpt))
        if(deposit && supporting.length)
          add('CASH_FLOW_RECLASSIFICATION',field,sentence,'来源把所述存款/财务公司影响列入经营现金流说明；不能自行改称非经营性因素，需复核分类及业务范围。',supporting.map(c=>c.id))
      }
      if(/非经常性损益/.test(sentence) && /少数股东/.test(sentence)
        && /(?:证明|佐证|说明|因此)[^。；]{0,90}(?:不相等|金额不同|数值不同|必然不同)/.test(sentence)
        && !negated(sentence.split(/证明|佐证|说明|因此/)[0]))
        add('PARTIAL_ITEM_PROFIT_INFERENCE',field,sentence,'局部非经常性损益的少数股东影响额不能证明全年利润金额不等；需完整同年度利润表或完整少数股东损益。')
      if(/净利润/.test(sentence) && /归母净利润|归属于(?:上市公司|母公司)股东的净利润/.test(sentence)){
        for(const m of sentence.matchAll(/(?:必然|必定|一定|总是|永远)(?:不相等|不同|不等于)|(?:必然|必定|一定|总是|永远)[^，,。；]{0,20}(?:不相等|金额不同|不等于)/g)){
          const clause=sentence.slice(0,m.index).split(/[，,]/).at(-1) ?? ''
          if(clause.endsWith('不') || negated(clause)) continue
          add('UNIVERSAL_PROFIT_INEQUALITY',field,sentence,'会计定义或归属范围不同不意味着金额必然不同；必须限定主体/期间并提供完整证据。')
        }
      }
    }
  }
  return {status:issues.length ? 'review_required' : 'no_issue_detected',issues,completeSemanticVerification:false}
}

export interface FilingContext {
  id: string; stockCode: string; period: string; summary: string; excerpt: string
  source: string; sourceUrl: string; locator: string; page: number
  documentSha256: string; publishedAt: string; capturedAt: string; validUntil: string
  verification: string; reviewNote: string
}

export interface ComparisonValue {
  stockCode: string; stockName: string; value: number | null; evidenceIds: string[]; note?: string
}

export interface FinancialComparison {
  caseId: 'D02'; status: 'comparable' | 'limited' | 'review_required'
  period: string; currency: string; canPublishDecision: false
  rows: {metric: string; label: string; unit: string; derived: boolean; formula: string; values: ComparisonValue[]}[]
  reasons: string[]; observations: string[]; limitations: string[]; contexts: FilingContext[]
}

const COMPARISON_STOCKS = [{code:'600519',name:'贵州茅台'},{code:'000858',name:'五粮液'}] as const
const COMPARISON_METRICS = [{key:'revenue',label:'营业收入',scope:'consolidated'},
  {key:'netProfit',label:'归母净利润',scope:'parent_attributable'},
  {key:'ocf',label:'经营活动现金流量净额',scope:'consolidated'}] as const

/** D02 is a deterministic accounting comparison, never an investment verdict. */
export function compareFinancialEvidence(input: {
  records: EvidenceRecord[]; contexts: FilingContext[]; now: string
}): FinancialComparison {
  const reasons: string[]=[]
  let review=false
  const chosen=new Map<string,EvidenceRecord>()
  const ids=new Set<string>()
  for(const r of input.records){
    if(ids.has(r.id)){review=true;reasons.push(`证据编号重复：${r.id}`)}
    ids.add(r.id)
  }
  const rows: FinancialComparison['rows']=COMPARISON_METRICS.map(m=>({
    metric:m.key,label:m.label,unit:'元',derived:false,formula:'2025年年度报告原始披露金额',
    values:COMPARISON_STOCKS.map(s=>{
      const candidates=input.records.filter(r=>r.stockCode===s.code && r.kind==='filing' && r.metric===m.key
        && r.period==='2025年度' && r.currency==='CNY' && r.unit==='元' && r.scope===m.scope && isUsableRecord(r,input.now))
      if(candidates.length>1){review=true;reasons.push(`${s.name} ${m.label}存在多条同口径来源，需复核冲突或重复`)}
      if(candidates.length!==1){
        reasons.push(`${s.name}缺少唯一、有效、2025年度/CNY/元且合并口径一致的${m.label}`)
        return {stockCode:s.code,stockName:s.name,value:null,evidenceIds:[],note:'口径不匹配、资料缺失或来源不唯一'}
      }
      const r=candidates[0];chosen.set(`${s.code}:${m.key}`,r)
      return {stockCode:s.code,stockName:s.name,value:r.value,evidenceIds:[r.id]}
    })
  }))
  const status=review ? 'review_required' : chosen.size===6 ? 'comparable' : 'limited'
  for(const d of [
    {key:'parentProfitToRevenue',label:'归母净利润 / 营业收入',num:'netProfit',den:'revenue',unit:'%',scale:100,formula:'归母净利润 ÷ 营业收入 × 100%'},
    {key:'ocfToParentProfit',label:'经营现金流 / 归母净利润',num:'ocf',den:'netProfit',unit:'倍',scale:1,formula:'合并经营活动现金流量净额 ÷ 归母净利润'},
    {key:'ocfToRevenue',label:'经营现金流 / 营业收入',num:'ocf',den:'revenue',unit:'%',scale:100,formula:'合并经营活动现金流量净额 ÷ 营业收入 × 100%'},
  ]){
    rows.push({metric:d.key,label:d.label,unit:d.unit,derived:true,formula:d.formula,values:COMPARISON_STOCKS.map(s=>{
      const n=chosen.get(`${s.code}:${d.num}`),den=chosen.get(`${s.code}:${d.den}`)
      const base={stockCode:s.code,stockName:s.name,evidenceIds:[n?.id,den?.id].filter((id): id is string=>!!id)}
      if(status!=='comparable') return {...base,value:null,note:'双方完整同口径资料未就绪，暂停派生指标比较'}
      if(!n || !den || den.value===null || den.value<=0) return {...base,value:null,note:'分母为零、负值或缺失，比率不适用'}
      const value=n.value!/den.value*d.scale
      return Number.isFinite(value) ? {...base,value} : {...base,value:null,note:'计算结果非有限值'}
    })})
  }
  const contexts=input.contexts.filter(c=>COMPARISON_STOCKS.some(s=>s.code===c.stockCode)
    && c.period==='2025年度' && c.verification==='source_checked' && !!safeSourceUrl(c.sourceUrl) && !!c.locator && !!c.excerpt
    && input.records.some(r=>r.stockCode===c.stockCode && r.period===c.period && r.documentSha256===c.documentSha256 && r.sourceUrl===c.sourceUrl && isUsableRecord(r,input.now))
    && dateValid(c.publishedAt) && Date.parse(c.publishedAt)<=Date.parse(input.now)
    && dateValid(c.validUntil) && Date.parse(c.validUntil)>=Date.parse(input.now))
  const observations: string[]=[]
  if(status==='comparable'){
    const margin=rows.find(r=>r.metric==='parentProfitToRevenue')!
    const [a,b]=margin.values
    if(a.value!==null && b.value!==null) observations.push(`归母净利润/营业收入：贵州茅台${a.value.toFixed(2)}%，五粮液${b.value.toFixed(2)}%；差${Math.abs(a.value-b.value).toFixed(2)}个百分点。该比率衡量归母利润占收入比例。`)
    const cash=rows.find(r=>r.metric==='ocfToParentProfit')!.values
    if(cash.every(v=>v.value!==null)) observations.push(`经营现金流/归母净利润：贵州茅台${cash[0].value!.toFixed(3)}倍，五粮液${cash[1].value!.toFixed(3)}倍；需结合财务子公司现金流及收入确认说明解读。`)
  }
  for(const stock of COMPARISON_STOCKS){
    if(!contexts.some(c=>c.stockCode===stock.code)) reasons.push(`${stock.name}财务口径附注未完成来源核对，解读仍有缺口`)
  }
  return {caseId:'D02',status,period:'2025年度',currency:'CNY',canPublishDecision:false,rows,reasons,observations,contexts,
    limitations:[
      '归母净利润/营业收入包含归属差异，不等同于合并净利率；归母净利润已扣除少数股东损益。',
      '合并经营现金流/归母净利润的分子与分母归属范围不同，只作辅助观察；现金流包含少数股东对应业务及财务子公司。',
      '双方使用相同报告期、币种、金额单位和字段定义；财务子公司、会计处理及经营结构仍存在差异。',
      '展示金额换算为亿元时保留两位小数，比率和差值均按未舍入原始金额计算，显示差值可能与已舍入比率的相减结果不同。',
      '仅依据六项年度金额与已登记附注，不能据此判断利润可持续性或投资优劣；需进一步分析扣非利润、营运资金和现金流构成。',
      '未执行行情估值、多智能体分析或风控审查；年度资料不代表最新季报，团队独立复核待完成。',
    ]}
}

export function buildFinancialComparisonReport(input: {
  comparison: FinancialComparison; runId: string; capturedAt: string; records: EvidenceRecord[]
}): string {
  const c=input.comparison
  const lines=['# 茅台—五粮液：2025年度财务证据对比','',`案例：${c.caseId}；运行编号：${input.runId}`,
    `运行时间：${input.capturedAt}；报告期：${c.period}；币种：${c.currency}`,'',
    `资料状态：${c.status==='comparable' ? '双方基础数据同口径，可进行限定范围的财务对比' : c.status==='review_required' ? '需复核冲突或重复来源' : '资料不足，派生比较暂停'}`,
    '本报告由登记原文和确定性公式生成，不生成最终投资评级、置信度或仓位建议。','',
    ...c.reasons.map(r=>`- ${md(r)}`),'','## 原始金额与派生指标','']
  for(const r of c.rows){
    lines.push(`### ${r.label}`,'',`口径/公式：${r.formula}；单位：${r.unit}`,
      ...r.values.map(v=>`- ${v.stockName}：${v.value===null ? '不适用/待补' : v.value.toLocaleString('zh-CN',{minimumFractionDigits:r.derived ? (r.unit==='倍' ? 3 : 2) : 2,maximumFractionDigits:r.derived ? (r.unit==='倍' ? 3 : 2) : 2})} ${r.unit}；输入证据：${v.evidenceIds.join('、') || '无'}${v.note ? `；${v.note}` : ''}`),'')
  }
  lines.push('## 可直接观察的结果','',...c.observations.map(o=>`- ${o}`),'',
    '## 影响解读的年报说明','',...c.contexts.flatMap(n=>[
      `- ${md(n.summary)}（${n.id}）`,
      `  来源：[${md(n.source)}](${safeSourceUrl(n.sourceUrl)}#page=${n.page})；${md(n.locator)}；文件SHA-256：${n.documentSha256}。`,
    ]),'','## 六项原始资料的定位','',...input.records.map(r=>
      `- ${r.id}：[${md(r.source)}](${safeSourceUrl(r.sourceUrl)}#page=${r.page})；${md(r.locator)}；原值${r.value} ${r.unit}；采集${r.capturedAt}；SHA-256 ${r.documentSha256 ?? '待补'}。`),
    '','## 边界与后续复核','',...c.limitations.map(l=>`- ${l}`))
  return lines.join('\n')
}
