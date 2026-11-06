import { requireUser, authErrorResponse, ownerFilter } from '@/lib/auth/server'
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { tryChatJSON } from '@/lib/ai/llm'
import type { ComparisonVerdict } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const maxDuration = 120

interface SessionWithDecision {
  id: string
  status: string
  meta: string | null
  stockName: string | null
  stockCode: string | null
  decision: {
    finalScore: number
    rating: string
    confidence: number
    keyLogic: string | null
    keyRisks: string | null
    riskLevel: string
  } | null
  agents: { agentKey: string; agentName: string; score: number | null; summary: string | null }[]
}

function parseStrArr(v: string | null): string[] {
  if (!v) return []
  try {
    const arr = JSON.parse(v)
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

function strongestWeakest(session: SessionWithDecision): { strongest: string; weakest: string } {
  const scored = session.agents
    .filter((a) => a.agentKey !== 'risk' && typeof a.score === 'number')
    .sort((x, y) => (y.score ?? 0) - (x.score ?? 0))
  const fmt = (a: { agentName: string; score: number | null; summary: string | null } | undefined, label: string) =>
    a ? `${a.agentName}（${a.score}分）：${(a.summary ?? '').slice(0, 60)}` : label
  return { strongest: fmt(scored[0], 'Data unavailable'), weakest: fmt(scored[scored.length - 1], 'Data unavailable') }
}

/** POST /api/compare — { groupId } 两个标的对比裁决（双方完成后生成并缓存） */
export async function POST(req: NextRequest) {
  try {
    const user=await requireUser(req,{write:true})
    const body = (await req.json().catch(() => null)) as { groupId?: string } | null
    const groupId = body?.groupId
    if (typeof groupId!=='string'||!groupId||groupId.length>100) return NextResponse.json({ error: '缺少 groupId' }, { status: 400 })

    const sessions = (await db.researchSession.findMany({
      where: { groupId, ...ownerFilter(user) },
      orderBy: { orderIndex: 'asc' },
      include: { decision: true, agents: true },
    })) as unknown as SessionWithDecision[]

    if(sessions.length!==2)return NextResponse.json({error:'对比记录不存在或组成员不完整'},{status:404})
    const blocked = sessions.some(s=>{
      try {
        const gate=JSON.parse(s.meta ?? '{}')?.audit?.decisionGate
        return gate && !gate.canPublishDecision
      } catch { return true }
    })
    if (blocked || sessions.some(s=>s.status==='failed') || sessions.some(s=>s.status==='completed' && !s.decision)) {
      return NextResponse.json({verdict:null,status:'blocked',reason:'至少一方资料不足、引用需复核或研究失败，本轮不生成胜者及配置建议。请查看双方证据与研究边界。'})
    }
    // Check gates before consulting a cached verdict.
    const cached = await db.comparisonResult.findUnique({ where: { groupId } })
    if (cached) {
      try { return NextResponse.json({verdict:JSON.parse(cached.result) as ComparisonVerdict}) } catch { /* regenerate */ }
    }

    const ready = sessions.filter((s) => s.decision)
    if (ready.length < 2) {
      return NextResponse.json({ verdict: null })
    }

    const [a, b] = ready
    const ctx = (s: SessionWithDecision) => ({
      name: `${s.stockName ?? '标的'}${s.stockCode ? `(${s.stockCode})` : ''}`,
      stockCode: s.stockCode ?? '',
      finalScore: s.decision!.finalScore,
      rating: s.decision!.rating,
      confidence: s.decision!.confidence,
      riskLevel: s.decision!.riskLevel,
      logic: parseStrArr(s.decision!.keyLogic),
      risks: parseStrArr(s.decision!.keyRisks),
      ...strongestWeakest(s),
    })
    const A = ctx(a)
    const B = ctx(b)

    const verdict = await tryChatJSON<ComparisonVerdict>(
      `你是基金公司首席投资官（CIO）。两个研究小组分别完成了两只股票的完整投委会流程，请给出对比裁决。
要求：winner 为更值得投资一方的名称；summary ≤120字；dimensions 给 3-5 个对比维度（如 成长性/盈利质量/估值/风险/行业地位），better 为占优一方名称，reason ≤40字；allocationSuggestion 给出两者之间的配置建议（≤60字）；rows 按给定数据填写，不要修改数字。只输出合法 JSON。
输出 {"winner":"...","summary":"...","dimensions":[{"name":"...","better":"...","reason":"..."}],"allocationSuggestion":"...","rows":[{"stockName":"...","stockCode":"...","finalScore":<int>,"rating":"...","confidence":<int>,"strongest":"...","weakest":"..."}]}`,
      `标的研究结论：
A：${JSON.stringify(A)}
B：${JSON.stringify(B)}`,
      90_000,
    )

    if (!verdict || !verdict.winner || !Array.isArray(verdict.rows)) {
      // LLM 失败 → 结构化降级（代码拼装，数字不编造）
      const fallbackVerdict: ComparisonVerdict = {
        winner: A.finalScore >= B.finalScore ? A.name : B.name,
        summary: `投委会评分对比：${A.name} ${A.finalScore}分（${A.rating}） vs ${B.name} ${B.finalScore}分（${B.rating}）。评分更高者综合性价比更优，置信度分别为 ${A.confidence}% / ${B.confidence}%。`,
        dimensions: [
          { name: '综合评分', better: A.finalScore >= B.finalScore ? A.name : B.name, reason: `${Math.max(A.finalScore, B.finalScore)} vs ${Math.min(A.finalScore, B.finalScore)}` },
          { name: '决策置信度', better: A.confidence >= B.confidence ? A.name : B.name, reason: `${Math.max(A.confidence, B.confidence)}% vs ${Math.min(A.confidence, B.confidence)}%` },
          { name: '风险水平', better: A.riskLevel <= B.riskLevel ? A.name : B.name, reason: `${A.riskLevel} vs ${B.riskLevel}` },
        ],
        allocationSuggestion: '建议以评分与置信度加权决定两者配置比例，风险等级较高一方适当低配。',
        rows: [
          { stockName: A.name, stockCode: '', finalScore: A.finalScore, rating: A.rating, confidence: A.confidence, strongest: A.strongest, weakest: A.weakest },
          { stockName: B.name, stockCode: '', finalScore: B.finalScore, rating: B.rating, confidence: B.confidence, strongest: B.strongest, weakest: B.weakest },
        ],
      }
      await db.comparisonResult.create({ data: { ownerId:user.id, groupId, result: JSON.stringify(fallbackVerdict) } })
      return NextResponse.json({ verdict: fallbackVerdict })
    }

    // rows 权威数字回填
    const rows = verdict.rows.slice(0, 2).map((r, i) => {
      const src = i === 0 ? A : B
      return {
        stockName: src.name,
        stockCode: src.stockCode ?? '',
        finalScore: src.finalScore,
        rating: src.rating,
        confidence: src.confidence,
        strongest: typeof r?.strongest === 'string' && r.strongest ? r.strongest : src.strongest,
        weakest: typeof r?.weakest === 'string' && r.weakest ? r.weakest : src.weakest,
      }
    })
    const normalized: ComparisonVerdict = { ...verdict, rows }
    await db.comparisonResult.upsert({
      where: { groupId },
      create: { ownerId:user.id, groupId, result: JSON.stringify(normalized) },
      update: { result: JSON.stringify(normalized) },
    })
    return NextResponse.json({ verdict: normalized })
  } catch (e) {
    const denied=authErrorResponse(e);if(denied)return denied
    console.error('[api/compare POST]', e)
    return NextResponse.json({ error: '生成对比裁决失败' }, { status: 500 })
  }
}
