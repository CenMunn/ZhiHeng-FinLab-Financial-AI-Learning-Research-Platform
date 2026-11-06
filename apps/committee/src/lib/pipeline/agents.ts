import type { EvidenceItem, MacroSnapshot, NewsItem, StockProfile, VoteType } from '@/lib/types'
import { chatJSON, chatText, tryChatJSON, withLLMTrace, type LLMProvider } from '@/lib/ai/llm'
import type { KlineBar, LiveQuote } from '@/lib/data/quotes'
import type { QuantMetrics } from './quant'
import { investmentScore, cashInterpretationIssues, reviewCashWarnings, CASH_QUALITY_ISSUE } from '@/lib/research/investment-score'
import { SLANG_TERMS_COUNT } from '@/lib/data/slang-dictionary'
import { isUsableRecord, isRiskPayloadValid, isAgentPayloadValid, normalizeDebateTurn, reviewFinancialSemantics, FINANCIAL_SEMANTIC_RULE, type EvidenceRecord, type FilingContext } from '@/lib/research-evidence/engine'
import { REPORTING_SCOPE_RULE, COMPACT_SOURCE_SYSTEM, reviewReportingClaims, recordReportingScope } from '@/lib/research-evidence/scope'

/**
 * Agent 定义（提示词 + 结构化输出）
 * 规则：财务数字只来自数据包，LLM 不生成任何数字类事实；无数据 → Data unavailable
 */

export interface DataPack {
  evidenceRecords?: EvidenceRecord[]
  evidenceAsOf?: string
  filingContexts?: FilingContext[]
  stock: StockProfile | null
  stockName: string
  stockCode: string | null
  market: string | null
  macro: MacroSnapshot
  news: NewsItem[]
  newsSearchStatus: 'ok' | 'empty' | 'failed'
  /** 财务线索（快照库未收录标的的真实检索结果，引用时必须标注来源） */
  financialClues?: NewsItem[]
  /** 市场热词解析上下文（易中天/茅指数等）：由确定性词典生成，注入给全部 Agent 防止误解 */
  hotTermNote?: string
  /** 市场黑话注释（股票黑话大词典命中）：行话白话解释，注入给全部 Agent 保证理解一致 */
  slangNote?: string
  /** 指数知识块（《全球指数大全》命中）：指数定义/层级关系/实时源说明 */
  indexNote?: string
  /** 热门标的快照库身份（3000 宇宙命中，limited 模式下的行业/收录标签） */
  universeNote?: string
  question: string
  focus?: string
  quant?: QuantMetrics
  /** 行情与日线已通过来源、时间和样本门槛后，允许量化 Agent 解读代码结果。 */
  quantitativeReady?: boolean
  technicalReady?: boolean
  live?: { quote: LiveQuote | null; kline: KlineBar[] } | null
}

export interface AgentOutput {
  score: number | null
  vote: VoteType | null
  confidence: number | null
  summary: string
  highlights: string[]
  concerns: string[]
  evidence: EvidenceItem[]
  details?: Record<string, unknown>
}

const JSON_RULE =
  '只输出一个合法 JSON 对象（UTF-8 中文），不要 markdown 围栏，不要解释文字。'
const EVIDENCE_SCHEMA = '{"claim":"与原值直接对应的事实和范围","evidenceId":"目录中的单个证据编号","value":"原始数字","unit":"原样单位","currency":"原样币种","period":"原样报告期","reportingScope":"consolidated|parent_company|segment|unknown，与登记一致"}'

const AGENT_BASE_RULE = `你是专业基金公司的资深分析师。遵守：
1) 所有数字类事实只能引用【数据包】中给出的数据，禁止编造或凭记忆生成数字。
2) 数据包中没有的数据，写 "Data unavailable"，不得猜测。
3) 结论必须可解释：每个判断都能对应数据包中的证据。
4) evidence中的每个数值引用必须填写 evidenceId、value（只含原始数字）、unit、currency、period；原样对应【证据目录】。source和核验状态由服务器回填，不得自行声称已核验。
5) 没有登记证据的数字不作事实；定性推断标注为推断。演示快照、检索摘要和未完成核验的量化值不能作为正式评级依据。
6) 每条数值引用只使用单个证据编号，不能拼接多个编号或自造derived编号。自算比率放在details并标为推算；没有独立登记的计算证据时，不放入evidence，也不得称为已核验。
7) 资料缺口写入concerns；定性推断写入summary或details。不得把Data unavailable、null或无来源的定性结论塞入数值evidence。找不到可引用原值时evidence为[]，不要补造证据编号。
8) claim只描述该证据原值支持的字段、主体和报告期；涉及另一主体或派生值时另行解释，不能让单条原始金额替整个复合判断背书。
9) 经营现金流是收支净额，不称为销售回款总额或回款规模。所给利润是归母净利润时必须说全，不能把与其比值更高直接解释成现金转化或回款质量更好。
10) 语言精炼、专业，中文输出。${JSON_RULE}
${FINANCIAL_SEMANTIC_RULE}
${REPORTING_SCOPE_RULE}`

