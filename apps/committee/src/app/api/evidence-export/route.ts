import { requireUser, authErrorResponse, ownerFilter } from '@/lib/auth/server'
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import type { ResearchAudit } from '@/lib/research-evidence/engine'

export const dynamic='force-dynamic'

/** Export the persisted snapshot, never silently rerun against changed sources. */
export async function GET(req: NextRequest) {
  const id=req.nextUrl.searchParams.get('runId') ?? ''
  const format=req.nextUrl.searchParams.get('format') ?? 'json'
  if(!/^(?:ev_[a-zA-Z0-9_-]{1,100}|c[a-z0-9]{24})$/.test(id) || !['json','md'].includes(format)) {
    return NextResponse.json({error:'导出参数无效'},{status:400})
  }
  try {
    const user=await requireUser(req)
    const session=await db.researchSession.findFirst({where:{id,...ownerFilter(user)},select:{meta:true}})
    const audit: ResearchAudit | undefined=session?.meta ? JSON.parse(session.meta).audit : undefined
    if(!audit || audit.version!=='evidence-v1' || audit.runId!==id || (format==='md' && !audit.reportMd)) {
      return NextResponse.json({error:'未找到该次核验记录'},{status:404})
    }
    return new Response(format==='json'?JSON.stringify(audit,null,2):audit.reportMd,{headers:{
      'Content-Type':format==='json'?'application/json; charset=utf-8':'text/markdown; charset=utf-8',
      'Content-Disposition':`attachment; filename="${id}.${format}"`,
      'Cache-Control':'no-store',
    }})
  } catch (e) {
    const denied=authErrorResponse(e);if(denied)return denied
    return NextResponse.json({error:'核验记录读取失败'},{status:500})
  }
}
