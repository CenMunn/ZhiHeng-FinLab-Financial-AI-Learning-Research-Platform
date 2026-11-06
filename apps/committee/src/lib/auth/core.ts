import { randomBytes, createHash, scrypt, timingSafeEqual } from 'node:crypto'

export class AuthError extends Error {
  status: number
  constructor(message: string, status = 401) { super(message); this.status = status }
}
export type AuthUser = { id: string; username: string; displayName: string; role: string }
export function validateCredentials(input: unknown) {
  const body=input as Record<string,unknown>|null
  const username=typeof body?.username==='string'?body.username.trim().toLowerCase():''
  const password=typeof body?.password==='string'?body.password:''
  if(!/^[a-z0-9_]{3,32}$/.test(username))throw new AuthError('用户名需为3—32位字母、数字或下划线',400)
  if(password.length<8||password.length>128||!/[a-zA-Z]/.test(password)||!/[0-9]/.test(password))throw new AuthError('密码需为8—128位，至少包含字母和数字',400)
  return {username,password}
}
const derive=(password:string,salt:Buffer)=>new Promise<Buffer>((resolve,reject)=>scrypt(password,salt,64,{N:32768,r:8,p:1,maxmem:64*1024*1024},(e,key)=>e?reject(e):resolve(key)))
export async function hashPassword(password:string) {
  const salt=randomBytes(16),key=await derive(password,salt)
  return `scrypt:${salt.toString('hex')}:${key.toString('hex')}`
}
export async function verifyPassword(password:string,stored:string) {
  const [algorithm,salt,key,...extra]=stored.split(':')
  if(algorithm!=='scrypt'||extra.length||!/^[a-f0-9]{32}$/.test(salt??'')||!/^[a-f0-9]{128}$/.test(key??'')||password.length>128)return false
  return timingSafeEqual(await derive(password,Buffer.from(salt,'hex')),Buffer.from(key,'hex'))
}
export const createToken=()=>randomBytes(32).toString('base64url')
export const hashToken=(token:string)=>createHash('sha256').update(token).digest('hex')
export const ownerFilter=(user:Pick<AuthUser,'id'|'role'>)=>user.role==='ADMIN'?{}:{ownerId:user.id}
export function assertSameOrigin(req:Request) {
  const url=new URL(req.url),host=req.headers.get('host')
  if(host&&/[\s/\\@?#]/.test(host))throw new AuthError('请求来源校验失败',403)
  // Next normalizes a loopback request URL to localhost even when its HTTP Host
  // is 127.0.0.1. Use the exact authority seen by the browser. Reverse proxies
  // must set APP_ORIGIN; forwarded host headers are deliberately not trusted.
  const expected=process.env.APP_ORIGIN?new URL(process.env.APP_ORIGIN).origin:host?`${url.protocol}//${host}`:url.origin
  if(req.headers.get('origin')!==expected||req.headers.get('sec-fetch-site')==='cross-site')throw new AuthError('请求来源校验失败，请在本应用页面操作',403)
}
