import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { assertSameOrigin, hashPassword, validateCredentials, AuthError } from '@/lib/auth/core'
import { authErrorResponse, consumeAuthBudget, setLoginCookie } from '@/lib/auth/server'
export const dynamic='force-dynamic'
export async function POST(req:Request) {
 try {
  assertSameOrigin(req)
  await consumeAuthBudget('register:global',30)
  const body=await req.json().catch(()=>null),{username,password}=validateCredentials(body)
  if(body?.role&&body.role!=='USER')throw new AuthError('注册账号只能使用普通用户身份',400)
  const displayName=typeof body?.displayName==='string'?body.displayName.trim().slice(0,40):username
  if(await db.user.findUnique({where:{username}}))throw new AuthError('该用户名已被使用',409)
  const user=await db.user.create({data:{username,displayName:displayName||username,passwordHash:await hashPassword(password),role:'USER'},select:{id:true,username:true,displayName:true,role:true}})
  const res=NextResponse.json({user},{status:201});await setLoginCookie(req,res,user.id);return res
 } catch(e) {return authErrorResponse(e)??NextResponse.json({error:'注册失败，请稍后重试'},{status:500})}
}
