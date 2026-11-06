import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { AuthError, authErrorResponse, requireUser } from '@/lib/auth/server'
export const dynamic='force-dynamic'
export async function GET(req:Request) {
 try {
  await requireUser(req,{admin:true})
  const users=await db.user.findMany({take:200,orderBy:{createdAt:'desc'},select:{id:true,username:true,displayName:true,role:true,disabled:true,createdAt:true}})
  return NextResponse.json({users},{headers:{'Cache-Control':'no-store'}})
 } catch(e){return authErrorResponse(e)??NextResponse.json({error:'读取账户失败'},{status:500})}
}
export async function PATCH(req:Request) {
 try {
  const admin=await requireUser(req,{admin:true,write:true}),body=await req.json().catch(()=>null)
  if(typeof body?.id!=='string'||typeof body?.disabled!=='boolean')throw new AuthError('账户或停用状态无效',400)
  if(body.id===admin.id)throw new AuthError('不能通过此页面停用当前管理员',400)
  await db.$transaction(async tx=>{
   const user=await tx.user.findUnique({where:{id:body.id}})
   if(!user)throw new AuthError('账户不存在',404)
   if(user.role==='ADMIN'&&body.disabled&&(await tx.user.count({where:{role:'ADMIN',disabled:false}}))<=1)throw new AuthError('至少保留一名有效管理员',400)
   await tx.user.update({where:{id:user.id},data:{disabled:body.disabled}})
   if(body.disabled)await tx.authSession.deleteMany({where:{userId:user.id}})
  })
  return NextResponse.json({ok:true})
 } catch(e){return authErrorResponse(e)??NextResponse.json({error:'修改账户失败'},{status:500})}
}
