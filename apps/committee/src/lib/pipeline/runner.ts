import { db } from '@/lib/db'
import type {
  AgentDTO,
  DebateDTO,
  DecisionDTO,
  MacroSnapshot,
  PipelineStatus,
  SessionDTO,
  SessionListItem,
  VoteType,
} from '@/lib/types'
import { findStock, STOCKS } from '@/lib/data/stocks'
import { GLOBAL_STOCKS, findGlobalStock } from '@/lib/data/global-stocks'
import { matchHotTerms, marketLabelOf } from '@/lib/data/hot-terms'
import { slangBlockForPrompt, matchSlang } from '@/lib/data/slang-dictionary'
import { indexKnowledgeBlock, matchIndexTopic, type IndexCatalogEntry } from '@/lib/data/index-encyclopedia'
import { matchUniverseStocks } from '@/lib/data/universe'
import { stockMentionPosition } from '@/lib/data/stock-mention'
import { MARKET_INDICES, type IndexDef } from '@/lib/data/quotes'
import type { StockProfile, PlanMeta } from '@/lib/types'
import { MACRO } from '@/lib/data/macro'
import { toTencentSymbol, fetchQuote, fetchDailyKline } from '@/lib/data/quotes'
import { collectCompanyNews, collectFinancialClues } from '@/lib/ai/search'
import { chatJSON, withLLMTrace } from '@/lib/ai/llm'
import { runResearchDiscussion, buildDiscussionReport, discussionSources, discussionDisplay } from '@/lib/research/discussion'
import { investmentScore, combineInvestmentScores, type ScoreComponent, type ScoreBasis } from '@/lib/research/investment-score'
import { computeQuantMetrics, type QuantMetrics } from './quant'
import {
  bullOpening,
  bearOpening,
  bullRebuttal,
  bearRebuttal,
  bullCrossAttack,
  bearCrossAttack,
  bullClosingArg,
  bearClosingArg,
  cioAgent,
  conflictResolution,
  fundamentalAgent,
  focusedSourceAgent,
  industryAgent,
  macroAgent,
  quantAgent,
  riskAgent,
  reportAgent,
  sentimentAgent,
  type AgentOutput,
  type DataPack,
  type RiskOutput,
} from './agents'
import { adjustConfidence, buildDecision, computeScore, type ScoreInput } from './scoring'
import { collectEvidence, collectFilingContexts } from '@/lib/research-evidence/catalog'
import { checkCitation, evaluateGate, canStartDecisionStages, reviewFinancialSemantics, buildReviewReport, GATE_LABELS, type ResearchAudit } from '@/lib/research-evidence/engine'
import { reviewReportingClaims } from '@/lib/research-evidence/scope'
import { selectResearchPath, executeFocusedSource } from '@/lib/research/focused-flow'
import {focusedReportObservation} from '@/lib/research/focused-report'
import { assessQuantitativeReadiness, buildQuantMetricEvidence } from '@/lib/research-evidence/market'

/**
 * 多智能体投委会 pipeline 编排器
 * planning → collecting → analyzing → debating → risk_review → voting → decision → report → completed
 */

const AGENT_NAMES: Record<string, string> = {
  fundamental: '基本面分析师',
  industry: '行业分析师',
  macro: '宏观策略分析师',
  quant: '量化分析师',
  sentiment: '舆情分析师',
  risk: '首席风险官',
  bull: '多头代表 Bull',
  bear: '空头代表 Bear',
  conflict: '观点冲突仲裁',
  cio: '首席投资官 CIO',
  planner: '研究规划师',
}

const inflight = new Map<string, Promise<void>>()

/** 全球常见标的中文名 → ticker 兜底表（LLM 未给出 code 时使用；行情层自动映射 us 前缀） */
const GLOBAL_NAME_TO_TICKER: { name: string; ticker: string }[] = [
  { name: '苹果', ticker: 'AAPL' },
  { name: '微软', ticker: 'MSFT' },
  { name: '英伟达', ticker: 'NVDA' },
  { name: '谷歌', ticker: 'GOOGL' },
  { name: '亚马逊', ticker: 'AMZN' },
  { name: '特斯拉', ticker: 'TSLA' },
  { name: 'Meta', ticker: 'META' },
  { name: '脸书', ticker: 'META' },
  { name: '台积电', ticker: 'TSM' },
  { name: '伯克希尔', ticker: 'BRK.B' },
  { name: '博通', ticker: 'AVGO' },
  { name: '阿里巴巴', ticker: 'BABA' },
  { name: '拼多多', ticker: 'PDD' },
  { name: '京东', ticker: 'JD' },
  { name: '百度', ticker: 'BIDU' },
  { name: '网易', ticker: 'NTES' },
  { name: '蔚来', ticker: 'NIO' },
  { name: '理想汽车', ticker: 'LI' },
  { name: '小鹏汽车', ticker: 'XPEV' },
]

/** 直接从查询文本中确定性匹配标的（本地库 + 全球库，不依赖 LLM，按出现位置排序） */
function directMatchStocks(query: string): { stock: StockProfile; pos: number }[] {
  const q = query.toLowerCase()
  const found: { stock: StockProfile; pos: number }[] = []
  for (const stock of [...STOCKS, ...GLOBAL_STOCKS]) {
    const keys: string[] = [stock.name.toLowerCase(), stock.code, ...stock.alias.map((a) => a.toLowerCase())]
    let bestPos = -1
    for (const k of keys) {
      if (k.length >= 2) {
        const idx = stockMentionPosition(q,k)
        if (idx !== -1 && (bestPos === -1 || idx < bestPos)) bestPos = idx
      }
    }
    if (bestPos !== -1) found.push({ stock, pos: bestPos })
  }
  return found.sort((a, b) => a.pos - b.pos).slice(0, 2)
}

// ---------- 指数研究模式（《全球指数大全》知识库接入） ----------

const INDEX_CODE_SET = new Set(MARKET_INDICES.map((d) => d.code))

/** 指数代码 → 展示市场标签 */
function indexMarketOf(def: IndexDef): string {
  const c = def.code.toLowerCase()
  if (c.startsWith('sh')) return 'SH'
  if (c.startsWith('sz')) return 'SZ'
  if (c.startsWith('bj')) return 'BJ'
  if (c.startsWith('hk')) return 'HK'
  if (c.startsWith('us') || def.group === 'us' || def.group === 'global') return 'US'
  return def.group.toUpperCase()
}

/**
 * 指数 → 合成研究标的（让指数获得与个股同级的完整流水线：
 * 实时行情/真实日K → 量化引擎 → 5 分析师 → 辩论 → 投票 → CIO → 报告）。
 * 估值/财务字段留空（指数无 PE/PB），数字可信度规则由提示词与量化引擎的空值容差保证。
 */
function buildIndexProfile(entry: IndexCatalogEntry, def: IndexDef): StockProfile {
  return {
    code: def.code,
    name: entry.name,
    market: indexMarketOf(def),
    alias: [entry.en.toLowerCase()],
    industry: '指数',
    sector: '指数',
    description: `${entry.name}（${entry.en}）：${entry.desc}${entry.relation ? ` 指数关系：${entry.relation}。` : ''}`,
    currency: def.currency ?? 'CNY',
    price: 0,
    changePct: 0,
    marketCap: 0,
    valuation: { pe: null, pePercentile: null, pb: 0, dividendYield: 0, peerAvgPe: 0 },
    financials: { revenue: 0, revenueGrowth: 0, netProfit: 0, profitGrowth: 0, grossMargin: 0, netMargin: 0, roe: 0, debtRatio: 0, ocf: 0 },
    history: [],
    technicals: { change1m: 0, change3m: 0, change6m: 0, change1y: 0, high52w: 0, low52w: 0, maTrend: 'above_mid', rsi14: 50, volatility: 'medium' },
    industryContext: { size: '指数研究模式', growth: '由真实日K与行情驱动', stage: '成熟期', concentration: '', outlook: '' },
    competitive: { rank: '', marketShare: '', moat: [], competitors: [] },
    risks: [],
    catalysts: [],
  }
}

