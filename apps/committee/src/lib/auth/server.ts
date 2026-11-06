import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { AuthError, assertSameOrigin, createToken, hashToken, type AuthUser } from './core'
export { AuthError, ownerFilter } from './core'
export const SESSION_COOKIE='investment_session'
const SESSION_SECONDS=12*60*60
export function readToken(req:Request) {
  const entry=(req.headers.get('cookie')??'').split(';').map(v=>v.trim()).find(v=>v.startsWith(SESSION_COOKIE+'='))
  const value=entry?.slice(SESSION_COOKIE.length+1)??''
  return /^[a-zA-Z0-9_-]{43}$/.test(value)?value:null
}
export async function currentUser(req:Request):Promise<AuthUser|null> {
  const token=readToken(req);if(!token)return null
  const session=await db.authSession.findUnique({where:{tokenHash:hashToken(token)},include:{user:true}})
  if(!session||session.expiresAt<=new Date()||session.user.disabled)return null
  const {id,username,displayName,role}=session.user
  return {id,username,displayName,role}
}
export async function requireUser(req:Request,options:{write?:boolean;admin?:boolean}={}) {
  if(options.write)assertSameOrigin(req)
  const user=await currentUser(req)
  if(!user)throw new AuthError('请登录后使用个人研究功能',401)
  if(options.admin&&user.role!=='ADMIN')throw new AuthError('此操作需要管理员身份',403)
  return user
}
export function authErrorResponse(error:unknown) {
  return error instanceof AuthError?NextResponse.json({error:error.message},{status:error.status,headers:{'Cache-Control':'no-store'}}):null
}
function cookieOptions(req:Request) {
  return {httpOnly:true,sameSite:'lax' as const,secure:(process.env.APP_ORIGIN??req.url).startsWith('https:'),path:'/',maxAge:SESSION_SECONDS}
}
export async function setLoginCookie(req:Request,res:NextResponse,userId:string) {
  const token=createToken()
  await db.authSession.create({data:{tokenHash:hashToken(token),userId,expiresAt:new Date(Date.now()+SESSION_SECONDS*1000)}})
  res.cookies.set(SESSION_COOKIE,token,cookieOptions(req))
  res.headers.set('Cache-Control','no-store')
}
export async function clearLoginCookie(req:Request,res:NextResponse) {
  const token=readToken(req)
  if(token)await db.authSession.deleteMany({where:{tokenHash:hashToken(token)}})
  res.cookies.set(SESSION_COOKIE,'',{...cookieOptions(req),maxAge:0})
}
// SQL backed limits also apply after a process restart. The local application does
// not trust forwarded IP headers; both username and all-auth global buckets apply.
export async function consumeAuthBudget(name:string,limit:number) {
  const now=new Date(),cutoff=new Date(now.getTime()-15*60*1000)
  await db.$transaction(async tx=>{
    const row=await tx.authThrottle.findUnique({where:{key:name}})
    if(row&&row.windowStart>cutoff&&row.attempts>=limit)throw new AuthError('尝试次数较多，请15分钟后重试',429)
    await tx.authThrottle.upsert({where:{key:name},create:{key:name,windowStart:now,attempts:1},update:!row||row.windowStart<=cutoff?{windowStart:now,attempts:1}:{attempts:{increment:1}}})
  })
}
