'use client'

import { GATE_LABELS, safeSourceUrl, isUsableRecord, type ResearchAudit } from '@/lib/research-evidence/engine'
import { Button } from '@/components/ui/button'

export function EvidencePanel({ audit, historical = false }: { audit?: ResearchAudit; historical?: boolean }) {
  if (!audit) return historical ? (
    <section className="panel border-amber-500/30 p-4 text-sm" role="note">
      初赛历史记录：保留原始输出，尚未经过本轮证据核验。历史评分及来源文字不代表已经复核。
    </section>
  ) : null
  const gate=audit.decisionGate
  const exportAudit=()=>{
    const a=document.createElement('a');a.href=`/api/evidence-export?runId=${encodeURIComponent(audit.runId)}&format=json`;a.download=`${audit.runId}-evidence.json`;document.body.appendChild(a);a.click();a.remove()
  }
  return (
    <details className="panel space-y-4 p-4 sm:p-5" aria-label="证据与研究边界"><summary className="cursor-pointer text-sm font-medium">资料与复核记录 · {audit.records.length}条来源</summary>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">证据与研究边界</h2>
          <p className="mt-1 break-all text-xs text-muted-foreground">运行编号：{audit.runId}</p>
        </div>
        <Button variant="outline" size="sm" onClick={exportAudit}>导出证据记录</Button>
      </header>
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm" role="status">
        <p className="font-semibold">{gate ? GATE_LABELS[gate.status] : '正在核对资料'}</p>
        {gate && !gate.canPublishDecision && <p className="mt-1">本轮未生成最终投资评级、置信度或仓位建议。</p>}
        {gate && <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">{gate.reasons.map(r=><li key={r}>{r}</li>)}</ul>}
        {audit.modelEvaluation==='not_run' && <p className="mt-2">本次为登记资料核对，未调用大模型；不能作为多智能体效果评测。</p>}
      </div>
      <p className="text-xs leading-5 text-muted-foreground">原始来源已核对与模型主张已核对是不同状态。数值匹配只检查数值、单位、币种和报告期；论点语义仍需人工复核。年度资料不代表最新季报。</p>
      <details>
        <summary className="cursor-pointer text-sm font-medium">来源目录（{audit.records.length}条）</summary>
        <div className="mt-3 max-h-[30rem] space-y-3 overflow-auto">
          {audit.records.map((r,i)=>{
            const url=safeSourceUrl(r.sourceUrl)
            const usable=isUsableRecord(r,audit.capturedAt)
            return <article key={`${r.id}-${i}`} className="rounded-lg border border-border p-3 text-sm">
              <div className="flex flex-wrap justify-between gap-2"><strong>{r.label}</strong><span className="text-xs text-muted-foreground">{r.verification==='demo' ? '演示近似值' : usable ? '原始来源已核对' : '未核验或过期'}</span></div>
              <p className="mt-1 break-all text-xs text-muted-foreground">{r.id}</p>
              {r.value !== null && <p className="mt-2 font-mono">{r.value} {r.unit} {r.currency}</p>}
              <p className="mt-1">报告期：{r.period}</p>
              <p className="mt-1 text-muted-foreground">{r.source} · {r.locator}</p>
              <p className="mt-1 text-xs text-muted-foreground">发布时间：{r.publishedAt ?? '未核实'} · 采集：{r.capturedAt}</p>
              <p className="mt-2 break-words text-xs leading-5">{r.excerpt}</p>
              {r.reviewNote && <p className="mt-1 text-xs text-muted-foreground">{r.reviewNote}</p>}
              {url && <a className="mt-2 inline-block text-primary underline underline-offset-4" href={r.page ? `${url}#page=${r.page}` : url} target="_blank" rel="noopener noreferrer">查看原始来源</a>}
            </article>
          })}
          {!audit.records.length && <p className="text-sm text-muted-foreground">当前标的尚无登记资料。</p>}
        </div>
      </details>
      {!!audit.claims.length && <details>
        <summary className="cursor-pointer text-sm font-medium">模型引用检查（{audit.claims.length}条）</summary>
        <ul className="mt-2 space-y-2 text-xs">{audit.claims.map((c,i)=><li key={i} className="rounded border border-border p-2">
          <p>{c.agentKey} · {c.evidenceId ?? '缺少编号'} · {c.verification==='matched' ? '数值口径匹配' : c.verification==='rejected' ? '核验失败' : '未核验'}</p>
          <p className="mt-1">待复核主张：{c.claim}</p><p className="mt-1 text-muted-foreground">{c.verificationNote}</p>
        </li>)}</ul>
      </details>}
      {!!audit.stageDurationsMs.total && <p className="text-xs text-muted-foreground">本次流程实测耗时：{(audit.stageDurationsMs.total/1000).toFixed(2)}秒。证据记录内各环节耗时包含其排队和重试；并行环节不可相加作为总耗时。</p>}
    </details>
  )
}