/** 实时行情块：腾讯行情接口的真实数据，注入给每个 Agent（数据可信度机制） */
function liveBlock(p: DataPack): string {
  if (p.evidenceRecords && !p.quantitativeReady) return '\n【行情边界】日线技术指标已登记在证据目录；正式估值评分仍含未核对快照字段，不能用于本轮评级或仓位建议。'
  const live = p.live
  if (!live) return ''
  const q = live.quote
  if (!q) return ''
  const klineTail = (live.kline ?? []).slice(-10).map((b) => `${b.date} O${b.open} H${b.high} L${b.low} C${b.close}`)
  const ma = p.quant
  return `\n【实时行情（数据源：腾讯财经，采集时间 ${q.time}）】
${JSON.stringify(
    {
      现价: q.price,
      涨跌: `${q.change > 0 ? '+' : ''}${q.change}（${q.changePct > 0 ? '+' : ''}${q.changePct}%）`,
      今开: q.open,
      昨收: q.prevClose,
      最高_最低: `${q.high}/${q.low}`,
      成交量_手: q.volume,
      成交额_万: q.amount,
      换手率: q.turnoverRate !== null ? `${q.turnoverRate}%` : null,
      市盈率TTM: q.peTtm,
      市净率: q.pb,
      总市值_亿: q.marketCap,
      '52周高_低': q.high52w && q.low52w ? `${q.high52w}/${q.low52w}` : null,
      量化引擎_真实K线计算: ma
        ? {
            数据源: ma.dataSource === 'live' ? '真实日K线' : '混合',
            RSI14: ma.rsi14,
            MA20: ma.ma20,
            MA60: ma.ma60,
            近1月涨跌: ma.changes.m1,
            近3月涨跌: ma.changes.m3,
            近6月涨跌: ma.changes.m6,
            近1年涨跌: ma.changes.y1,
            年化波动率: ma.volatilityAnnualPct,
            '52周位置': `${ma.pos52w}/100`,
          }
        : null,
      近10个交易日K线: klineTail,
      可信度说明: p.evidenceRecords ? '行情来源、采集时间和日线样本已登记；量化指标由代码计算，可引用证据目录中的对应编号。' : '本块数据为行情接口实时采集；与快照库冲突时以本块为准。',
    },
    null,
    1,
  )}`
}

/** 财务线索块：真实检索到的营收/利润/估值线索（来源可查，非编造） */
function clueBlock(p: DataPack): string {
  const clues = p.financialClues ?? []
  if (clues.length === 0) return ''
  return `\n【财务线索（web_search 真实检索结果）】${JSON.stringify(
    clues.map((c) => ({ 线索: c.title, 来源: c.source, 日期: c.date ?? '', 摘要: c.summary ?? '' })),
    null,
    1,
  )}\n（以上为可引用的真实检索线索，引用时标注“新闻来源数据”）`
}

function stockBlock(p: DataPack): string {
  if (p.evidenceRecords) {
    const records=p.evidenceRecords.filter(r=>r.kind==='filing' && isUsableRecord(r,p.evidenceAsOf ?? new Date().toISOString()))
    return JSON.stringify({公司名称:p.stockName,股票代码:p.stockCode,
      财务资料:records.map(r=>({evidenceId:r.id,主体股票代码:r.stockCode,指标:r.label,value:r.value,unit:r.unit,currency:r.currency,period:r.period,scope:r.scope})),
      会计口径说明:(p.filingContexts??[]).map(r=>({主体股票代码:r.stockCode,period:r.period,summary:r.summary,excerpt:r.excerpt,source:r.source,page:r.page,sourceUrl:r.sourceUrl,documentSha256:r.documentSha256})),
      资料边界:'仅上述财务字段经过原始来源核对；其他财务、行业规模及预测均未核验。年度数据不代表最新季报；不得从模型记忆补数。'},null,1)
  }
  if (!p.stock) {
    return `【公司财务数据】快照库未收录该标的完整财务档案。${
      p.universeNote ? `${p.universeNote}\n` : ''
    }${clueBlock(p)}\n除上述检索线索外，其余财务数字 Data unavailable：仅可依据实时行情、检索线索与行业常识做定性判断，禁止编造快照之外的财务数字；引用线索数字必须注明“新闻来源数据”。`
  }
  const s = p.stock
  // 指数研究模式：无公司财务口径，估值/财务段位替换为指数说明（避免 0 值误导）
  if (s.industry === '指数') {
    return JSON.stringify(
      {
        研究对象类型: '股票指数（非公司，无 PE/营收/利润等公司财务口径）',
        指数概况: s.description,
        展示市场: `${s.market} / ${s.currency}`,
        点位与走势: '以【实时行情】块的指数点位/涨跌/真实K线为准',
        分析要求: '围绕指数点位位置、趋势结构、成分风格、宏观与资金面、历史波动展开；禁止引用公司财务数据；估值/盈利维度写 Data unavailable 或跳过。',
      },
      null,
      1,
    )
  }
  return JSON.stringify(
    {
      公司概况: s.description,
      行业: s.industry,
      市场与币种: `${s.market} / ${s.currency}`,
      现价: s.price,
      当日涨跌: `${s.changePct}%`,
      总市值: `${s.marketCap} 亿(CNY口径)`,
      估值: {
        PE: s.valuation.pe,
        PE_5年分位: s.valuation.pePercentile !== null ? `${s.valuation.pePercentile}%` : '亏损无意义',
        PB: s.valuation.pb,
        股息率: `${s.valuation.dividendYield}%`,
        同业平均PE: s.valuation.peerAvgPe,
      },
      财务_最新年度: {
        营收: `${s.financials.revenue} 亿`,
        营收增速: `${s.financials.revenueGrowth}%`,
        归母净利: `${s.financials.netProfit} 亿`,
        净利增速: `${s.financials.profitGrowth}%`,
        毛利率: `${s.financials.grossMargin}%`,
        净利率: `${s.financials.netMargin}%`,
        ROE: `${s.financials.roe}%`,
        资产负债率: `${s.financials.debtRatio}%`,
        经营现金流: `${s.financials.ocf} 亿`,
      },
      近三年趋势: s.history,
      技术面: {
        近1月: `${s.technicals.change1m}%`,
        近3月: `${s.technicals.change3m}%`,
        近6月: `${s.technicals.change6m}%`,
        近1年: `${s.technicals.change1y}%`,
        '52周高/低': `${s.technicals.high52w}/${s.technicals.low52w}`,
        均线状态: s.technicals.maTrend,
        RSI14: s.technicals.rsi14,
        波动性: s.technicals.volatility,
      },
      行业背景: s.industryContext,
      竞争地位: s.competitive,
      已知风险: s.risks,
      潜在催化: s.catalysts,
      数据来源说明: '公司 2024 年年度报告及 2025Q3 季报演示快照库（近似值）',
    },
    null,
    1,
  )
}

/** 组合数据包文本：基础块 + 实时行情块 */
function packBlock(p: DataPack): string {
  return `${stockBlock(p)}${liveBlock(p)}${p.evidenceRecords ? `\n【证据目录】\n${JSON.stringify(p.evidenceRecords.filter(r=>r.kind!=='demo').map(r=>({...r,reportingScope:recordReportingScope(r)})))}\n目录中的 verification 是来源登记状态，不代表你的论点已通过核验；scope=parent_attributable是合并报表归属指标，不能称母公司单体。` : ''}`
}

