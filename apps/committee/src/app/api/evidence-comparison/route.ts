import { requireUser, authErrorResponse } from '@/lib/auth/server'
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import facts from '@/lib/data/verified-facts.json'
import contexts from '@/lib/data/filing-context.json'
import { buildFinancialComparisonReport, compareFinancialEvidence, type EvidenceRecord, type FilingContext, type ResearchAudit } from '@/lib/research-evidence/engine'

export const dynamic='force-dynamic'

/** Fixed annual case, no network/LLM calls and no investment winner. */
export async function POST(req: NextRequest) {
 try {
  const user=await requireUser(req,{write:true})
  const body=await req.json().catch(()=>null)
  if(body?.caseId!=='D02') return NextResponse.json({error:'请选择有效案例 D02'},{status:400})
  const started=Date.now(), capturedAt=new Date().toISOString(), id=`ev_${crypto.randomUUID()}`
  const records=(facts as EvidenceRecord[]).filter(r=>['600519','000858'].includes(r.stockCode)).map(r=>({...r}))
  const financialComparison=compareFinancialEvidence({records,contexts:contexts as FilingContext[],now:capturedAt})
  const audit: ResearchAudit={version:'evidence-v1',runId:id,capturedAt,records,claims:[],failedAgents:[],
    modelEvaluation:'not_run',stageDurationsMs:{},financialComparison,
    decisionGate:{status:financialComparison.status==='review_required'?'review_required':'limited',canPublishDecision:false,
      checkedAt:capturedAt,reasons:[...financialComparison.reasons,'本次完成限定范围的年度财务对比，未执行估值、多智能体研究或风控审查']}}
  audit.reportMd=buildFinancialComparisonReport({comparison:financialComparison,runId:id,capturedAt,records})
  audit.stageDurationsMs.evidenceComparison=Date.now()-started
  const query='比较贵州茅台与五粮液2025年度营业收入、归母净利润与经营现金流，展示公式、来源和财务口径限制。'
    await db.researchSession.create({data:{ownerId:user.id,id,query,intent:'comparison',stockName:'贵州茅台—五粮液',status:'completed',progress:100,
      currentStepLabel:financialComparison.status==='comparable'?'年度财务证据对比完成，未运行投资决策':'年度财务对比受限，请复核资料',
      meta:JSON.stringify({intent:'comparison',question:query,stocks:[{code:'600519',name:'贵州茅台',market:'SH'},{code:'000858',name:'五粮液',market:'SZ'}],
        plan:['核对六项同口径年报金额','按确定性公式计算辅助指标','披露财务口径与解读限制'],audit})}})
    return NextResponse.json({audit,sessionId:id})
  } catch (e) {
    const denied=authErrorResponse(e);if(denied)return denied
    return NextResponse.json({error:'对比记录保存失败，请检查数据库配置'},{status:500})
  }
}
