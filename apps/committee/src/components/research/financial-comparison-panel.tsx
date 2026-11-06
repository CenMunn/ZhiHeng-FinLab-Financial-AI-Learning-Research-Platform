'use client'

import type { FinancialComparison } from '@/lib/research-evidence/engine'

export function FinancialComparisonPanel({ comparison }: {comparison: FinancialComparison}) {
  const status=comparison.status==='comparable'?'同口径基础数据齐备':comparison.status==='review_required'?'来源需要复核':'资料不足'
  return <section className="panel space-y-5 p-4 sm:p-5" aria-label="茅台与五粮液财务对比">
    <header>
      <p className="text-xs font-medium text-primary">D02 · 2025年度 · CNY</p>
      <h2 className="mt-2 text-xl font-semibold">茅台—五粮液：财务证据对比</h2>
      <p className="mt-2 text-sm text-muted-foreground">{status}。以下比率由原始金额计算；解读需结合附注。</p>
    </header>
    {!!comparison.reasons.length && <ul className="list-disc space-y-1 pl-5 text-sm text-amber-600">{comparison.reasons.map(r=><li key={r}>{r}</li>)}</ul>}
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">双方2025年度金额和辅助财务比率</caption>
        <thead className="bg-muted/40"><tr><th className="p-3">指标 / 展示单位</th><th className="p-3">贵州茅台</th><th className="p-3">五粮液</th></tr></thead>
        <tbody>{comparison.rows.map(r=><tr className="border-t border-border" key={r.metric}>
          <th scope="row" className="p-3 font-medium">{r.label}<span className="mt-1 block text-xs font-normal text-muted-foreground">{r.derived?r.unit:'亿元（元 ÷ 100,000,000）'}</span></th>
          {r.values.map(v=><td key={v.stockCode} className="p-3 align-top">
            <span className="font-mono font-semibold">{v.value===null?'待补 / 不适用':(r.derived?v.value:v.value/1e8).toLocaleString('zh-CN',{minimumFractionDigits:r.unit==='倍'?3:2,maximumFractionDigits:r.unit==='倍'?3:2})}</span>
            {!r.derived && v.value!==null && <span className="mt-1 block whitespace-nowrap font-mono text-[11px] text-muted-foreground">原值 {v.value.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})} 元</span>}
            {v.note && <span className="mt-1 block max-w-56 text-xs text-muted-foreground">{v.note}</span>}
          </td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <details className="rounded-lg border border-border p-3">
      <summary className="cursor-pointer text-sm font-medium">查看计算公式与输入证据编号</summary>
      <div className="mt-3 space-y-3">{comparison.rows.filter(r=>r.derived).map(r=><div key={r.metric} className="text-xs leading-5">
        <p className="font-medium">{r.formula}</p>
        {r.values.map(v=><p key={v.stockCode} className="break-all text-muted-foreground">{v.stockName}：{v.evidenceIds.join(' + ') || '未取得输入'}</p>)}
      </div>)}</div>
    </details>
    {!!comparison.observations.length && <div className="space-y-2 text-sm leading-6">{comparison.observations.map(o=><p key={o}>{o}</p>)}</div>}
    <div className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
      <h3 className="font-medium">影响解读的年报说明</h3>
      {comparison.contexts.map(c=><div key={c.id} className="text-sm leading-6">
        <p>{c.summary}</p>
        <a href={`${c.sourceUrl}#page=${c.page}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary underline underline-offset-4">{c.source} · {c.locator}</a>
      </div>)}
    </div>
    <details><summary className="cursor-pointer text-sm font-medium">适用范围与复核清单</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-xs leading-5 text-muted-foreground">{comparison.limitations.map(l=><li key={l}>{l}</li>)}</ul></details>
  </section>
}