function macroBlock(p: DataPack): string {
  if (p.evidenceRecords) return '【宏观数据】本轮尚未提供经核对的宏观披露，数字 Data unavailable。不得使用旧演示快照作事实。'
  return JSON.stringify({ 宏观快照: p.macro, 快照说明: '公开宏观数据整理的演示快照' }, null, 1)
}

function newsBlock(p: DataPack): string {
  if (p.news.length === 0) {
    return `【实时新闻】${
      p.newsSearchStatus === 'failed' ? '检索失败' : '未检索到结果'
    }。请基于已有定性信息分析，并在 evidence 中注明 Data unavailable。`
  }
  return JSON.stringify(
    {
      实时新闻: p.news.map((n) => ({ 标题: n.title, 来源: n.source, 日期: n.date ?? '', 摘要: n.summary ?? '' })),
      来源说明: '公开资讯接口或网络检索结果，具体来源与发布时间见逐条记录；新闻摘要不等同于已核验财务事实。',
    },
    null,
    1,
  )
}

function questionBlock(p: DataPack): string {
  return `【研究任务】用户问题："${p.question}"${p.focus ? `（重点关注：${p.focus}）` : ''} 研究对象：${p.stockName}${
    p.stockCode ? `(${p.stockCode})` : ''
  }${p.hotTermNote ? `\n【热词解析——必须遵守】${p.hotTermNote}` : ''}${
    p.slangNote
      ? `\n【市场黑话注释——系统内置 ${SLANG_TERMS_COUNT} 条词典自动匹配】${p.slangNote}`
      : ''
  }${p.indexNote ? `\n【指数知识库——《全球指数大全》】${p.indexNote}` : ''}`
}

// ---------- 通用输出解析 ----------

function parseAgentOutput(raw: Record<string, unknown>, fallbackName: string): AgentOutput {
  const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? Math.round(v) : null)
  const strArr = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()).map((x) => String(x).trim()).slice(0, 5) : []
  const voteRaw = typeof raw.vote === 'string' ? raw.vote.toUpperCase() : ''
  const vote: VoteType | null = ['BUY', 'HOLD', 'SELL'].includes(voteRaw) ? (voteRaw as VoteType) : null
  const evRaw = Array.isArray(raw.evidence) ? raw.evidence : []
  const evidence: EvidenceItem[] = []
  for (const e of evRaw) {
    if (typeof e !== 'object' || e === null) continue
    const o = e as Record<string, unknown>
    const claim = String(o.claim ?? o.论点 ?? '').slice(0, 120)
    if (!claim) continue
    const conf = o.confidence
    evidence.push({
      claim,
      evidenceId: typeof o.evidenceId === 'string' ? o.evidenceId.slice(0,160) : undefined,
      unit: typeof o.unit === 'string' ? o.unit.slice(0,30) : undefined,
      currency: typeof o.currency === 'string' ? o.currency.slice(0,10) : undefined,
      period: typeof o.period === 'string' ? o.period.slice(0,60) : undefined,
      reportingScope: ['consolidated','parent_company','segment','unknown'].includes(String(o.reportingScope)) ? o.reportingScope as EvidenceItem['reportingScope'] : undefined,
      value: o.value !== undefined ? String(o.value).slice(0, 60) : undefined,
      source: o.source !== undefined ? String(o.source).slice(0, 80) : undefined,
      confidence: conf === 'High' || conf === 'Medium' || conf === 'Low' ? conf : undefined,
    })
  }
  evidence.splice(4)

  const score = num(raw.score)
  return {
    score: score !== null ? Math.max(0, Math.min(100, score)) : null,
    vote,
    confidence: num(raw.confidence),
    summary: typeof raw.summary === 'string' ? raw.summary.slice(0, 300) : `${fallbackName}分析完成`,
    highlights: strArr(raw.highlights),
    concerns: strArr(raw.concerns),
    evidence,
    details: typeof raw.details === 'object' && raw.details !== null ? (raw.details as Record<string, unknown>) : undefined,
  }
}

const SCORE_RULE = `评分是本角色对投资吸引力的主观判断，越高越看好；不是上涨概率。score必须是0到100的整数，confidence为0到100整数。先利用给定资料形成与本角色有关的条件性判断：公司财报、现金流和已核对技术资料也可提供间接线索；缺少行业、宏观或新闻专用资料，不是自动放弃评分的理由。间接评分必须说清观察角度和假设，不能冒充当期行业景气、宏观状态或已发生的新闻，confidence不高于40。只有完全没有可用信息或没有任何可解释的判断时score=50、confidence=0，并在details.scoreReason说明无法判断；不得把50说成市场中性。充分直接资料时confidence不高于80。details.scoreReason用一句人话解释分数，不自算财务比率或新增数字。评分数字可生成，财务事实数字只能来自给定资料。vote为null，不以估计分发布买卖指令。summary不超过80字，先说判断；具体缺口放concerns。`