/**
 * 防幻觉锚点校验：LLM 识别出的标的是否在用户原文中有文字锚点。
 * 校验规则：代码命中 / 全名命中 / 名称的任意 ≥2 字连续片段命中。
 * 热词（易中天）与简称（茅台）场景由 directMatchStocks / matchHotTerms 前置确定性解析，
 * 本函数只用于拦截 LLM 在「用户已点名具体标的」时输出的无关公司（如易中天→贵州茅台）。
 */
function hasTextAnchor(name: string, code: string, query: string): boolean {
  const q = query.toLowerCase()
  if (code && code.length >= 3 && stockMentionPosition(q,code)!==-1) return true
  const n = name.toLowerCase().trim()
  if (!n) return false
  if (q.includes(n)) return true
  const minLen = n.length >= 2 ? 2 : 1
  for (let len = n.length; len >= minLen; len--) {
    for (let i = 0; i + len <= n.length; i++) {
      if (q.includes(n.slice(i, i + len))) return true
    }
  }
  return false
}

export function launchResearch(sessionId: string): void {
  if (inflight.has(sessionId)) return
  const p = runPipeline(sessionId)
    .catch(async (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e)
      console.error(`[pipeline:${sessionId}] fatal:`, msg)
      await updateSession(sessionId, {
        status: 'failed',
        error: `研究流程异常中断：${msg.slice(0, 160)}`,
        currentStepLabel: '流程异常',
      }).catch(() => undefined)
    })
    .finally(() => inflight.delete(sessionId))
  inflight.set(sessionId, p)
}

async function updateSession(id: string, data: { status?: PipelineStatus; progress?: number; currentStepLabel?: string; error?: string; meta?: PlanMeta; stockCode?: string | null; stockName?: string | null; market?: string | null; intent?: string }) {
  const { meta, ...rest } = data
  await db.researchSession.update({
    where: { id },
    data: { ...rest, ...(meta !== undefined ? { meta: JSON.stringify(meta) } : {}) },
  })
}

async function addAgentRow(sessionId: string, key: string, out: AgentOutput, durationMs: number, details?: Record<string, unknown>) {
  await db.agentAnalysis.create({
    data: {
      sessionId,
      agentKey: key,
      agentName: AGENT_NAMES[key] ?? key,
      score: out.score,
      vote: out.vote,
      confidence: out.confidence,
      summary: out.summary,
      highlights: JSON.stringify(out.highlights ?? []),
      concerns: JSON.stringify(out.concerns ?? []),
      evidence: JSON.stringify(out.evidence ?? []),
      details: JSON.stringify(details ?? out.details ?? {}),
      durationMs,
    },
  })
}

async function addDebateRow(sessionId: string, round: number, phase: string, speakerKey: string, stance: string, content: string) {
  await db.debateMessage.create({
    data: { sessionId, round, phase, speakerKey, speakerName: AGENT_NAMES[speakerKey] ?? speakerKey, stance, content },
  })
}

function neutralQuant(): QuantMetrics {
  return {
    pe: null, pePercentile: null, pb: 0, dividendYield: 0, peg: null, peVsPeerPct: null,
    pos52w: 50, momentum: 50, valuation: 50, volatility: 'unknown' as QuantMetrics['volatility'],
    volatilityAnnualPct: null, rsi14: 50, maTrendLabel: 'Data unavailable', trendVerdict: 'Data unavailable',
    dataSource: 'snapshot', changes: { m1: null, m3: null, m6: null, y1: null }, ma20: null, ma60: null, ma120: null,
  }
}

function fmtSummaries(list: { name: string; out: AgentOutput }[]): string {
  return list
    .map(({ name, out }) => {
      const score = out.score !== null ? `评分${out.score}` : '评分N/A'
      const vote = out.vote ? `投票${out.vote}` : ''
      return `- ${name}：${score} ${vote}。${out.summary} 优势：${(out.highlights ?? []).slice(0, 2).join('；') || '无'} 风险：${(out.concerns ?? []).slice(0, 2).join('；') || '无'}`
    })
    .join('\n')
}

// ---------- Pipeline 主流程 ----------

