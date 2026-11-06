import { NextRequest, NextResponse } from 'next/server'
import { resolveQuery } from '@/lib/research/resolve-query'
export const dynamic='force-dynamic'
/** Local interpretation only. No model calls and no stored research. */
export async function POST(req:NextRequest) {
  try {
    const body=await req.json().catch(()=>null)
    return NextResponse.json(await resolveQuery(body?.query))
  } catch(e) {
    return NextResponse.json({error:e instanceof Error ? e.message:'问题解析失败，请重试'},{status:400})
  }
}