function scoredRun<T extends {output:AgentOutput;error:Error|null}>(run:T,pack:DataPack|undefined,role?:string):T {
  if(!pack||!role)return run
  const now=pack.evidenceAsOf??new Date().toISOString()
  const records=(pack.evidenceRecords??[]).filter(r=>isUsableRecord(r,now)&&r.kind!=='demo')
  const filings=records.filter(r=>r.kind==='filing')
  const direct=role==='fundamental'?filings.length>=3:role==='industry'?records.some(r=>/^industry|market_share/.test(r.metric)):role==='macro'?records.some(r=>/^macro|interest_rate|cpi|gdp/.test(r.metric)):role==='sentiment'?pack.newsSearchStatus==='ok'&&pack.news.length>0:false
  const hasDirection=direct||records.length>0||(pack.filingContexts??[]).some(c=>c.verification==='source_checked'&&Date.parse(c.publishedAt)<=Date.parse(now)&&Date.parse(c.validUntil)>=Date.parse(now))
  const policy=investmentScore({score:run.output.score,confidence:run.output.confidence,hasDirection,direct:direct&&role!=='fundamental',failed:!!run.error,reason:typeof run.output.details?.scoreReason==='string'?run.output.details.scoreReason:run.output.summary})
  const baselineSummaries:Record<string,string>={industry:'行业判断重点看需求、竞争和回款变化；目前先按基准值观察，不对景气与排名作方向判断。',macro:'目前不对宏观方向下注。利率、政策与需求变化，是接下来最值得跟踪的变量。',sentiment:'暂时没有可用的事件信号，后续重点关注业绩披露、经营变化与监管消息。'}
  if(policy.basis==='baseline'&&!run.error&&baselineSummaries[role]){
    const original={summary:run.output.summary,highlights:run.output.highlights,concerns:run.output.concerns,evidence:run.output.evidence}
    run.output={...run.output,summary:baselineSummaries[role],highlights:[],concerns:[],evidence:[],details:{...run.output.details,baselineAnalysis:original,displaySummarySource:'baseline_template'}}
  }
  run.output={...run.output,score:policy.score,confidence:policy.confidence,vote:null,details:{...run.output.details,scoreKind:'investment_attractiveness',scoreBasis:policy.basis,scoreReason:policy.reason}}
  return run
}

async function runAgent<T extends Record<string, unknown>>(
  system:string,user:string,fallback:(e:Error)=>AgentOutput,timeoutMs=120_000,provider:LLMProvider='deepseek',pack?:DataPack,role?:string,
):Promise<{output:AgentOutput;raw:T|null;error:Error|null;durationMs:number}>{
  const started=Date.now(),calls:unknown[]=[],attempts:{candidate:unknown;issues:unknown[]}[]=[],polarityReviews:unknown[]=[]
  try {
    const instruction=system+(role?'\n'+SCORE_RULE+'\n置信度大于0时，50分也属于条件性判断，不称为基准值。只有confidence=0才称基准值。评分理由只写判断理由，不重复score、confidence、vote等字段名或数字。':'')
    let result=await withLLMTrace(()=>chatJSON<T>(instruction,user,timeoutMs,provider))
    calls.push(...result.calls)
    for(let attempt=0;attempt<2;attempt++){
      const parsed=result.value
      if(!isAgentPayloadValid(parsed))throw new Error('AGENT_OUTPUT_INVALID')
      const attributableOnly=!!pack?.evidenceRecords?.some(r=>r.metric==='netProfit'&&r.scope==='parent_attributable')
      const details=parsed.details as Record<string,unknown>|undefined
      const texts=[parsed.summary,...(Array.isArray(parsed.highlights)?parsed.highlights:[]),...(Array.isArray(parsed.concerns)?parsed.concerns:[]),details?.scoreReason].filter((x):x is string=>typeof x==='string')
      let issues=pack?[...reviewFinancialSemantics(parsed,{records:pack.evidenceRecords??[],contexts:pack.filingContexts??[],now:pack.evidenceAsOf??new Date().toISOString()}).issues,...reviewReportingClaims(parsed,{records:pack.evidenceRecords??[],contexts:pack.filingContexts??[]}).issues,...cashInterpretationIssues(texts,attributableOnly).map(message=>({code:'CASH_FLOW_INTERPRETATION',message}))]:[]
      if(role&&issues.length){
        const polarity=await reviewCashWarnings(texts,issues.map(i=>i.message),(s,u)=>withLLMTrace(()=>chatJSON(s,u,45_000,provider)))
        calls.push(...polarity.calls)
        if(polarity.eligible){const {calls:reviewCalls,...metadata}=polarity;polarityReviews.push({...metadata,programIssues:issues})}
        if(polarity.accepted)issues=issues.filter(i=>i.message!==CASH_QUALITY_ISSUE)
      }
      attempts.push({candidate:parsed,issues})
      if(issues.length&&attempt===0&&role){
        try {
          result=await withLLMTrace(()=>chatJSON<T>(instruction+'\n你现在复核并修正自己的候选分析。按给定原页及检查问题修正年度、范围和因果判断。删除资料不支持的断言，保留有用观点。返回同样JSON，不声称人工审核通过。',JSON.stringify({sourceInput:user,originalCandidate:parsed,issues}),timeoutMs,provider))
          calls.push(...result.calls);continue
        }catch(e){calls.push(...((e as {llmCalls?:unknown[]})?.llmCalls??[]))}
      }
      const review={status:issues.length?'review_required':attempt?'model_repaired':polarityReviews.length?'model_reviewed':'no_issue_detected',issues,attempts,polarityReviews,completeSemanticVerification:false}
      const out=parseAgentOutput(parsed,fallback(new Error('parse')).summary)
      if(!issues.length&&role&&(out.score===null||(out.confidence===0&&pack?.evidenceRecords?.some(r=>isUsableRecord(r,pack.evidenceAsOf??new Date().toISOString()))))){
        try{
          const scoring=await withLLMTrace(()=>chatJSON<{score:number;confidence:number;scoreReason:string}>(SCORE_RULE+'只返回JSON：{"score":整数,"confidence":整数,"scoreReason":"一句理由"}。这是有限资料下的条件性投资判断，不能因资料不完整一律返回null；完全无方向性信息才给50分基准值。',JSON.stringify({role,sourceInput:user,acceptedAnalysis:parsed}),60_000,provider))
          calls.push(...scoring.calls)
          out.score=typeof scoring.value.score==='number'&&Number.isFinite(scoring.value.score)?Math.round(Math.max(0,Math.min(100,scoring.value.score))):null
          out.confidence=typeof scoring.value.confidence==='number'?scoring.value.confidence:null
          out.details={...out.details,scoreReason:scoring.value.scoreReason,scoreCandidate:scoring.value}
          let scoreReviewIssues=cashInterpretationIssues([typeof scoring.value.scoreReason==='string'?scoring.value.scoreReason:''],attributableOnly)
          if(scoreReviewIssues.length){
            const polarity=await reviewCashWarnings([scoring.value.scoreReason],scoreReviewIssues,(s,u)=>withLLMTrace(()=>chatJSON(s,u,45_000,provider)))
            calls.push(...polarity.calls)
            out.details.scorePolarityReview={accepted:polarity.accepted,assessment:polarity.assessment,passages:polarity.passages}
            if(polarity.accepted)scoreReviewIssues=scoreReviewIssues.filter(i=>i!==CASH_QUALITY_ISSUE)
          }
          if(scoreReviewIssues.length){out.score=null;out.confidence=0;out.details={...out.details,scoreReason:'评分解释存在口径问题，暂按基准值展示。',scoreReviewIssues}}
        }catch(e){calls.push(...((e as {llmCalls?:unknown[]})?.llmCalls??[]))}
      }
      out.details={...out.details,llmCalls:calls,semanticReview:review}
      if(issues.length){
        return scoredRun({output:{...neutralFallback('当前解释仍有矛盾，先查看财报原值。'),concerns:issues.map(i=>i.message),details:{llmCalls:calls,semanticReview:{...review,originalOutput:parsed}}},raw:parsed,error:new Error('FINANCIAL_SEMANTIC_REVIEW_REQUIRED'),durationMs:Date.now()-started},pack,role)
      }
      return scoredRun({output:out,raw:parsed,error:null,durationMs:Date.now()-started},pack,role)
    }
    throw new Error('AGENT_OUTPUT_INVALID')
  }catch(e){
    const error=e instanceof Error?e:new Error('AGENT_FAILED')
    calls.push(...((e as {llmCalls?:unknown[]})?.llmCalls??[]))
    const safe=/^[A-Z][A-Z0-9_]+$/.test(error.message)?error.message:'AGENT_OUTPUT_INVALID'
    return scoredRun({output:{...fallback(error),concerns:[`调用或输出校验失败：${safe}`],details:{llmCalls:calls,errorCode:safe,attempts}},raw:null,error,durationMs:Date.now()-started},pack,role)
  }
}
function neutralFallback(summary:string):AgentOutput{return {score:null,vote:null,confidence:null,summary,highlights:[],concerns:[],evidence:[]}}

