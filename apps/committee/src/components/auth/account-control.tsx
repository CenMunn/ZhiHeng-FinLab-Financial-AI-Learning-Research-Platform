'use client'
import {useEffect,useState,type FormEvent} from 'react'
import {LogIn,LogOut,ShieldCheck,UserRound} from 'lucide-react'
import {useAuth,type AccountUser} from './auth-provider'
import {Button} from '@/components/ui/button'
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog'
import {Input} from '@/components/ui/input'
type ManagedUser=AccountUser&{disabled:boolean;createdAt:string}
function AdminDialog({open,onClose}:{open:boolean;onClose:()=>void}) {
 const {user}=useAuth(),[rows,setRows]=useState<ManagedUser[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const load=async()=>{const res=await fetch('/api/admin/users',{cache:'no-store'}),body=await res.json();if(!res.ok)throw Error(body.error);setRows(body.users)}
 useEffect(()=>{if(open)void load().catch(e=>setError(e.message))},[open])
 const toggle=async(row:ManagedUser)=>{
  setBusy(true);setError('')
  try {const res=await fetch('/api/admin/users',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:row.id,disabled:!row.disabled})});if(!res.ok)throw Error((await res.json()).error);await load()}
  catch(e){setError(e instanceof Error?e.message:'操作失败')}finally{setBusy(false)}
 }
 return <Dialog open={open} onOpenChange={v=>{if(!v)onClose()}}><DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"><DialogHeader><DialogTitle>账户管理</DialogTitle><DialogDescription>管理员可查看账户和停用状态。停用会立即撤销该账户的登录会话。</DialogDescription></DialogHeader>
  {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
  <div className="space-y-2">{rows.map(row=><div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"><div><p className="text-sm font-medium">{row.displayName} <span className="text-muted-foreground">@{row.username}</span></p><p className="mt-1 text-xs text-muted-foreground">{row.role==='ADMIN'?'管理员':'普通用户'} · {row.disabled?'已停用':'有效'}</p></div><Button size="sm" variant="outline" disabled={busy||row.id===user?.id} onClick={()=>void toggle(row)}>{row.id===user?.id?'当前管理员':row.disabled?'启用':'停用'}</Button></div>)}</div>
 </DialogContent></Dialog>
}
export function AccountControl() {
 const {user,loading,open,setOpen,refresh,logout}=useAuth()
 const [mode,setMode]=useState<'login'|'register'>('login'),[username,setUsername]=useState(''),[password,setPassword]=useState(''),[displayName,setDisplayName]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[adminOpen,setAdminOpen]=useState(false)
 const submit=async(e:FormEvent)=>{
  e.preventDefault();setError('');setBusy(true)
  try {const res=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,...(mode==='register'?{displayName}:{})})});const body=await res.json();if(!res.ok)throw Error(body.error??'登录失败');setPassword('');await refresh();setOpen(false)}
  catch(e){setError(e instanceof Error?e.message:'请稍后重试')}finally{setBusy(false)}
 }
 return <>
  {loading?<span className="text-xs text-muted-foreground">账户加载中</span>:user?<div className="flex items-center gap-1.5">
   <span className="hidden max-w-28 truncate text-xs text-muted-foreground sm:inline"><UserRound className="mr-1 inline size-3.5"/>{user.displayName}</span>
   {user.role==='ADMIN'&&<Button size="sm" variant="outline" className="h-9 gap-1.5 px-2" onClick={()=>setAdminOpen(true)}><ShieldCheck className="size-3.5"/><span className="hidden sm:inline">账户管理</span><span className="sm:hidden">管理</span></Button>}
   <Button variant="ghost" size="icon" className="size-9" aria-label="退出登录" onClick={()=>void logout().catch(e=>setError(e.message))}><LogOut className="size-4"/></Button>
  </div>:<Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={()=>{setError('');setOpen(true)}}><LogIn className="size-3.5"/>登录 / 注册</Button>}
  <Dialog open={open} onOpenChange={v=>{setOpen(v);if(!v)setPassword('')}}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>{mode==='login'?'登录研究工作台':'创建研究账户'}</DialogTitle><DialogDescription>研究记录、自选和组合分析按账户保存。新注册账号为普通用户；管理员由本地初始化配置。</DialogDescription></DialogHeader>
   <form className="space-y-4" onSubmit={e=>void submit(e)}>
    <div className="space-y-1.5"><label htmlFor="auth-username" className="text-sm font-medium">用户名</label><Input id="auth-username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_]+" placeholder="3—32位字母、数字或下划线"/></div>
    {mode==='register'&&<div className="space-y-1.5"><label htmlFor="auth-displayname" className="text-sm font-medium">显示名称</label><Input id="auth-displayname" value={displayName} onChange={e=>setDisplayName(e.target.value)} maxLength={40} placeholder="例如：研究员小猫"/></div>}
    <div className="space-y-1.5"><label htmlFor="auth-password" className="text-sm font-medium">密码</label><Input id="auth-password" type="password" autoComplete={mode==='login'?'current-password':'new-password'} value={password} onChange={e=>setPassword(e.target.value)} required minLength={8} maxLength={128} placeholder="至少8位，包含字母和数字"/></div>
    {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
    <Button className="w-full" type="submit" disabled={busy}>{busy?'正在处理…':mode==='login'?'登录':'注册并登录'}</Button>
    <Button type="button" variant="ghost" className="w-full" disabled={busy} onClick={()=>{setMode(mode==='login'?'register':'login');setError('');setPassword('')}}>{mode==='login'?'还没有账户？创建普通用户账户':'已有账户？返回登录'}</Button>
   </form>
  </DialogContent></Dialog>
  {user?.role==='ADMIN'&&<AdminDialog open={adminOpen} onClose={()=>setAdminOpen(false)}/>}
 </>
}
