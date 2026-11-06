'use client'

import { ArrowRight } from 'lucide-react'
import type { ResearchConclusion } from '@/lib/research/discussion'

/** Overview and final-decision tab must show the same persisted conclusion. */
export function ResearchDecision({ conclusion, compact = false, onOpen }: {
  conclusion: ResearchConclusion
  compact?: boolean
  onOpen?: () => void
}) {
  const score = conclusion.scoreSummary
  const hasScore = !!score && score.basis !== 'baseline' && score.confidence > 0
  const status = conclusion.status === 'unavailable'
    ? '暂不作方向判断'
    : conclusion.status === 'partial' ? '部分分析未完成 · 当前结论' : '基于当前资料的AI研究判断'
  return (
    <section className={`panel h-full space-y-5 ${compact ? 'p-5' : 'p-6'}`} aria-label={compact ? '投资决议摘要' : '投资决议'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className={`${compact ? 'text-lg' : 'text-xl'} font-semibold`}>投资决议</h3>
          <p className="mt-1 text-sm text-muted-foreground">{status}</p>
        </div>
        {onOpen && <button type="button" className="flex items-center gap-1 text-sm text-primary" onClick={onOpen}>
          查看完整决议 <ArrowRight className="size-3" aria-hidden />
        </button>}
      </div>
      {hasScore ? (
        <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-muted/20 p-4" data-testid="decision-score">
          <strong className="num text-4xl text-primary">{score.score}<span className="ml-1 text-sm text-muted-foreground">/100</span></strong>
          <div><p className="font-semibold">{score.label}</p><p className="mt-1 text-xs text-muted-foreground">判断置信度 {score.confidence}%</p></div>
        </div>
      ) : <p className="rounded-lg border border-border bg-muted/20 p-3 text-sm text-muted-foreground">当前可用分析不足以形成综合投资评分，基准值不作为投资评分。</p>}
      <p className="break-words leading-7" data-testid="decision-summary">{conclusion.summary}</p>
      {(!compact || conclusion.risks.length > 0) && (
        <div className="space-y-4">
          {([
            ['核心判断', compact ? [] : conclusion.points],
            ['关键风险', compact ? conclusion.risks.slice(0, 1) : conclusion.risks],
          ] as [string, string[]][]).filter(([, items]) => items.length > 0).map(([title, items]) => (
            <div key={title}><h4 className="mb-2 font-semibold">{title}</h4><ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
              {items.map((text, index) => <li className="break-words" key={index}>{text}</li>)}
            </ul></div>
          ))}
        </div>
      )}
      <p className="text-xs leading-5 text-muted-foreground">评分反映当前资料下的投资吸引力判断，不是上涨概率。正式买卖评级与仓位建议仍需充分的估值和风险资料。</p>
      {!compact && <details className="border-t border-border pt-4 text-xs leading-6 text-muted-foreground">
        <summary className="cursor-pointer text-sm">评分、来源与后续关注</summary>
        <p className="mt-2">{score?.method}</p>
        <ul className="mt-2 list-disc pl-4">{conclusion.missing.map((text, index) => <li key={index}>{text}</li>)}</ul>
        <p className="mt-2 break-all">来源：{conclusion.sourceIds.join('；') || '暂无'}</p>
        <p>自动检查与AI复核不等于人工确认。</p>
      </details>}
    </section>
  )
}