// ---------- 5 个分析 Agent ----------

export async function fundamentalAgent(p: DataPack) {
  const system = `${AGENT_BASE_RULE}

你的角色：基本面分析师（Fundamental Analyst）。研究公司经营质量：营收与利润增长、毛利率/净利率、ROE、现金流质量、资产负债表健康度、盈利稳定性与趋势。

输出 JSON 字段：
{"score": 0-100或null, "vote": "BUY|HOLD|SELL或null", "confidence": 0-100或null, "summary": "≤80字，只答用户所问", "highlights": ["仅有明确来源的必要结论，可为空"], "concerns": ["影响所问答案的资料缺口，可为空"], "evidence": [${EVIDENCE_SCHEMA}], "details": {"quality":"仅在用户询问且有据时说明，否则null","growth":"仅在用户询问且有据时说明，否则null"}}`
  const user = `${questionBlock(p)}\n\n${packBlock(p)}\n\n${newsBlock(p)}`
  return runAgent(system, user, () => neutralFallback('基本面分析生成失败，已降级处理'),120_000,'deepseek',p,'fundamental')
}

export async function focusedSourceAgent(p: DataPack) {
  const system=`${COMPACT_SOURCE_SYSTEM}
产品证据：每个evidence只引用登记目录的单个evidenceId，value/unit/currency/period原样；没有对应原值不自造编号。计算放details并注明推算。资料缺口放concerns。score/vote/confidence均为null。
只输出合法JSON：{"score":null,"vote":null,"confidence":null,"summary":"所问结论","highlights":[],"concerns":[],"evidence":[${EVIDENCE_SCHEMA}],"details":{}}`
  return runAgent(system,`${questionBlock(p)}\n\n${packBlock(p)}`,()=>neutralFallback('财报核对失败，原始结果待复核'),120_000,'deepseek',p)
}

export async function industryAgent(p: DataPack) {
  const system = `${AGENT_BASE_RULE}

你的角色：行业分析师（Industry Analyst）。研究行业空间与增速、所处生命周期、竞争格局与集中度、公司行业地位与护城河、上下游关系。

输出 JSON 字段：
{"score": 0-100 行业与竞争地位分, "vote": "BUY|HOLD|SELL", "confidence": 0-100, "summary": "≤80字核心结论（含行业景气度判断）", "highlights": ["3-4条"], "concerns": ["2-3条"], "evidence": [${EVIDENCE_SCHEMA}], "details": {"景气度":"如 中性偏弱","行业地位":"如 行业Top3","核心壁垒":"如 品牌+渠道"}}`
  const user = `${questionBlock(p)}\n\n${packBlock(p)}\n\n${newsBlock(p)}`
  const missing=!!p.evidenceRecords&&!p.evidenceRecords.some(r=>/^industry|market_share|industry_growth/.test(r.metric)&&isUsableRecord(r,p.evidenceAsOf??new Date().toISOString()))
  const run=await runAgent(system+(missing?'\n本轮没有已核对行业数据：不能编造行业景气、份额或排名。用一两句解释行业研究最重要的观察点，不重复财报金额，不把某家公司的会计事项推广至所有公司。可解释条件性竞争逻辑；没有方向信息时给50分基准值，不将其视为中性行业判断。':''), user, () => neutralFallback('行业分析生成失败，已降级处理'),120_000,'deepseek',p,'industry')
  return run
}

export async function macroAgent(p: DataPack) {
  const system = `${AGENT_BASE_RULE}

你的角色：宏观策略分析师（Macro Analyst）。基于宏观快照判断当前环境（Risk On / Neutral / Risk Off），以及宏观因素对该公司的传导路径（利率、流动性、消费、政策、汇率、行业政策）。

输出 JSON 字段：
{"score": 0-100 宏观环境对该股友好度, "vote": "BUY|HOLD|SELL", "confidence": 0-100, "summary": "≤80字核心结论（含环境判断）", "highlights": ["利好因素2-3条"], "concerns": ["利空因素2-3条"], "evidence": [${EVIDENCE_SCHEMA}], "details": {"环境":"Risk On|Neutral|Risk Off","传导":"一句话传导路径"}}`
  const user = `${questionBlock(p)}\n\n${macroBlock(p)}\n\n${packBlock(p)}\n\n${newsBlock(p)}`
  const run=await runAgent(system+(p.evidenceRecords?'\n本轮宏观资料未经核对，不能断言当前宏观状态。用自然语言解释最相关的一个条件性传导，不重复现金流数字；没有方向信息时给50分基准值，不把假设写成事实。':''), user, () => neutralFallback('宏观分析生成失败，已降级处理'),120_000,'deepseek',p,'macro')
  return run
}