async function runPipeline(sessionId: string): Promise<void> {
  const runStarted=Date.now()
  const session = await db.researchSession.findUnique({ where: { id: sessionId } })
  if (!session) throw new Error('session not found')
  const query = session.query

  // ===== 1. Research Planner =====
  await updateSession(sessionId, { status: 'planning', progress: 6, currentStepLabel: 'Research Planner 正在拆解研究任务…' })

  // 1a. 确定性直接匹配（快照库，优先，抗 LLM 失败）
  const direct = directMatchStocks(query)

  // 1a+. 市场热词/组合名确定性解析（易中天/茅指数/宁王…）：必须在 LLM 之前执行，作为防幻觉锚点
  const hotMatches = matchHotTerms(query)

  // 1a++. 市场黑话理解（股票黑话大词典）：用户提问中的行话/术语白话注释，注入全部 Agent
  const slangNote = slangBlockForPrompt(query)
  const slangHits = matchSlang(query)

  // 1a+++ 指数知识（《全球指数大全》）：无论个股还是指数研究，命中即注入知识块
  const indexNote = indexKnowledgeBlock(query)

  // 统一候选集：快照库直配 + 宇宙热门股 + 热词成员 + LLM 补充（去重、按原文出现位置排序）
  interface Cand {
    profile: StockProfile | null // 命中快照库 → 完整研究模式
    code: string // 通用代码：A股 6 位 / 港股 5 位 / 美股 ticker（limited 模式取实时行情用）
    name: string
    market: string
    pos: number
  }
  const cands: Cand[] = []
  const pushCand = (c: Cand) => {
    if (c.code && !cands.some((x) => x.code === c.code)) cands.push(c)
  }
  for (const d of direct) pushCand({ profile: d.stock, code: d.stock.code, name: d.stock.name, market: d.stock.market, pos: d.pos })
  for (const hm of hotMatches) {
    for (const m of hm.term.stocks) {
      const profile = findStock(m.code) ?? findGlobalStock(m.code) ?? null
      pushCand({ profile, code: m.code, name: m.name, market: m.market, pos: hm.pos })
    }
  }

  // 1a++++ 全球热门标的快照库（A股/港股/美股 各1000只）：确定性识别热门股（权威名称+市场+行业标签）
  const uniMatches = await matchUniverseStocks(query, 2)
  const uniHitOfChosen = new Map<string, (typeof uniMatches)[number]['stock']>()
  for (const u of uniMatches) {
    uniHitOfChosen.set(u.stock.code, u.stock)
    pushCand({ profile: null, code: u.stock.code, name: u.stock.name, market: u.stock.market, pos: u.pos })
  }
  /** 用户是否已点名具体标的/热词（决定是否对 LLM 输出做锚点校验） */
  const queryIsSpecific = cands.length > 0

  // 1b. LLM 规划（尽力而为：拆解计划 + 识别直接匹配遗漏的标的；受防幻觉铁律约束）
  const DEFAULT_PLAN = ['识别研究标的与研究意图', '采集财务快照与实时新闻', '基本面·行业·宏观并行分析', '估值与技术面量化分析', '新闻舆情与事件分析', 'Bull vs Bear 多空辩论', '风险审查与投委投票', 'CIO 综合裁决与报告']
  const planRes = await chatJSON<{ stocks?: { name?: string; code?: string }[]; focus?: string; plan?: string[] }>(
    `你是基金公司的研究主管（Research Planner）。解析用户的投资研究请求：识别研究标的（股票名称/代码/简称/俗称/组合名）与研究意图，并制定研究计划。若用户是在多个标的之间做比较/对比，必须按用户提到的顺序识别出全部对比标的（2只），不能只识别一只。${'只输出合法 JSON。'}
输出 {"stocks":[{"name":"公司名","code":"代码(如能识别)"}], "focus":"一句话研究重点", "plan":["研究计划5-8条，每条≤20字"]}
代码规则：A股用 6 位数字（如 600519、300502）；港股用 5 位数字（如 00700）；美股/中概股用 ticker（如 AAPL、NVDA、TSLA、BABA、PDD），不确定时留空。
【标的识别铁律——违反即为严重事故】
1) 用户提到的简称/俗称/组合名/市场黑话必须按市场惯用含义解析，严禁替换成语义无关的其他公司。常见热词对照：易中天=新易盛300502+中际旭创300308+天孚通信300394（CPO/光模块三剑客）；宁王=宁德时代300750；茅指数=贵州茅台等核心龙头组合；宁组合=宁德时代/汇川技术等成长组合；中概互联=腾讯/阿里/美团组合；中特估=中国神华/工商银行等央国企。
2) 若用户原文出现了具体公司名/代码/俗称，必须原样解析该标的本身，严禁输出原文未提及且含义无关的公司（例如把「易中天」解析成「贵州茅台」属于严重错误）。
3) 没有把握时 stocks 返回空数组，宁缺毋滥，严禁编造代码。
4) 只有当用户问的是行业/主题且未点名任何具体标的时，才识别该行业最具代表性的 1-2 家公司。`,
    `用户输入：${query}

可用标的库提示（部分）：贵州茅台600519、五粮液000858、泸州老窖000568、宁德时代300750、比亚迪002594、隆基绿能601012、阳光电源300274、中芯国际688981、北方华创002371、海光信息688041、寒武纪688256、腾讯控股00700.HK、阿里巴巴-W09988.HK、美团03690.HK、招商银行600036、工商银行601398、中国平安601318、恒瑞医药600276、迈瑞医疗300760、药明康德603259、伊利股份600887、海天味业603288、美的集团000333、格力电器000651、立讯精密002475、汇川技术300124、三一重工600031、中国神华601088、长江电力600900、中信证券600030、东方财富300059、科大讯飞002230、金山办公688111、紫金矿业601899、万华化学600309、顺丰控股002352、京东方A000725、中国石油601857、片仔癀600436、东鹏饮料605499。
常见全球标的：苹果AAPL、微软MSFT、英伟达NVDA、谷歌GOOGL、亚马逊AMZN、特斯拉TSLA、Meta META、台积电TSM、伯克希尔BRK.B、博通AVGO、阿里巴巴BABA、拼多多PDD、京东JD、百度BIDU、网易NTES、蔚来NIO、理想汽车LI、小鹏汽车XPEV。
其他热门标的（未收录快照库，代码同样有效）：新易盛300502、中际旭创300308、天孚通信300394、工业富联601138、中兴通讯000063、浪潮信息000977、中科曙光603019、中国中免601888、牧原股份002714、沪电股份002463、华工科技000988。
若用户请求的是行业/主题而非单只股票，请将 stocks 识别为该行业最具代表性的 1-2 家公司（铁律 1/2 仍然生效）。`,
    45_000,
  ).catch(() => ({ stocks: [], focus: undefined, plan: undefined }))

  const planStocks = (planRes.stocks ?? []).filter((s) => s && s.name).slice(0, 2)
  for (const ps of planStocks) {
    const profile = findStock(ps.code ?? '') ?? findStock(ps.name ?? '') ?? findGlobalStock(ps.code ?? '') ?? findGlobalStock(ps.name ?? '')
    const name = (profile?.name ?? ps.name ?? '').trim()
    let code = (ps.code ?? profile?.code ?? '').trim().toUpperCase().replace(/\.(O|N|US|OQ)$/, '')
    // 全球标的兑底：LLM 只给出中文名且未命中快照库时，用常见 ticker 兑底表
    if (!code && !profile && name) {
      code = GLOBAL_NAME_TO_TICKER.find((g) => name.includes(g.name) || g.name.includes(name))?.ticker ?? ''
    }
    // 防幻觉锚点校验：用户已点名具体标的/热词时，LLM 补充标的必须在原文中有锚点，
    // 否则一律丢弃（拦截「易中天→贵州茅台」类幻觉）
    if (queryIsSpecific && !hasTextAnchor(name, code, query)) {
      console.warn(`[planner] 丢弃未锚定标的（防幻觉）：${name || '(空)'}(${code || '-'}) ← "${query.slice(0, 40)}"`)
      continue
    }
    const pos = name ? query.toLowerCase().indexOf(name.toLowerCase()) : -1
    pushCand({
      profile,
      code: code || profile?.code || '',
      name,
      market: profile?.market ?? marketLabelOf(code),
      pos: pos >= 0 ? pos : 900, // 原文未出现 → LLM 推荐，排在末位
    })
  }
  const matched = [...cands].sort((a, b) => a.pos - b.pos).slice(0, 2)

  // ===== 1c. 指数研究模式：用户问的是指数而非个股（《全球指数大全》接入，实时行情驱动） =====
  if (matched.length === 0 && indexNote && !queryIsSpecific) {
    const topic = matchIndexTopic(query)
    if (topic?.entry.quoteCode) {
      const def = MARKET_INDICES.find((d) => d.code === topic.entry.quoteCode)
      if (def) {
        const profile = buildIndexProfile(topic.entry, def)
        cands.length = 0
        pushCand({ profile, code: profile.code, name: profile.name, market: profile.market, pos: 0 })
        matched.push({ profile, code: profile.code, name: profile.name, market: profile.market, pos: 0 })
        console.log(`[planner] 指数研究模式：${profile.name}(${profile.code})`)
      }
    }
  }

  const isComparison = (session.intent === 'comparison' || matched.length >= 2) && !!session.groupId
  const chosen: Cand | null = isComparison ? (matched[session.orderIndex] ?? matched[0] ?? null) : (matched[0] ?? null)
  // 快照库命中 → 完整研究模式（与茅台同级全流程）；未命中 → limited-data 模式（A股/港股/美股任意代码实时行情）
  const finalTarget: StockProfile | null = chosen?.profile ?? null
  const isIndexTarget = finalTarget != null && INDEX_CODE_SET.has(finalTarget.code)
  const limitedCode: string | null = finalTarget ? null : chosen?.code ?? null
  const fallbackName = queryIsSpecific
    ? query.slice(0, 20) // 已点名但未能解析出代码：展示原文，绝不使用被丢弃的 LLM 幻觉名称
    : (planStocks[session.orderIndex]?.name ?? planStocks[0]?.name ?? query.slice(0, 20))
  const stockName = finalTarget?.name ?? chosen?.name ?? fallbackName
  const marketLabel = finalTarget?.market ?? (limitedCode ? marketLabelOf(limitedCode) : null)

  // 热词上下文：写入 meta（前端展示）并注入给全部 Agent（保证全链路理解一致）
  const hotMembers = [...new Map(hotMatches.flatMap((h) => h.term.stocks).map((s) => [s.code, s])).values()]
  const hotTermNote =
    hotMatches.length > 0
      ? `用户提问中的「${hotMatches.map((h) => h.matched).join('」「')}」是市场热词/组合昵称，已按市场惯用含义确定性解析，严禁理解为其他无关公司。释义：${hotMatches.map((h) => h.term.note).join('；')}。${chosen ? `本次研究对象为 ${chosen.name}(${chosen.code})` : ''}${hotMembers.length > 1 ? `；组合全部成员：${hotMembers.map((m) => `${m.name}(${m.code})`).join('、')}，分析与结论必须覆盖组合整体逻辑与成员间相对强弱` : ''}。`
      : undefined

  const meta: PlanMeta = {
    intent: isComparison ? 'comparison' : 'single',
    question: query,
    focus: planRes.focus,
    stocks: matched.map((s) => ({ code: s.code, name: s.name, market: s.market })),
    plan: (planRes.plan ?? []).length > 0 ? (planRes.plan ?? []).slice(0, 8) : DEFAULT_PLAN,
    ...(slangHits.length > 0
      ? {
          slangTerms: slangHits.slice(0, 8).map((h) => ({ term: h.term, meaning: h.meaning })),
        }
      : {}),
    ...(hotMatches.length > 0
      ? {
          hotTerm: {
            term: hotMatches.map((h) => h.matched).join('·'),
            note: hotMatches.map((h) => h.term.note).join('；'),
            members: hotMembers.map(({ code, name, market }) => ({ code, name, market })),
          },
        }
      : {}),
  }

  await updateSession(sessionId, {
    status: 'planning',
    progress: 10,
    currentStepLabel: `研究计划已生成：${stockName}`,
    stockCode: finalTarget?.code ?? limitedCode,
    stockName,
    market: marketLabel,
    intent: isComparison ? 'comparison' : 'single',
    meta,
  })

  // ===== 2. Data Collection =====
  await updateSession(sessionId, { status: 'collecting', progress: 14, currentStepLabel: '采集实时行情与财务快照…' })
  let news: PlanMeta['news'] = []
  let newsSearchStatus: 'ok' | 'empty' | 'failed' = 'empty'
  try {
    news = await collectCompanyNews(stockName, finalTarget?.code ?? limitedCode ?? '')
    newsSearchStatus = news.length > 0 ? 'ok' : 'empty'
  } catch {
    newsSearchStatus = 'failed'
  }
  meta.news = news
  meta.newsSearchStatus = newsSearchStatus
  const isUniverseTarget = !finalTarget && chosen != null && uniHitOfChosen.has(chosen.code)
  meta.dataNote = isIndexTarget
    ? '指数研究模式：点位/涨跌/成交与日K来自腾讯财经·雅虎财经实时行情；指数定义、层级与成员关系来自内置《全球股票市场与主要指数大全》知识库；新闻来自实时网络检索。'
    : isUniverseTarget
    ? `标的已收录于「全球热门标的快照库」（全球热门 10000 只，行业：${
        uniHitOfChosen.get(chosen?.code ?? '')?.industry ?? '综合'
      }）：分析基于实时行情（腾讯财经/雅虎财经）、web_search 检索的财务线索与实时新闻，数字均标注来源。`
    : finalTarget
    ? finalTarget.market === 'US'
      ? '关键财务数字来自全球标的快照库（基于公开年报/季报整理，近似值，人民币亿元口径）与腾讯财经实时行情；新闻来自实时网络检索。'
      : '关键财务数字来自演示快照库（基于公开年报整理，近似值）与腾讯财经实时行情；新闻来自实时网络检索。'
    : limitedCode
      ? `标的「${stockName}(${limitedCode})」未收录快照库：分析基于实时行情（腾讯财经/雅虎财经）、web_search 检索的财务线索与实时新闻，数字均标注来源。`
      : '未能解析出可交易标的代码：分析基于 web_search 财务线索与实时新闻，数字均标注来源。'

  // 1e. limited-data 标的：检索真实财务线索（营收/利润/估值），注入给全部 Agent
  let financialClues: PlanMeta['news'] = []
  if (!finalTarget) {
    try {
      financialClues = await collectFinancialClues(stockName, limitedCode ?? '')
    } catch {
      financialClues = []
    }
  }

  // 2b. 实时行情 + 真实日K（腾讯财经/雅虎）：驱动量化引擎与 Agent 数据包
  // limited 模式传通用代码：A股 6 位/港股 5 位/美股 ticker 由行情层自动归一化（sz300502/hk00700/usNVDA）
  // 指数模式传指数内部代码（sh000300 / hkHSI / ^N225）：行情层自动分流腾讯/雅虎
  let live: { quote: Awaited<ReturnType<typeof fetchQuote>>; kline: Awaited<ReturnType<typeof fetchDailyKline>> } | null = null
  {
    const quoteSymbol = finalTarget
      ? isIndexTarget
        ? finalTarget.code
        : toTencentSymbol(finalTarget.code)
      : limitedCode
    if (quoteSymbol) {
      const [quote, kline] = await Promise.all([fetchQuote(quoteSymbol), fetchDailyKline(quoteSymbol, 300)])
      if (quote) {
        live = { quote, kline }
        meta.quote = {
          price: quote.price,
          change: quote.change,
          changePct: quote.changePct,
          high: quote.high,
          low: quote.low,
          open: quote.open,
          prevClose: quote.prevClose,
          volume: quote.volume,
          amount: quote.amount,
          turnoverRate: quote.turnoverRate,
          peTtm: quote.peTtm,
          pb: quote.pb,
          marketCap: quote.marketCap,
          high52w: quote.high52w,
          low52w: quote.low52w,
          time: quote.time,
          currency: quote.currency,
        }
      }
    }
  }
  await updateSession(sessionId, {
    status: 'collecting',
    progress: 20,
    currentStepLabel: [
      newsSearchStatus === 'ok' ? `已获取 ${news.length} 条实时新闻` : '新闻检索受限，进入降级分析',
      live?.quote ? `实时行情 ${live.quote.price}（${live.quote.changePct > 0 ? '+' : ''}${live.quote.changePct}%）` : null,
      live && live.kline.length > 60 ? `${live.kline.length} 日真实K线` : null,
    ]
      .filter(Boolean)
      .join(' · '),
    meta,
  })

  // ===== 3. Parallel Analysis =====
  await updateSession(sessionId, { status: 'analyzing', progress: 24, currentStepLabel: '5 位分析师 Agent 并行研究中…' })
  const pack: DataPack = {
    stock: finalTarget,
    stockName,
    stockCode: finalTarget?.code ?? limitedCode,
    market: finalTarget?.market ?? marketLabel,
    macro: MACRO as MacroSnapshot,
    news: news ?? [],
    newsSearchStatus,
    financialClues,
    question: query,
    focus: planRes.focus,
    hotTermNote,
    ...(slangNote ? { slangNote } : {}),
    ...(indexNote ? { indexNote } : {}),
    ...(!finalTarget && chosen && uniHitOfChosen.has(chosen.code)
      ? {
          universeNote: `该标的已收录于「全球热门标的快照库」（A股/港股/美股 各1000只热门股，行业：${
            uniHitOfChosen.get(chosen.code)?.industry ?? '综合'
          }）。名称与代码为行情源权威数据，可放心使用；财务数字仍需来自实时行情/检索线索。`,
        }
      : {}),
  }
  const qMetrics = finalTarget ? computeQuantMetrics(finalTarget, live) : neutralQuant()
  const capturedAt = new Date().toISOString()
  const marketReadiness = assessQuantitativeReadiness({
    stockCode: pack.stockCode ?? limitedCode ?? 'unknown',
    quote: live?.quote ?? null,
    kline: live?.kline ?? [],
    capturedAt,
  })
  // Technical indicators are fully derived from registered market inputs.
  // The valuation score still blends snapshot percentile, peer and dividend
  // fields, so the combined quantitative score remains unavailable for voting.
  const quantitativeReady = false
  const quantitativeReadinessReason = '正式估值评分仍含未核对的快照分位、同业 PE 或股息率，技术指标可展示但不能用于综合评分'
  pack.quant = qMetrics
  pack.live = live
  pack.quantitativeReady = quantitativeReady
  pack.technicalReady = marketReadiness.ready
  const requestedCodes=meta.intent==='comparison'?meta.stocks.map(s=>s.code):[pack.stockCode].filter((c): c is string=>!!c)
  const baseEvidence = collectEvidence({stockCode:pack.stockCode,stock:finalTarget,news:news ?? [],financialClues:financialClues ?? [],quote:live?.quote ?? null,capturedAt,peerStockCodes:requestedCodes})
  pack.filingContexts=collectFilingContexts(requestedCodes,capturedAt)
  const marketIds = new Set(marketReadiness.records.map((record) => record.id))
  const evidenceRecords = baseEvidence.filter((record) => !marketIds.has(record.id))
  evidenceRecords.push(...marketReadiness.records)
  if (marketReadiness.ready && finalTarget && live?.quote) {
    evidenceRecords.push(...buildQuantMetricEvidence({
      stockCode: pack.stockCode ?? finalTarget.code,
      quote: live.quote,
      kline: live.kline,
      metrics: {
        momentum: qMetrics.momentum,
        rsi14: qMetrics.rsi14,
        ma20: qMetrics.ma20,
        ma60: qMetrics.ma60,
        ma120: qMetrics.ma120,
      },
      capturedAt,
    }))
  }
  const audit: ResearchAudit = {
    version:'evidence-v1',runId:sessionId,capturedAt,
    records:evidenceRecords,
    claims:[],stageDurationsMs:{collectionAndPlanning:Date.now()-runStarted},failedAgents:[],modelEvaluation:'live',
  }
  pack.evidenceRecords=audit.records
  pack.evidenceAsOf=capturedAt
  meta.audit=audit
  await updateSession(sessionId,{meta})

  if(selectResearchPath(query)==='focused_source') {
    await updateSession(sessionId,{status:'analyzing',progress:35,currentStepLabel:'财报核对精简路径：单角色分析与确定性证据检查'})
    const focused=await executeFocusedSource(pack,focusedSourceAgent)
    const result=focused.analysis
    result.output.evidence=result.output.evidence.map(c=>checkCitation({...c,agentKey:'fundamental'},audit.records,capturedAt))
    audit.claims.push(...result.output.evidence)
    if(result.error)audit.failedAgents.push('fundamental')
    audit.stageDurationsMs.fundamental=result.durationMs
    audit.skippedStages=focused.skippedRoles
    audit.decisionGate=evaluateGate({records:audit.records,claims:audit.claims,riskStatus:'not_run',failedAgents:audit.failedAgents,quantitativeReady:false,now:new Date().toISOString()})
    await addAgentRow(sessionId,'fundamental',result.output,result.durationMs,{...result.output.details,researchPath:'focused_source',executionStatus:result.error?'failed':'ok',skippedRoles:focused.skippedRoles})
    audit.reportMd=buildReviewReport({runId:sessionId,stockName,query,records:audit.records,gate:audit.decisionGate,claims:audit.claims,
      analyses:[{name:'财报核对精简路径',summary:focusedReportObservation(result.output)}]})
    audit.stageDurationsMs.total=Date.now()-runStarted
    await updateSession(sessionId,{status:'completed',progress:100,currentStepLabel:'财报核对报告已完成；精简路径不执行投资投票',meta})
    return
  }

  const started = Date.now()
  const [fund, ind, mac, qnt, sen] = await Promise.all([
    fundamentalAgent(pack),
    industryAgent(pack),
    macroAgent(pack),
    quantAgent(pack, qMetrics),
    sentimentAgent(pack),
  ])
  const elapsed = Date.now() - started

  const agentDefs: { key: string; run: { output: AgentOutput; raw: Record<string, unknown> | null; error: Error | null; durationMs: number }; details?: Record<string, unknown> }[] = [
    { key: 'fundamental', run: fund, details: fund.raw && typeof fund.raw.details === 'object' ? (fund.raw.details as Record<string, unknown>) : undefined },
    { key: 'industry', run: ind, details: ind.raw && typeof ind.raw.details === 'object' ? (ind.raw.details as Record<string, unknown>) : undefined },
    { key: 'macro', run: mac, details: mac.raw && typeof mac.raw.details === 'object' ? (mac.raw.details as Record<string, unknown>) : undefined },
    { key: 'quant', run: qnt, details: { ...(qnt.raw?.details ?? {}), valuation: null, momentum: qMetrics.momentum, pe: qMetrics.pe, pePercentile: null, peg: null, pos52w: qMetrics.pos52w, rsi14: qMetrics.rsi14, trend: qMetrics.trendVerdict, dataSource: qMetrics.dataSource, volatilityAnnualPct: qMetrics.volatilityAnnualPct, ma20: qMetrics.ma20, ma60: qMetrics.ma60, ma120: qMetrics.ma120, changes: qMetrics.changes, maTrendLabel: qMetrics.maTrendLabel } },
    { key: 'sentiment', run: sen, details: sen.raw && typeof sen.raw.details === 'object' ? (sen.raw.details as Record<string, unknown>) : undefined },
  ]

  let done = 0
  for (const def of agentDefs) {
    if (def.key==='quant' && !quantitativeReady) def.details={executionStatus:'limited',valuation:null,momentum:marketReadiness.ready ? qMetrics.momentum : null,pe:marketReadiness.ready ? qMetrics.pe : null,pePercentile:null,peg:null,pos52w:marketReadiness.ready ? qMetrics.pos52w : null,rsi14:marketReadiness.ready ? qMetrics.rsi14 : null,volatilityAnnualPct:marketReadiness.ready ? qMetrics.volatilityAnnualPct : null,ma20:marketReadiness.ready ? qMetrics.ma20 : null,ma60:marketReadiness.ready ? qMetrics.ma60 : null,ma120:marketReadiness.ready ? qMetrics.ma120 : null,changes:marketReadiness.ready ? qMetrics.changes : {m1:null,m3:null,m6:null,y1:null},dataSource:marketReadiness.ready ? 'technical_source_checked' : 'unverified',maTrendLabel:marketReadiness.ready ? qMetrics.maTrendLabel : '尚未完成输入核验',readinessReasons:[...marketReadiness.reasons, quantitativeReadinessReason]}
    if(def.key==='quant'&&!quantitativeReady&&def.details){
      const count=live?.kline.length??0
      def.details.momentum=audit.records.find(r=>r.id===`quant:${pack.stockCode}:momentum`)?.value??null
      def.details.pe=marketReadiness.ready?live?.quote?.peTtm??null:null
      def.details.changes=marketReadiness.ready?{m1:count>=22?qMetrics.changes.m1:null,m3:count>=64?qMetrics.changes.m3:null,m6:count>=127?qMetrics.changes.m6:null,y1:count>=251?qMetrics.changes.y1:null}:{m1:null,m3:null,m6:null,y1:null}
      if(count<127)def.details.trend=null
      if(count<120){def.details.pos52w=null;def.details.maTrendLabel='仅展示样本充足的均线原值'}
    }
    if (def.run.error) audit.failedAgents.push(def.key)
    def.run.output.evidence=def.run.output.evidence.map(c=>checkCitation({...c,agentKey:def.key},audit.records,capturedAt))
    audit.claims.push(...def.run.output.evidence)
    audit.stageDurationsMs[def.key]=def.run.durationMs
    const savedDetails=def.run.error?.message==='FINANCIAL_SEMANTIC_REVIEW_REQUIRED'
      ? def.run.output.details : {...def.details,...def.run.output.details}
    await addAgentRow(sessionId, def.key, def.run.output, def.run.durationMs, {...savedDetails,executionStatus:def.run.error?.message==='FINANCIAL_SEMANTIC_REVIEW_REQUIRED' ? 'review_required' : def.run.error ? 'failed' : def.key==='quant' ? 'limited' : 'ok'})
    done++
    await updateSession(sessionId, {
      progress: 24 + Math.round((done / agentDefs.length) * 20),
      currentStepLabel: `${AGENT_NAMES[def.key]} 已完成分析`,
    }).catch(() => undefined)
  }
  audit.stageDurationsMs.parallelAnalysis=elapsed
  await updateSession(sessionId,{meta})

  const coreOutputs: { key: string; name: string; out: AgentOutput }[] = [
    { key: 'fundamental', name: '基本面分析师', out: fund.output },
    { key: 'industry', name: '行业分析师', out: ind.output },
    { key: 'macro', name: '宏观策略分析师', out: mac.output },
    { key: 'quant', name: '量化分析师', out: qnt.output },
    { key: 'sentiment', name: '舆情分析师', out: sen.output },
  ]
  const agentSummaries = fmtSummaries(coreOutputs)

  const decisionPreflight=canStartDecisionStages({records:audit.records,claims:audit.claims,failedAgents:audit.failedAgents,quantitativeReady,now:new Date().toISOString()})
  if(!decisionPreflight.ready) {
    const input={query,stockName,stockCode:pack.stockCode,companies:Object.fromEntries(meta.stocks.map(s=>[s.code,s.name])),records:audit.records,contexts:pack.filingContexts??[],now:new Date().toISOString(),analyses:coreOutputs.map(a=>({key:a.key,name:a.name,summary:a.out.summary,highlights:a.out.highlights,concerns:a.out.concerns,evidence:a.out.evidence,basis:typeof a.out.details?.scoreBasis==='string'?a.out.details.scoreBasis:undefined,executionStatus:audit.failedAgents.includes(a.key)?'review_required':a.key==='quant'?'limited':'ok'}))}
    audit.skippedStages=discussionSources(input).length?['voting','investment_rating']:['debating','risk_review','voting','investment_rating']
    await updateSession(sessionId,{status:'debating',progress:46,currentStepLabel:'双方讨论：先看经营表现，再看关键分歧',meta})
    audit.researchDiscussion=[]
    const result=await runResearchDiscussion(input,async(_role,system,user)=>withLLMTrace(()=>chatJSON(system,user,_role.endsWith(':semantic_review')?45_000:120_000,'deepseek')),async turn=>{
      audit.researchDiscussion!.push(turn)
      audit.stageDurationsMs[`discussion:${turn.role}`]=turn.durationMs
      if(turn.status!=='ok')audit.failedAgents.push(`discussion:${turn.role}`)
      if(turn.role==='risk'){
        const score=investmentScore({score:turn.score,confidence:turn.confidence,hasDirection:turn.sourceIds.length>0,failed:turn.status!=='ok',reason:turn.scoreReason??turn.summary})
        await addAgentRow(sessionId,'risk',{score:score.score,vote:null,confidence:score.confidence,summary:turn.summary,highlights:turn.points,concerns:[...turn.risks,...turn.missing,...turn.issues],evidence:[]},turn.durationMs,{executionStatus:turn.status,scoreKind:'investment_attractiveness',scoreBasis:score.basis,scoreReason:score.reason,sourceIds:turn.sourceIds,llmCalls:turn.calls,semanticReview:{status:turn.polarityReviews?.some(r=>r.accepted)?'model_reviewed':'no_issue_detected',polarityReviews:turn.polarityReviews,completeSemanticVerification:false}})
      }
      if(turn.role!=='conclusion'){
        const content=discussionDisplay(turn)
        const risk=turn.role==='risk',bull=turn.role.startsWith('bull')
        await addDebateRow(sessionId,risk?3:turn.role.includes('rebuttal')?2:1,risk?'risk':turn.role.includes('rebuttal')?'rebuttal':'opening',risk?'risk':bull?'bull':'bear',risk?'risk':bull?'bull':'bear',content)
      }
      const status=turn.role==='conclusion'||turn.role==='risk'?'decision':turn.role.includes('rebuttal')?'risk_review':'debating'
      await updateSession(sessionId,{status,progress:48+audit.researchDiscussion!.length*6,currentStepLabel:turn.role==='conclusion'?'研究结论已生成，整理报告':turn.role==='risk'?'风控结果已记录，生成研究结论':'双方正在交换观点',meta})
    })
    const components:ScoreComponent[]=coreOutputs.map(a=>({key:a.key,score:a.out.score??50,confidence:a.out.confidence??0,basis:(a.out.details?.scoreBasis??'baseline') as ScoreBasis,reason:typeof a.out.details?.scoreReason==='string'?a.out.details.scoreReason:undefined,technical:a.out.details?.scoreKind==='technical_momentum'}))
    const riskTurn=result.turns.find(t=>t.role==='risk')
    if(riskTurn){const score=investmentScore({score:riskTurn.score,confidence:riskTurn.confidence,hasDirection:riskTurn.sourceIds.length>0,failed:riskTurn.status!=='ok',reason:riskTurn.scoreReason??riskTurn.summary});components.push({key:'risk',...score})}
    else{
      const score=investmentScore({score:null,hasDirection:false})
      components.push({key:'risk',...score})
      await addAgentRow(sessionId,'risk',{score:score.score,vote:null,confidence:0,summary:'尚无可审查的经营结论，先按基准值展示风险判断。',highlights:[],concerns:[],evidence:[]},0,{executionStatus:'limited',scoreKind:'investment_attractiveness',scoreBasis:'baseline',scoreReason:score.reason,llmCalls:[]})
    }
    result.conclusion.scoreSummary=combineInvestmentScores(components)
    audit.researchConclusion=result.conclusion
    if(result.conclusion.status==='complete'&&audit.failedAgents.length){result.conclusion.status='partial';result.conclusion.risks.push('部分分析角色未通过，需结合各角色状态复核。')}
    const risk=result.turns.find(t=>t.role==='risk')
    audit.decisionGate=evaluateGate({records:audit.records,claims:audit.claims,riskStatus:!risk?'not_run':risk.status==='ok'?'ok':'failed',failedAgents:audit.failedAgents,quantitativeReady,now:new Date().toISOString()})
    await updateSession(sessionId,{status:'report',progress:90,currentStepLabel:'整理研究结论、数据对照、双方论证及来源附录',meta})
    audit.reportMd=buildDiscussionReport({...input,runId:sessionId,turns:result.turns,conclusion:result.conclusion,ratingReasons:audit.decisionGate.reasons})
    audit.stageDurationsMs.total=Date.now()-runStarted
    await updateSession(sessionId,{status:'completed',progress:100,meta,currentStepLabel:result.conclusion.status==='complete'?'分析、评分与报告已完成':result.conclusion.status==='partial'?'报告已保存，部分分析尚未完成':'研究记录已保存'})
    return
  }

  // ===== 4. Bull vs Bear Debate（4 轮制：立论 → 反驳 → 交叉质证 → 结辩）=====
  await updateSession(sessionId, { status: 'debating', progress: 46, currentStepLabel: 'R1 立论：Bull / Bear 陈述立场…' })
  const [bull, bear] = await Promise.all([bullOpening(pack, agentSummaries), bearOpening(pack, agentSummaries)])
  await addDebateRow(sessionId, 1, 'opening', 'bull', 'bull', bull.content)
  await updateSession(sessionId, { progress: 48, currentStepLabel: '多头立论完成，空头陈述中…' })
  await addDebateRow(sessionId, 1, 'opening', 'bear', 'bear', bear.content)
  await updateSession(sessionId, { progress: 50, currentStepLabel: 'R2 反驳：双方针锋相对…' })

  const [bullR, bearR] = await Promise.all([bullRebuttal(pack, bear.content), bearRebuttal(pack, bull.content)])
  await addDebateRow(sessionId, 2, 'rebuttal', 'bull', 'bull', bullR.content)
  await updateSession(sessionId, { progress: 52, currentStepLabel: '多头反驳完成，空头反驳中…' })
  await addDebateRow(sessionId, 2, 'rebuttal', 'bear', 'bear', bearR.content)
  await updateSession(sessionId, { progress: 54, currentStepLabel: 'R3 交叉质证：定点攻击对方最薄弱论点…' })

  const [bullC, bearC] = await Promise.all([
    bullCrossAttack(pack, bear.content, bearR.content),
    bearCrossAttack(pack, bull.content, bullR.content),
  ])
  await addDebateRow(sessionId, 3, 'crossexam', 'bull', 'bull', bullC.content)
  await updateSession(sessionId, { progress: 56, currentStepLabel: '多头质证完成，空头质证中…' })
  await addDebateRow(sessionId, 3, 'crossexam', 'bear', 'bear', bearC.content)
  await updateSession(sessionId, { progress: 58, currentStepLabel: 'R4 结辩：双方最后陈述…' })

  const fullDebate = [bull.content, bear.content, bullR.content, bearR.content, bullC.content, bearC.content].join('\n')
  const [bullF, bearF] = await Promise.all([bullClosingArg(pack, fullDebate), bearClosingArg(pack, fullDebate)])
  await addDebateRow(sessionId, 4, 'closing', 'bull', 'bull', bullF.content)
  await updateSession(sessionId, { progress: 60, currentStepLabel: '多头结辩完成，空头结辩中…' })
  await addDebateRow(sessionId, 4, 'closing', 'bear', 'bear', bearF.content)
  await updateSession(sessionId, { progress: 62, currentStepLabel: '冲突检测中…' })

  for (const [key, turn] of Object.entries({bull, bear, bullR, bearR, bullC, bearC, bullF, bearF})) {
    if (turn.error) audit.failedAgents.push(`debate:${key}`)
  }

  // Conflict detection（PRD 第 17 节）：观点分差 ≥ 2 档触发（第 5 轮）
  let conflictNote = ''
  const votesSoFar: { name: string; vote: VoteType | null; summary: string }[] = coreOutputs.map(({ name, out }) => ({
    name,
    vote: out.vote,
    summary: out.summary,
  }))
  const voteNum = (v: VoteType | null) => (v === 'BUY' ? 1 : v === 'SELL' ? -1 : 0)
  let pairA: (typeof votesSoFar)[number] | null = null
  let pairB: (typeof votesSoFar)[number] | null = null
  let maxSpread = 0
  for (let i = 0; i < votesSoFar.length; i++) {
    for (let j = i + 1; j < votesSoFar.length; j++) {
      const spread = Math.abs(voteNum(votesSoFar[i].vote) - voteNum(votesSoFar[j].vote))
      if (spread > maxSpread) {
        maxSpread = spread
        pairA = votesSoFar[i]
        pairB = votesSoFar[j]
      }
    }
  }
  if (maxSpread >= 2 && pairA && pairB) {
    conflictNote = `${pairA.name}(${pairA.vote}) 与 ${pairB.name}(${pairB.vote}) 存在观点冲突，已触发针对性再论证。`
    await updateSession(sessionId, { currentStepLabel: '⚡ 检测到观点冲突，触发针对性论证…' })
    const turns = await conflictResolution(
      pack,
      pairA.name, pairA.vote ?? 'HOLD', pairA.summary,
      pairB.name, pairB.vote ?? 'HOLD', pairB.summary,
    )
    turns.forEach((turn, i) => { if (turn.error) audit.failedAgents.push(`conflict:${i + 1}`) })
    await addDebateRow(sessionId, 5, 'conflict', 'conflict', 'neutral', `⚡ 观点冲突检测：${pairA.name}（${pairA.vote}）与 ${pairB.name}（${pairB.vote}）意见相左，系统要求双方进一步论证。`)
    const stanceOf = (v: VoteType | null) => (voteNum(v) > 0 ? 'bull' : voteNum(v) < 0 ? 'bear' : 'neutral')
    if (turns[0]) await addDebateRow(sessionId, 5, 'conflict', 'conflict', stanceOf(pairA.vote), `${pairA.name}：${turns[0].content}`)
    if (turns[1]) await addDebateRow(sessionId, 5, 'conflict', 'conflict', stanceOf(pairB.vote), `${pairB.name}：${turns[1].content}`)
    await updateSession(sessionId, { progress: 64, currentStepLabel: '冲突仲裁完成' })
  }

  // ===== 5. Risk Officer =====
  await updateSession(sessionId, { status: 'risk_review', progress: 66, currentStepLabel: '首席风险官独立审查中…' })
  const debateSummary = [bull.content, bear.content, bullR.content, bearR.content, bullC.content, bearC.content, bullF.content, bearF.content].join('\n')
  const risk = await riskAgent(pack, agentSummaries, debateSummary)
  const riskOut: RiskOutput = risk.output
  riskOut.evidence=riskOut.evidence.map(c=>checkCitation({...c,agentKey:'risk'},audit.records,capturedAt))
  audit.claims.push(...riskOut.evidence)
  audit.stageDurationsMs.risk=risk.durationMs
  await addAgentRow(sessionId, 'risk', risk.error ? {...riskOut,score:null,vote:null,confidence:null} : riskOut, risk.durationMs, {
    executionStatus:risk.error ? 'failed' : 'ok',
    riskLevel: risk.error ? null : riskOut.riskLevel,
    riskPenalty: risk.error ? null : riskOut.riskPenalty,
    topRisks: riskOut.topRisks,
  })
  await addDebateRow(sessionId, 6, 'risk', 'risk', 'risk', risk.error ? '【风控审查未完成】暂停评级与仓位建议，需要人工复核。' : `【风控审查】风险等级 ${riskOut.riskLevel}，风险惩罚 -${riskOut.riskPenalty} 分。${riskOut.summary} Top 风险：${riskOut.topRisks.join('；')}`)
  await updateSession(sessionId, { progress: 70, currentStepLabel: '风控审查完成' })

  audit.decisionGate=evaluateGate({records:audit.records,claims:audit.claims,
    riskStatus:risk.error ? 'failed' : 'ok',failedAgents:audit.failedAgents,quantitativeReady,now:new Date().toISOString()})
  if (!audit.decisionGate.canPublishDecision) {
    audit.stageDurationsMs.total=Date.now()-runStarted
    audit.reportMd=buildReviewReport({runId:sessionId,stockName,query,records:audit.records,gate:audit.decisionGate,claims:audit.claims})
    await updateSession(sessionId,{status:'completed',progress:100,meta,currentStepLabel:`研究结束：${GATE_LABELS[audit.decisionGate.status]}，未生成投资评级`})
    return
  }
  await updateSession(sessionId,{meta})

  // ===== 6. Voting =====
  await updateSession(sessionId, { status: 'voting', progress: 73, currentStepLabel: '投资委员会加权投票中…' })
  const scoreInput: ScoreInput = {
    fundamental: fund.output.score,
    valuation: qMetrics.valuation,
    industry: ind.output.score,
    macro: mac.output.score,
    momentum: qMetrics.momentum,
    sentiment: sen.output.score,
    risk: riskOut.score,
    votes: [
      { key: 'fundamental', vote: fund.output.vote },
      { key: 'quant', vote: qnt.output.vote },
      { key: 'industry', vote: ind.output.vote },
      { key: 'macro', vote: mac.output.vote },
      { key: 'sentiment', vote: sen.output.vote },
      { key: 'risk', vote: riskOut.vote },
    ],
    riskPenalty: riskOut.riskPenalty,
    riskLevel: riskOut.riskLevel,
  }
  const score = computeScore(scoreInput)
  await updateSession(sessionId, { progress: 76, currentStepLabel: `投票完成：${score.voteSummary.filter((v) => v.vote === 'BUY').length} 票 BUY / ${score.voteSummary.filter((v) => v.vote === 'HOLD').length} 票 HOLD / ${score.voteSummary.filter((v) => v.vote === 'SELL').length} 票 SELL` })

  // ===== 7. CIO Decision =====
  await updateSession(sessionId, { status: 'decision', progress: 80, currentStepLabel: 'CIO 综合裁决中…' })
  const pos = buildDecision({ score, confidence: 60, horizon: '12-24个月', keyLogic: [], keyRisks: [], thesis: [], riskLevel: riskOut.riskLevel })
  const cio = await cioAgent(pack, {
    dimensionScores: score.dimensionScores,
    initialScore: score.initialScore,
    riskPenalty: score.riskPenalty,
    finalScore: score.finalScore,
    rating: score.rating,
    positionMin: pos.positionMin,
    positionMax: pos.positionMax,
    voteSummary: score.voteSummary.map((v) => `${v.agentName}(${v.weight > 0 ? Math.round(v.weight * 100) : 0}%权重)：${v.vote}`).join('；'),
    riskLevel: riskOut.riskLevel,
    topRisks: riskOut.topRisks,
    conflictNote,
  })
  const allVotes = score.voteSummary.map((v) => v.vote)
  const confidence = adjustConfidence(cio?.confidence ?? 60, allVotes)
  const decision = buildDecision({
    score,
    confidence,
    horizon: cio?.horizon ?? '12-24个月',
    keyLogic: cio?.keyLogic?.length ? cio.keyLogic : fund.output.highlights.slice(0, 4),
    keyRisks: cio?.keyRisks?.length ? cio.keyRisks : riskOut.topRisks,
    thesis:
      cio?.thesis?.length
        ? cio.thesis
        : [
            { title: 'Growth', points: fund.output.highlights.slice(0, 2) },
            { title: 'Competitive Advantage', points: ind.output.highlights.slice(0, 2) },
            { title: 'Valuation', points: qnt.output.highlights.slice(0, 2) },
            { title: 'Macro', points: mac.output.highlights.slice(0, 2) },
            { title: 'Risk', points: riskOut.topRisks.slice(0, 2) },
          ],
    riskLevel: riskOut.riskLevel,
  })

  const created = await db.finalDecision.create({
    data: {
      sessionId,
      initialScore: decision.initialScore,
      riskPenalty: decision.riskPenalty,
      finalScore: decision.finalScore,
      rating: decision.rating,
      confidence: decision.confidence,
      positionMin: decision.positionMin,
      positionMax: decision.positionMax,
      horizon: decision.horizon,
      riskLevel: decision.riskLevel,
      voteSummary: JSON.stringify(decision.voteSummary ?? []),
      thesis: JSON.stringify(decision.thesis ?? []),
      keyLogic: JSON.stringify(decision.keyLogic ?? []),
      keyRisks: JSON.stringify(decision.keyRisks ?? []),
      reportMd: null,
    },
  })
  await updateSession(sessionId, { progress: 86, currentStepLabel: `CIO 裁决：${decision.rating}（${decision.finalScore}/100）` })

  // ===== 8. Report =====
  await updateSession(sessionId, { status: 'report', progress: 90, currentStepLabel: '撰写投资研究报告…' })
  const agentSections = coreOutputs
    .map(({ name, out }) => `- ${name}（${out.score ?? 'N/A'}分，${out.vote ?? 'N/A'}）：${out.summary}`)
    .join('\n')
  const voteSummaryStr = score.voteSummary.map((v) => `${v.agentName}: ${v.vote}（权重 ${Math.round(v.weight * 100)}%）`).join('；')
  let reportMd = await reportAgent(pack, {
    finalScore: decision.finalScore,
    rating: decision.rating,
    confidence: decision.confidence,
    position: `${decision.positionMin}-${decision.positionMax}%`,
    horizon: decision.horizon,
    riskLevel: decision.riskLevel,
    keyLogic: decision.keyLogic ?? [],
    keyRisks: decision.keyRisks ?? [],
    agentSections,
    voteSummary: voteSummaryStr,
  })
  if(reportMd) {
    const annual=reviewFinancialSemantics({report:reportMd},{records:audit.records,contexts:pack.filingContexts??[],now:capturedAt})
    const reporting=reviewReportingClaims({report:reportMd},{records:audit.records,contexts:pack.filingContexts??[]})
    const issues=[...annual.issues,...reporting.issues]
    audit.reportReview={status:issues.length?'review_required':'no_issue_detected',issues,completeSemanticVerification:false,...(issues.length?{originalDraft:reportMd}:{})}
    if(issues.length) reportMd=null
  }
  if (!reportMd) {
    reportMd = fallbackReport(stockName, finalTarget?.code ?? limitedCode, decision, agentSections, voteSummaryStr, riskOut)
  }
  await db.finalDecision.update({ where: { id: created.id }, data: { reportMd } })
  audit.stageDurationsMs.total=Date.now()-runStarted
  await updateSession(sessionId, { status: 'completed', progress: 100, meta, currentStepLabel: `研究完成：${decision.rating}` })
}

