import { NextRequest, NextResponse } from 'next/server'
import { requireUser, authErrorResponse, ownerFilter } from '@/lib/auth/server'
import { db } from '@/lib/db'
import { collectCompanyNews } from '@/lib/ai/search'

export const dynamic = 'force-dynamic'

/** Latest browsing feed; never rewrites the evidence snapshot of a saved report. */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const user = await requireUser(req)
    const { id } = await params
    const session = await db.researchSession.findFirst({ where: { id, ...ownerFilter(user) }, select: { stockName: true, stockCode: true } })
    if (!session) return NextResponse.json({ error: '研究不存在或无权访问' }, { status: 404 })
    const news = session.stockName || session.stockCode ? await collectCompanyNews(session.stockName ?? '', session.stockCode ?? '') : []
    return NextResponse.json({ news, status: news.length ? 'ok' : 'empty', fetchedAt: new Date().toISOString() }, { headers: { 'Cache-Control': 'no-store' } })
  } catch (error) {
    const denied = authErrorResponse(error)
    if (denied) return denied
    return NextResponse.json({ status: 'failed', error: '新闻来源暂时连接失败，请点击刷新重试。' }, { status: 502, headers: { 'Cache-Control': 'no-store' } })
  }
}