export async function quantAgent(p: DataPack, q: QuantMetrics) {
  if (p.evidenceRecords && !p.quantitativeReady) {
    if(p.technicalReady){
      const records=p.evidenceRecords.filter(r=>r.id.startsWith(`quant:${p.stockCode}:`)&&isUsableRecord(r,p.evidenceAsOf??new Date().toISOString()))
      const momentum=records.find(r=>r.metric==='momentum')
      const output:AgentOutput={score:momentum?.value??50,vote:null,confidence:momentum?70:0,summary:momentum?'已按登记日线计算技术动量与均线指标，仅反映价格走势，不代表估值或预期收益。':'仅展示样本长度足够的登记技术指标；完整动量所需历史不足，按50分基准值展示。',highlights:records.map(r=>`${r.metric}：${r.value} ${r.unit}`),concerns:['同业估值、股息率和历史分位尚未核对，不生成综合估值分或买卖投票。'],evidence:records.map(r=>({claim:r.label,evidenceId:r.id,value:String(r.value),unit:r.unit,currency:r.currency,period:r.period})),details:{scoreKind:'technical_momentum',scoreBasis:momentum?'source_based':'baseline',scoreReason:'仅为代码计算的技术动量分，不是投资评级',calculationEngine:'registered_daily_bars'}}
      return {output,raw:null,error:null,durationMs:0}
    }
    return {output:{...neutralFallback('暂按50分基准值展示，取得足够日线后更新技术判断。'),score:50,confidence:0,details:{scoreKind:'technical_momentum',scoreBasis:'baseline',scoreReason:'信息不足，50分为基准值，不计入综合分。'}},raw:null,error:null,durationMs:0}
  }
  const system = `${AGENT_BASE_RULE}

你的角色：量化分析师（Quant Analyst）。下面给出【代码计算的量化指标】（这些数字是权威的，直接引用，不要修改）：估值吸引力分、动量分、PE/PE分位、PEG、52周位置、RSI、均线状态。你的任务是解读这些指标并给出估值与技术面结论。

输出 JSON 字段：
{"score": 0-100 量化综合分（估值与动量结合）, "vote": "BUY|HOLD|SELL", "confidence": 0-100, "summary": "≤80字（含估值水平与技术趋势判断）", "highlights": ["2-4条"], "concerns": ["2-3条"], "evidence": [${EVIDENCE_SCHEMA}], "details": {"valuation": <直接引用估值吸引力分>, "momentum": <直接引用动量分>, "估值水平":"偏高|合理|偏低", "技术趋势":"如 中性偏强"}}`
  const user = `${questionBlock(p)}

【代码计算的量化指标（权威数据，直接引用）】
${JSON.stringify({ ...q, 均线状态: q.maTrendLabel, 趋势判定: q.trendVerdict }, null, 1)}

${packBlock(p)}`
  const run = await runAgent<{ details?: Record<string, unknown> }>(
    system,
    user,
    () => neutralFallback('量化分析生成失败，已降级处理'),
    120_000,'deepseek',p,
  )
  // 权威数值回填：valuation/momentum 强制使用代码计算值
  if (run.output.details) {
    run.output.details.valuation = q.valuation
    run.output.details.momentum = q.momentum
  } else if (run.raw) {
    run.output.details = { ...(run.raw.details ?? {}), valuation: q.valuation, momentum: q.momentum }
  }
  return run
}

export async function sentimentAgent(p: DataPack) {
  const system = `${AGENT_BASE_RULE}

你的角色：新闻与舆情分析师（News & Sentiment Analyst）。基于【实时新闻】判断近期事件的情绪倾向（正面/中性/负面）、识别关键事件（业绩、政策、产品、风险事件），给出舆情面结论。

输出 JSON 字段：
{"score": 0-100 舆情面得分, "vote": "BUY|HOLD|SELL", "confidence": 0-100, "summary": "≤80字（概括近期新闻主线与情绪）", "highlights": ["正面事件2-3条"], "concerns": ["负面/风险事件2-3条"], "evidence": [${EVIDENCE_SCHEMA}], "details": {"正面事件数": <int>, "负面事件数": <int>, "情绪倾向":"正面|中性|负面"}}`
  const user = `${questionBlock(p)}\n\n${newsBlock(p)}\n\n${packBlock(p)}`
  const missing=p.newsSearchStatus!=='ok'||!p.news.length
  const run=await runAgent(system+(missing?'\n本轮无可用新闻：不能声称观察到实时舆情或已发生事件。可依据给定财报中的已披露事项，评估后续信息敏感性并给条件性投资评分，置信度不高于40；说清评分针对的假设和关注点。完全没有可解释线索时才用50分基准值。':''), user, () => neutralFallback('舆情分析生成失败，已降级处理'),120_000,'deepseek',p,'sentiment')
  return run
}

// ---------- 辩论 Agent ----------

export interface DebateTurn {
  error?: string
  content: string
}

/** 各角色共用 DeepSeek；角色分工不代表模型独立性。 */
const DEBATE_PROVIDER: LLMProvider = 'deepseek'