function fallbackReport(
  stockName: string,
  code: string | null,
  d: Omit<DecisionDTO, 'id' | 'sessionId' | 'createdAt'>,
  agentSections: string,
  voteSummary: string,
  risk: RiskOutput,
): string {
  return `# ${stockName}${code ? `(${code})` : ''} 投资研究报告

> 注：LLM 报告生成受限，本报告由系统以结构化数据自动汇编。

## 一、执行摘要
AI 投资委员会最终评级 **${d.rating}**，Investment Score **${d.finalScore}/100**（初始分 ${d.initialScore}，风险惩罚 -${d.riskPenalty}），置信度 **${d.confidence}%**，建议仓位 **${d.positionMin}-${d.positionMax}%**，投资周期 ${d.horizon}，风险等级 **${d.riskLevel}**。

## 二、投委会决议
- 核心投资逻辑：
${(d.keyLogic ?? []).map((k) => `  - ${k}`).join('\n')}
- 主要风险：
${(d.keyRisks ?? []).map((k) => `  - ${k}`).join('\n')}

## 三、投委投票
${voteSummary}

## 四、各 Agent 分析摘要
${agentSections}

## 五、风险分析（Risk Officer）
- 风险等级：${risk.riskLevel}
- Top 风险：
${(risk.topRisks ?? []).map((k) => `  - ${k}`).join('\n')}

## 六、证据与数据来源
- 关键财务数字：公司年报/季报演示快照库（近似值）
- 新闻与舆情：实时网络检索（web_search）
- 估值与动量指标：系统量化引擎代码计算

*AI 生成投研内容，仅供研究参考，不构成投资建议。*
`
}

