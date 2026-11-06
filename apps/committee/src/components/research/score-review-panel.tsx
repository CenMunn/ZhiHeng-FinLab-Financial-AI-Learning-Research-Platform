'use client'
import {useEffect,useId,useState} from 'react'
import type {AgentDTO} from '@/lib/types'
import type {ScoreReviewState} from '@/lib/research/score-review'
import {Button} from '@/components/ui/button'
export function ScoreReviewPanel({agent,revision,onUpdated}:{agent:AgentDTO;revision:number;onUpdated:()=>void|Promise<unknown>}){
 const state=agent.details?.scoreReview as ScoreReviewState|undefined,id=useId()
 const [text,setText]=useState(''),[source,setSource]=useState(''),[locator,setLocator]=useState(''),[period,setPeriod]=useState(''),[checked,setChecked]=useState(false)
 const [score,setScore]=useState(String(agent.score??50)),[confidence,setConfidence]=useState(String(agent.confidence||40)),[reason,setReason]=useState('')
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('')
 const historyCount=state?.history.length??0
 useEffect(()=>{setScore(String(agent.score??50));setConfidence(String(agent.confidence||40))},[agent.score,agent.confidence,historyCount])
 const inputClass='mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50'
 async function submit(action:'ai_rescore'|'accept_ai'|'manual_adjust'){
  setError('');setMessage('')
  if(action!=='ai_rescore'&&!reason.trim()){setError('请先填写你的复核或调整理由。');return}
  if(action==='manual_adjust'&&(!/^\d{1,3}$/.test(score)||!/^\d{1,3}$/.test(confidence))){setError('分数和置信度请填写0至100的整数。');return}
  const hasSupplement=!![text,source,locator,period].some(s=>s.trim())
  if(hasSupplement&&(!text.trim()||!source.trim()||!locator.trim())){setError('补充资料需要填写摘录、来源和页码或定位。');return}
  setBusy(action)
  try{
   const r=await fetch(`/api/research/${agent.sessionId}/score-review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,agentId:agent.id,expectedRevision:revision,reason,score:Number(score),confidence:Number(confidence),proposalId:state?.proposal?.id,...(hasSupplement?{supplement:{text,source,locator,period,checked}}:{})})})
   const data=await r.json().catch(()=>null)
   if(!r.ok){if(r.status===409)await onUpdated();throw Error(data?.error??'保存未完成，请重试')}
   await onUpdated()
   setText('');setSource('');setLocator('');setPeriod('');setChecked(false)
   setMessage(action==='ai_rescore'?'AI候选已保存。请核对理由，确认后才会更新综合分。':'已保存，综合分与报告已同步更新。')
  }catch(e){setError(e instanceof Error?e.message:'保存未完成，请重试')}finally{setBusy('')}
 }
 return <details className="mt-4 border-t border-border pt-3" aria-label={`${agent.agentName}评分复核`}>
  <summary className="cursor-pointer text-sm font-medium text-primary">补充资料与人工复核</summary>
  <div className="mt-4 space-y-4 text-sm" aria-busy={!!busy}>
   <p className="text-xs leading-6 text-muted-foreground">可用已有资料重新估分，也可补充原文。AI复评分先保存为候选；人工确认或直接调整后更新综合分和报告。原始回答与核验记录保留。</p>
   <fieldset disabled={!!busy} className="space-y-3">
    <legend className="mb-2 font-medium">补充资料 <span className="font-normal text-muted-foreground">可选</span></legend>
    <div><label className="block" htmlFor={id+'-text'}>原文摘录</label><textarea id={id+'-text'} rows={3} maxLength={4000} className={inputClass} value={text} onChange={e=>setText(e.target.value)} placeholder="粘贴与此角色判断有关的原文"/></div>
    <label className="block" htmlFor={id+'-source'}>来源链接或文件名称<input id={id+'-source'} maxLength={500} className={inputClass} value={source} onChange={e=>setSource(e.target.value)}/></label>
    <div className="grid gap-3 sm:grid-cols-2"><label htmlFor={id+'-locator'}>页码或定位<input id={id+'-locator'} maxLength={200} className={inputClass} value={locator} onChange={e=>setLocator(e.target.value)} placeholder="如第8页第二段"/></label><label htmlFor={id+'-period'}>资料期间<input id={id+'-period'} maxLength={80} className={inputClass} value={period} onChange={e=>setPeriod(e.target.value)} placeholder="如2025年度"/></label></div>
    <label className="flex items-start gap-2 text-xs leading-5"><input className="mt-1" type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/>我已核对这段摘录与原文一致</label>
    <Button type="button" variant="outline" disabled={!!busy} onClick={()=>void submit('ai_rescore')}>{busy==='ai_rescore'?'AI正在复评分…':'根据现有及补充资料重新评分'}</Button>
   </fieldset>
   {state?.proposal&&<section className="space-y-2 rounded-md border border-primary/30 p-3" aria-label="待确认AI评分">
    <p className="font-medium">待确认AI候选：{state.proposal.score}/100 <span className="text-xs font-normal text-muted-foreground">置信度{state.proposal.confidence}%</span></p>
    <p className="text-sm leading-6">{state.proposal.reason}</p><p className="text-xs text-muted-foreground">当前生效分仍为{agent.score??'未评分'}。填写下方理由后，可确认采用。</p>
   </section>}
   <fieldset disabled={!!busy} className="space-y-3 border-t border-border pt-3">
    <legend className="mb-2 font-medium">人工复核</legend>
    <div><label className="block" htmlFor={id+'-reason'}>复核或调整理由</label><textarea id={id+'-reason'} rows={2} maxLength={1000} className={inputClass} value={reason} onChange={e=>setReason(e.target.value)} placeholder="说明认可的依据，或调整分数的理由"/></div>
    {state?.proposal&&<Button type="button" disabled={!!busy} onClick={()=>void submit('accept_ai')}>{busy==='accept_ai'?'保存中…':'确认采用AI候选评分'}</Button>}
    <div className="grid grid-cols-2 gap-3"><label htmlFor={id+'-score'}>人工调整分数<input id={id+'-score'} type="number" min={0} max={100} step={1} className={inputClass} value={score} onChange={e=>setScore(e.target.value)}/></label><label htmlFor={id+'-confidence'}>判断置信度<input id={id+'-confidence'} type="number" min={0} max={100} step={1} className={inputClass} value={confidence} onChange={e=>setConfidence(e.target.value)}/></label></div>
    <Button type="button" variant="outline" disabled={!!busy} onClick={()=>void submit('manual_adjust')}>{busy==='manual_adjust'?'保存中…':'保存人工调整'}</Button>
    <p className="text-xs leading-5 text-muted-foreground">人工调整会单独标注，不改变原始财报及引用的核验状态。操作人取自当前登录账号。</p>
   </fieldset>
   {error&&<p role="alert" className="text-sm text-red-500">{error}</p>}{message&&<p role="status" className="text-sm text-primary">{message}</p>}
   {state&&<details><summary className="cursor-pointer text-xs text-muted-foreground">原始评分与复核历史（{historyCount}次）</summary><div className="mt-2 max-h-72 space-y-3 overflow-auto text-xs leading-6"><p>原始分数：{state.original.score??'未评分'}；{state.original.reason}</p>{state.history.map(h=><div key={h.id} className="border-t border-border pt-2"><p>{new Date(h.at).toLocaleString('zh-CN')} · {h.actor.displayName||h.actor.username} · {h.action==='manual_adjust'?'人工调整':h.action==='accept_ai'?'确认AI候选':'AI复评分候选'}</p><p>{h.before.score??'未评分'} → {h.after.score??'未评分'}；{h.reason}</p></div>)}{state.supplements.map(s=><div key={s.id} className="border-t border-border pt-2"><p>{s.source} · {s.locator} · {s.period}</p><p className="whitespace-pre-wrap">{s.text}</p><p>{s.checkedBy?'提交人已核对原文':'用户补充，尚未核对'}</p></div>)}</div></details>}
  </div>
 </details>
}