export async function bullOpening(p: DataPack, agentSummaries: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是投委会中的多头代表（Bull Agent）。基于各分析师的核心观点，提炼"为什么值得投资"的最强论证。150字以内，直接引用分析师给出的数据/论据，语气有力但不夸大。${JSON_RULE}
输出 {"content": "论证内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n各分析师观点：\n${agentSummaries}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function bearOpening(p: DataPack, agentSummaries: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是投委会中的空头代表（Bear Agent）。基于各分析师的核心观点，提炼"为什么不值得投资/最需要警惕什么"的最强论证。150字以内，直接引用分析师给出的数据/论据，尖锐但专业。${JSON_RULE}
输出 {"content": "论证内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n各分析师观点：\n${agentSummaries}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function bullRebuttal(p: DataPack, bearArg: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是多头代表（Bull Agent），这是第 2 轮反驳。请针对空头立论进行反驳（130字以内）。用数据说话，指出空头论点中被忽视的积极因素或过度悲观的假设，仅在证据充足时引用目录数字；资料不足时明确说明，不补造数字。${JSON_RULE}
输出 {"content": "反驳内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n空头立论：${bearArg}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function bearRebuttal(p: DataPack, bullArg: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是空头代表（Bear Agent），这是第 2 轮反驳。请针对多头立论进行反驳（130字以内）。指出多头论点的薄弱假设、兑现门槛与下行风险，仅在证据充足时引用目录数字；资料不足时明确说明，不补造数字。${JSON_RULE}
输出 {"content": "反驳内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n多头立论：${bullArg}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

/** 第 3 轮：交叉质证 — 双方各亮出对方论证链中最薄弱的一环，并用量化数据攻击 */
export async function bullCrossAttack(p: DataPack, bearOpening: string, bearRebuttal: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是多头代表（Bull Agent），第 3 轮交叉质证。请从空头两轮发言中找出【最薄弱的一个论点】（内部矛盾/数据误读/假设站不住），进行定点攻击（130字以内）。要求：先指出对方的具体说法，再用数据包中的量化数据（估值/动量/RSI/行情）反驳，逻辑必须闭环。${JSON_RULE}
输出 {"content": "质证内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n空头第1轮立论：${bearOpening}\n\n空头第2轮反驳：${bearRebuttal}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function bearCrossAttack(p: DataPack, bullOpening: string, bullRebuttal: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是空头代表（Bear Agent），第 3 轮交叉质证。请从多头两轮发言中找出【最薄弱的一个论点】（内部矛盾/数据误读/假设站不住），进行定点攻击（130字以内）。要求：先指出对方的具体说法，再用数据包中的量化数据（估值/波动率/52周位置/技术面）反驳，逻辑必须闭环。${JSON_RULE}
输出 {"content": "质证内容"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n多头第1轮立论：${bullOpening}\n\n多头第2轮反驳：${bullRebuttal}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

/** 第 4 轮：结辩陈词 — 各自总结全场最强论据链，面向投委做最后陈述 */
export async function bullClosingArg(p: DataPack, fullDebate: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是多头代表（Bull Agent），第 4 轮结辩陈词。请面向投委会做最后陈述（140字以内）：提炼全场辩论中你方站得住的最强论据链（基本面→估值/技术面→催化），正面回应对方最强攻击后收尾，给出明确的"为什么现在值得配置"。${JSON_RULE}
输出 {"content": "结辩陈词"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n【全场辩论纪要】\n${fullDebate}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function bearClosingArg(p: DataPack, fullDebate: string): Promise<DebateTurn> {
  const text = await tryChatJSON<{ content?: string }>(
    `你是空头代表（Bear Agent），第 4 轮结辩陈词。请面向投委会做最后陈述（140字以内）：提炼全场辩论中你方站得住的最强论据链（估值/风险/技术面→下行情形），正面回应对方最强攻击后收尾，给出明确的"为什么此刻应该谨慎"。${JSON_RULE}
输出 {"content": "结辩陈词"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n【全场辩论纪要】\n${fullDebate}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return normalizeDebateTurn(text?.content)
}

export async function conflictResolution(
  p: DataPack,
  agentA: string,
  voteA: string,
  argA: string,
  agentB: string,
  voteB: string,
  argB: string,
): Promise<DebateTurn[]> {
  const res = await tryChatJSON<{ a?: string; b?: string }>(
    `投委会检测到两位分析师观点严重冲突，请分别以两位分析师的第一人称口吻进行一轮针对性再论证（各110字以内，直接交锋，引用数据）。${JSON_RULE}
输出 {"a": "${agentA}的再论证", "b": "${agentB}的再论证"}`,
    `研究标的：${p.stockName}${liveBlock(p)}\n\n${agentA}（投票${voteA}）：${argA}\n\n${agentB}（投票${voteB}）：${argB}`,
    180_000,
    DEBATE_PROVIDER,
  )
  return [
    normalizeDebateTurn(res?.a),
    normalizeDebateTurn(res?.b),
  ]
}

// ---------- Risk Officer ----------

export interface RiskOutput extends AgentOutput {
  riskLevel: RiskLevelOut
  riskPenalty: number
  topRisks: string[]
}

type RiskLevelOut = 'Low' | 'Medium' | 'High' | 'Very High'

export async function riskAgent(p: DataPack, agentSummaries: string, debateSummary: string) {
  const system = `${AGENT_BASE_RULE}

你的角色：首席风险官（Risk Officer / CRO）。你的任务不是证明股票值得买，而是尽可能找出投资逻辑的问题：财务异常、盈利质量、债务、政策、行业、估值、黑天鹅、以及各 Agent 之间的观点冲突。你拥有"风险惩罚分"（0-15 分，用于下调最终评分）与风险定级权。

输出 JSON 字段：
{"score": 0-100 风险调整后吸引力分（越高=风险状况越好）, "vote": "BUY|HOLD|SELL", "confidence": 0-100, "riskLevel": "Low|Medium|High|Very High", "riskPenalty": 0-15, "topRisks": ["Top3风险，按严重程度排序"], "summary": "≤80字风控结论", "highlights": ["风险缓释因素1-2条"], "concerns": ["即 topRisks 的简版2-3条"], "evidence": [${EVIDENCE_SCHEMA}]}`
  const user = `${questionBlock(p)}

【各分析师观点】
${agentSummaries}

【辩论纪要】
${debateSummary}

${packBlock(p)}`
  const run = await runAgent<{ riskLevel?: string; riskPenalty?: number; topRisks?: string[] }>(
    system,
    user,
    () => ({
      ...neutralFallback('风控审查生成失败，需人工复核；暂停最终评级与仓位建议'),
      riskLevel: 'Medium' as RiskLevelOut,
      riskPenalty: 5,
      topRisks: ['风控审查未能完成，存在未识别风险'],
    }),
    180_000,
    DEBATE_PROVIDER,
    p,
  )
  const lvlRaw = run.raw?.riskLevel
  const riskLevel: RiskLevelOut = (['Low', 'Medium', 'High', 'Very High'] as const).includes(lvlRaw as RiskLevelOut)
    ? (lvlRaw as RiskLevelOut)
    : 'Medium'
  const penalty = typeof run.raw?.riskPenalty === 'number' ? Math.max(0, Math.min(15, Math.round(run.raw.riskPenalty))) : 5
  const topRisks = Array.isArray(run.raw?.topRisks) ? run.raw!.topRisks.filter((x) => typeof x === 'string').slice(0, 3) : []
  const output: RiskOutput = { ...run.output, riskLevel, riskPenalty: penalty, topRisks: topRisks.length ? topRisks : run.output.concerns.slice(0, 3) }
  const validRisk = isRiskPayloadValid(run.raw)
  return { output, error: run.error ?? (validRisk ? null : new Error('INVALID_RISK_OUTPUT')), durationMs: run.durationMs }
}

// ---------- CIO ----------

export interface CIOOutput {
  confidence: number
  horizon: string
  keyLogic: string[]
  keyRisks: string[]
  thesis: { title: string; points: string[] }[]
  narrative: string
}

export async function cioAgent(
  p: DataPack,
  ctx: {
    dimensionScores: Record<string, number | null>
    initialScore: number
    riskPenalty: number
    finalScore: number
    rating: string
    positionMin: number
    positionMax: number
    voteSummary: string
    riskLevel: string
    topRisks: string[]
    conflictNote: string
  },
): Promise<CIOOutput | null> {
  const system = `你是基金公司首席投资官（CIO）。投委会已完成全部研究与投票，评分系统计算出最终结果（数字是权威的，不得修改）。你的任务：综合各方观点撰写最终投资决议的叙述部分。
${FINANCIAL_SEMANTIC_RULE}
${REPORTING_SCOPE_RULE}

输出 JSON 字段：
{"confidence": 30-95 置信度（参考投票一致性与证据强度，Risk Officer 风险越高置信度应越低）, "horizon": "投资周期如 12-24个月", "keyLogic": ["核心投资逻辑3-4条，每条≤40字"], "keyRisks": ["主要风险2-3条，每条≤40字"], "thesis": [{"title":"Growth|Competitive Advantage|Valuation|Macro|Risk 之一","points":["支撑要点2-3条"]}] 共5项, "narrative": "≤100字给投资人的决议陈述"}
${JSON_RULE}`
  const user = `研究标的：${p.stockName}${p.stockCode ? `(${p.stockCode})` : ''}
用户问题：${p.question}

【评分系统计算结果（权威）】
${JSON.stringify(ctx.dimensionScores)}
初始分 ${ctx.initialScore} → 风险惩罚 -${ctx.riskPenalty} → 最终分 ${ctx.finalScore} / 评级 ${ctx.rating} / 建议仓位 ${ctx.positionMin}-${ctx.positionMax}% / 风险等级 ${ctx.riskLevel}

【投委投票】
${ctx.voteSummary}

【Risk Officer Top 风险】
${ctx.topRisks.join('；')}
${ctx.conflictNote ? `\n【观点冲突提示】\n${ctx.conflictNote}` : ''}

【实时行情参考】
${liveBlock(p) || 'Data unavailable'}

【公司概况】
${p.stock ? p.stock.description : ''}
（详见评分输入）`
  return tryChatJSON<CIOOutput>(system, user, 180_000, DEBATE_PROVIDER)
}

// ---------- 报告 ----------

export async function reportAgent(
  p: DataPack,
  ctx: {
    finalScore: number
    rating: string
    confidence: number
    position: string
    horizon: string
    riskLevel: string
    keyLogic: string[]
    keyRisks: string[]
    agentSections: string
    voteSummary: string
  },
): Promise<string | null> {
  const system = `你是金融机构的研究报告撰稿人，基于已提供事实与决议撰写《投资研究报告》（Markdown）。不为报告补造研究事实。要求：
- 使用以下章节结构（一/二/三...编号二级标题）：执行摘要、公司概况、基本面分析、行业与竞争格局、宏观环境、估值与技术面、新闻与舆情、多空辩论纪要、风险分析、投资委员会决议、证据与数据来源附录
- 报告开头列研究时点、披露报告期、编制范围、资料状态，注明历史年度资料不代表最新季度
- 所有数字必须来自提供的数据，禁止编造；无数据处使用正式中文“资料不足，尚无法核验”
- 事实、程序计算、有限推断分别描述；每项主要财务事实附证据编号、报表范围、年度及来源页；派生值写清原始输入、公式、单位，不把自算值当原披露
- 辩论纪要用要点形式呈现多空交锋；风险分析按严重程度排序
- 决议章节明确给出：评级、最终评分、置信度、建议仓位、投资周期、核心逻辑、主要风险
- 语言客观、专业、精炼，避免“稳赚”“上车”“资金必然追捧”等营销和黑话，不将置信度称为盈利概率，不以评级宣称真实投资收益
- 总长900-1500字；资料不足的章节可合并为缺口说明，不机械扩写凑篇幅
${FINANCIAL_SEMANTIC_RULE}
${REPORTING_SCOPE_RULE}
直接输出 Markdown 正文（不要代码围栏）。`
  const user = `研究标的：${p.stockName}${p.stockCode ? `(${p.stockCode})` : ''} | 用户问题：${p.question}
研究时点：${p.evidenceAsOf ?? new Date().toISOString()}

【最终决议（权威数字）】
评级 ${ctx.rating} | 最终评分 ${ctx.finalScore}/100 | 置信度 ${ctx.confidence}% | 建议仓位 ${ctx.position} | 投资周期 ${ctx.horizon} | 风险等级 ${ctx.riskLevel}
核心逻辑：${ctx.keyLogic.join('；')}
主要风险：${ctx.keyRisks.join('；')}

【投委投票】
${ctx.voteSummary}

【各 Agent 分析摘要】
${ctx.agentSections}

【数据包】
${packBlock(p)}

${macroBlock(p)}

${newsBlock(p)}`
  return chatText(system, user, 120_000, 'deepseek').catch(() => null)
}
