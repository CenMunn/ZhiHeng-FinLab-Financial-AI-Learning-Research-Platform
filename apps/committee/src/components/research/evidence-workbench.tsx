'use client'

import { Header } from '@/components/home/header'
import { useAuth } from '@/components/auth/auth-provider'
import { useState } from 'react'
import { CORE_RESEARCH_CASES } from '@/lib/data/core-research-cases'
import type { ResearchAudit } from '@/lib/research-evidence/engine'
import { EvidencePanel } from './evidence-panel'
import { ReportTab } from './report-tab'
import { Button } from '@/components/ui/button'
import { FinancialComparisonPanel } from './financial-comparison-panel'

export function EvidenceWorkbench() {
  const {user}=useAuth()
  return <EvidenceWorkbenchContent key={user?.id??'guest'}/>
}
function EvidenceWorkbenchContent() {
  const {user,setOpen:openAuth}=useAuth()
  const [code,setCode]=useState<string>('600519')
  const [audit,setAudit]=useState<ResearchAudit | undefined>()
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const selected=CORE_RESEARCH_CASES.find(c=>c.code===code)!
  const run=async(mode: 'single' | 'comparison'='single')=>{
    if(!user){openAuth(true);return}
    setBusy(true);setError('');setAudit(undefined)
    try {
      const res=await fetch(mode==='comparison'?'/api/evidence-comparison':'/api/evidence-check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(mode==='comparison'?{caseId:'D02'}:{stockCode:code})})
      const data=await res.json()
      if (!res.ok) throw new Error(data.error ?? '资料核对失败')
      setAudit(data.audit)
    } catch(e) {setError(e instanceof Error ? e.message : '资料核对失败')} finally {setBusy(false)}
  }
  return <><Header view="home"/><main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
    <a href="/" className="text-sm text-primary underline underline-offset-4">返回智投委 AI</a>
    <a href="/filings" className="ml-4 text-sm text-primary underline underline-offset-4">上传其他公司财务页 PDF</a>
    <header><p className="text-sm text-muted-foreground">智投委 AI · 投研资料核验助手</p><h1 className="mt-2 text-3xl font-semibold">财报核验与同行比较</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">面向需要核对财报的研究人员与金融学习者。选择公司或生成同行对比，查看金额、计算口径与原文，再导出带证据的报告。本入口核对已登记资料，不调用大模型。</p></header>
    <section className="panel space-y-4 p-5">
      <label className="block text-sm font-medium" htmlFor="core-stock">选择研究公司</label>
      <select id="core-stock" className="w-full rounded-md border border-border bg-background p-3 text-sm" value={code} disabled={busy} onChange={e=>{setCode(e.target.value);setAudit(undefined);setError('')}}>
        {CORE_RESEARCH_CASES.map(c=><option value={c.code} key={c.code}>{c.name} · {c.code} · {['600519','000858'].includes(c.code)?'年报资料已登记':'原始资料待补充'}</option>)}
      </select>
      <p className="text-sm leading-6"><span className="font-semibold">演示问题：</span>{selected.query}</p>
      <p className="text-xs leading-5 text-muted-foreground">已登记贵州茅台、五粮液2025年年报各3项金额，附原文、页码和文件哈希；其余8只样本尚待补充原始资料。</p>
      <Button disabled={busy} onClick={()=>void run()}>{busy?'正在核对并保存…':'核对已登记资料'}</Button>
      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
    </section>
    <section className="panel space-y-3 p-5">
      <p className="text-xs font-medium text-primary">固定演示案例 D02</p>
      <h2 className="text-lg font-semibold">茅台—五粮液：2025年度财务对比</h2>
      <p className="text-sm leading-6 text-muted-foreground">核对双方营收、归母净利润与经营现金流，计算辅助比率，同时说明收入确认核算与财务子公司对解读的影响。</p>
      <Button disabled={busy} variant="outline" onClick={()=>void run('comparison')}>{busy?'正在核对并保存…':'生成茅台—五粮液对比'}</Button>
    </section>
    {audit && <>
      {audit.financialComparison && <FinancialComparisonPanel comparison={audit.financialComparison}/>}
      <EvidencePanel audit={audit}/><ReportTab reportMd={audit.reportMd ?? null} stockName={audit.financialComparison?'贵州茅台—五粮液':selected.name} generatedAt={audit.decisionGate?.checkedAt} downloadUrl={`/api/evidence-export?runId=${audit.runId}&format=md`} audited/>
    </>}
  </main></>
}
