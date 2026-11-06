import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { assertSameOrigin, validateCredentials, verifyPassword, AuthError } from '@/lib/auth/core'
import { authErrorResponse, consumeAuthBudget, setLoginCookie } from '@/lib/auth/server'
export const dynamic='force-dynamic'
// Valid synthetic hash forces the same password derivation for unknown names.
const DUMMY_HASH='scrypt:'+('00'.repeat(16))+':'+('00'.repeat(64))
export async function POST(req:Request) {
 try {
  assertSameOrigin(req)
  await consumeAuthBudget('login:global',150)
  const {username,password}=validateCredentials(await req.json().catch(()=>null))
  await consumeAuthBudget('login:user:'+username,10)
  const row=await db.user.findUnique({where:{username}})
  const valid=await verifyPassword(password,row?.passwordHash??DUMMY_HASH)
  if(!row||!valid||row.disabled)throw new AuthError('用户名或密码错误，或账号已停用',401)
  const {id,displayName,role}=row,user={id,username,displayName,role}
  const res=NextResponse.json({user});await setLoginCookie(req,res,id);return res
 } catch(e){return authErrorResponse(e)??NextResponse.json({error:'登录失败，请稍后重试'},{status:500})}
}
