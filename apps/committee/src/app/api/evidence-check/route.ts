import { requireUser, authErrorResponse } from '@/lib/auth/server'
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { CORE_RESEARCH_CASES } from '@/lib/data/core-research-cases'
import { collectEvidence } from '@/lib/research-evidence/catalog'
import { buildReviewReport, evaluateGate, type ResearchAudit } from '@/lib/research-evidence/engine'

export const dynamic='force-dynamic'

/** A real deterministic check of registered sources, explicitly not an LLM run. */
export async function POST(req: NextRequest) {
 try {
  const user=await requireUser(req,{write:true})
  const body=await req.json().catch(()=>null)
  const selected=CORE_RESEARCH_CASES.find(c=>c.code===body?.stockCode)
  if (!selected) return NextResponse.json({error:'请从核心样本中选择有效标的'},{status:400})
  const started=Date.now(), capturedAt=new Date().toISOString()
  const records=collectEvidence({stockCode:selected.code,stock:null,news:[],financialClues:[],quote:null,capturedAt})
  const gate=evaluateGate({records,claims:[],riskStatus:'ok',failedAgents:[],quantitativeReady:false,now:capturedAt})
  // This mode doesn't run a risk officer. Never suggest a completed risk review.
  if (gate.status !== 'review_required') gate.status='limited'
  gate.canPublishDecision=false
  gate.reasons=gate.reasons.filter(r=>!r.startsWith('量化输入') && !r.startsWith('部分分析主张'))
  gate.reasons.push('本次仅核对已登记资料，未执行行情采集、多智能体研究或风控审查')
  const id=`ev_${crypto.randomUUID()}`
  const audit:ResearchAudit={version:'evidence-v1',runId:id,capturedAt,records,claims:[],decisionGate:gate,
    stageDurationsMs:{},failedAgents:[],modelEvaluation:'not_run'}
  audit.reportMd=buildReviewReport({runId:id,stockName:selected.name,query:selected.query,records,gate,claims:[]})
  audit.stageDurationsMs.evidenceCheck=Date.now()-started
    await db.researchSession.create({data:{ownerId:user.id,id,query:selected.query,stockCode:selected.code,stockName:selected.name,market:selected.code.startsWith('6')?'SH':'SZ',
      status:'completed',progress:100,currentStepLabel:'登记资料核对完成，未运行投资决策',
      meta:JSON.stringify({intent:'single',question:selected.query,stocks:[{code:selected.code,name:selected.name,market:selected.code.startsWith('6')?'SH':'SZ'}],plan:['核对已登记资料'],audit})}})
    return NextResponse.json({audit,sessionId:id})
  } catch (e) {
    const denied=authErrorResponse(e);if(denied)return denied
    return NextResponse.json({error:'证据记录保存失败，请检查数据库配置'},{status:500})
  }
}