// ---------- DTO 映射 ----------

export function mapSession(s: {
  id: string; query: string; intent: string; groupId: string | null; stockCode: string | null; stockName: string | null; market: string | null; status: string; currentStepLabel: string | null; progress: number; error: string | null; meta: string | null; createdAt: Date; updatedAt: Date
}): SessionDTO {
  let meta: PlanMeta | null = null
  if (s.meta) {
    try {
      meta = JSON.parse(s.meta) as PlanMeta
    } catch {
      meta = null
    }
  }
  return {
    id: s.id,
    query: s.query,
    intent: s.intent,
    groupId: s.groupId,
    stockCode: s.stockCode,
    stockName: s.stockName,
    market: s.market,
    status: s.status as PipelineStatus,
    currentStepLabel: s.currentStepLabel,
    progress: s.progress,
    error: s.error,
    meta,
    createdAt: s.createdAt.toISOString(),
    updatedAt: s.updatedAt.toISOString(),
  }
}

export function mapAgent(a: { id: string; sessionId: string; agentKey: string; agentName: string; score: number | null; vote: string | null; confidence: number | null; summary: string | null; highlights: string | null; concerns: string | null; evidence: string | null; details: string | null; durationMs: number | null; createdAt: Date }): AgentDTO {
  const parse = <T,>(v: string | null, fb: T): T => {
    if (!v) return fb
    try {
      return JSON.parse(v) as T
    } catch {
      return fb
    }
  }
  return {
    id: a.id,
    sessionId: a.sessionId,
    agentKey: a.agentKey as AgentDTO['agentKey'],
    agentName: a.agentName,
    score: a.score,
    vote: (a.vote as VoteType) ?? null,
    confidence: a.confidence,
    summary: a.summary,
    highlights: parse<string[]>(a.highlights, []),
    concerns: parse<string[]>(a.concerns, []),
    evidence: parse(a.evidence, []),
    details: parse<Record<string, unknown> | null>(a.details, null),
    durationMs: a.durationMs,
    createdAt: a.createdAt.toISOString(),
  }
}

