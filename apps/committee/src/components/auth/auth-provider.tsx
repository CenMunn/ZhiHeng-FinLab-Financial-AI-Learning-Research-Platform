'use client'
import {createContext,useContext,useCallback,useEffect,useState,type ReactNode} from 'react'
export type AccountUser={id:string;username:string;displayName:string;role:string}
type AuthContextValue={user:AccountUser|null;loading:boolean;open:boolean;setOpen:(open:boolean)=>void;revision:number;refresh:()=>Promise<void>;logout:()=>Promise<void>}
const Context=createContext<AuthContextValue|null>(null)
export function AuthProvider({children}:{children:ReactNode}) {
 const [user,setUser]=useState<AccountUser|null>(null),[loading,setLoading]=useState(true),[open,setOpen]=useState(false),[revision,setRevision]=useState(0)
 const refresh=useCallback(async()=>{
  try {const res=await fetch('/api/auth/me',{cache:'no-store'});if(!res.ok)throw Error('账户状态获取失败');setUser((await res.json()).user)}
  catch {setUser(null)} finally {setLoading(false);setRevision(v=>v+1)}
 },[])
 useEffect(()=>{void refresh()},[refresh])
 const logout=useCallback(async()=>{
  const res=await fetch('/api/auth/logout',{method:'POST'})
  if(!res.ok)throw Error('退出失败，请重试')
  setUser(null);setRevision(v=>v+1)
 },[])
 return <Context.Provider value={{user,loading,open,setOpen,revision,refresh,logout}}>{children}</Context.Provider>
}
export function useAuth(){const state=useContext(Context);if(!state)throw Error('AuthProvider required');return state}
