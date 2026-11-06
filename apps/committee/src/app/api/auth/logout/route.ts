import { NextResponse } from 'next/server'
import { assertSameOrigin } from '@/lib/auth/core'
import { authErrorResponse, clearLoginCookie } from '@/lib/auth/server'
export async function POST(req:Request) {
 try {assertSameOrigin(req);const res=NextResponse.json({ok:true});await clearLoginCookie(req,res);return res}
 catch(e){return authErrorResponse(e)??NextResponse.json({error:'退出失败'},{status:500})}
}