export function mapDebate(m: { id: string; sessionId: string; round: number; phase: string; speakerKey: string; speakerName: string; stance: string; content: string; createdAt: Date }): DebateDTO {
  return {
    id: m.id,
    sessionId: m.sessionId,
    round: m.round,
    phase: m.phase as DebateDTO['phase'],
    speakerKey: m.speakerKey,
    speakerName: m.speakerName,
    stance: m.stance as DebateDTO['stance'],
    content: m.content,
    createdAt: m.createdAt.toISOString(),
  }
}

export function mapDecision(d: { id: string; sessionId: string; initialScore: number; riskPenalty: number; finalScore: number; rating: string; confidence: number; positionMin: number; positionMax: number; horizon: string; riskLevel: string; voteSummary: string | null; thesis: string | null; keyLogic: string | null; keyRisks: string | null; reportMd: string | null; createdAt: Date } | null): DecisionDTO | null {
  if (!d) return null
  const parse = <T,>(v: string | null, fb: T): T => {
    if (!v) return fb
    try {
      return JSON.parse(v) as T
    } catch {
      return fb
    }
  }
  return {
    id: d.id,
    sessionId: d.sessionId,
    initialScore: d.initialScore,
    riskPenalty: d.riskPenalty,
    finalScore: d.finalScore,
    rating: d.rating as DecisionDTO['rating'],
    confidence: d.confidence,
    positionMin: d.positionMin,
    positionMax: d.positionMax,
    horizon: d.horizon,
    riskLevel: d.riskLevel as DecisionDTO['riskLevel'],
    voteSummary: parse(d.voteSummary, null),
    thesis: parse(d.thesis, null),
    keyLogic: parse(d.keyLogic, null),
    keyRisks: parse(d.keyRisks, null),
    reportMd: d.reportMd,
    createdAt: d.createdAt.toISOString(),
  }
}

export async function listSessions(limit = 12, ownerId?:string): Promise<SessionListItem[]> {
  const rows = await db.researchSession.findMany({
    where:{...(ownerId?{ownerId}:{}),NOT:{OR:[{id:{startsWith:'pdf_'}},{id:{startsWith:'fr_'}}]}},
    orderBy: { createdAt: 'desc' },
    take: limit,
    include: { decision: true },
  })
  return rows.map((s) => ({
    id: s.id,
    query: s.query,
    stockCode: s.stockCode,
    stockName: s.stockName,
    market: s.market,
    status: s.status as PipelineStatus,
    intent: s.intent,
    groupId: s.groupId,
    finalScore: s.decision?.finalScore ?? null,
    rating: s.decision?.rating ?? null,
    riskLevel: s.decision?.riskLevel ?? null,
    createdAt: s.createdAt.toISOString(),
  }))
}
