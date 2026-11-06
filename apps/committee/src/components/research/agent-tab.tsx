'use client'

// Agent 洞察 Tab — AI INVESTMENT COMMITTEE · 全 9 席位
// 6 分析席（5 分析师 + 风控官全宽特色卡）+ 3 博弈仲裁席（Bull / Bear / 冲突调解员，由辩论记录驱动）
// 分析中：终端式等待态（micro-label + typing-dot + shimmer 扫描线 + 流式占位）；完成：径向仪表 + 证据链

import { motion } from 'framer-motion'
import { ShieldAlert } from 'lucide-react'
import type { AgentDTO, DebateDTO } from '@/lib/types'
import { AGENT_META, voteTone } from '@/lib/client-utils'
import {
  GeoBadge,
  ModelChip,
  RadialGauge,
  TerminalWait,
  confidenceDot,
} from '@/components/research/bits'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {ScoreReviewPanel} from '@/components/research/score-review-panel'

// 模型约定：分析师 = 角色模型；风控官 = 角色模型
function deskModel(agentKey: string): { model: string; tone: 'primary' | 'gold' } {
  return agentKey === 'risk' ? { model: '风控模型', tone: 'gold' } : { model: '分析模型', tone: 'primary' }
}

const PHASE_SHORT: Record<DebateDTO['phase'], string> = {
  opening: '立论',
  rebuttal: '反驳',
  crossexam: '质证',
  closing: '结辩',
  conflict: '仲裁',
  risk: '风控',
}

function EvidenceRow({
  claim,
  value,
  source,
  confidence,
}: {
  claim: string
  value?: string
  source?: string
  confidence?: 'High' | 'Medium' | 'Low'
}) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border/50 bg-muted/25 px-2.5 py-1.5">
      <span className={cn('mt-[6px] size-1.5 shrink-0 rounded-full', confidenceDot(confidence))} aria-hidden />
      <p className="min-w-0 flex-1 truncate text-xs leading-5" title={claim}>
        {claim}
      </p>
      {value && <span className="num shrink-0 text-[11px] font-semibold text-foreground/85">{value}</span>}
      {source && <span className="num hidden shrink-0 max-w-32 truncate text-[10px] text-muted-foreground/70 sm:block">{source}</span>}
    </div>
  )
}

/** 分析席终端式等待态（替代普通骨架屏） */
function AgentSkeletonCard({ label, seatNo, active=true }: { label: string; seatNo: number; active?: boolean }) {
  const meta = AGENT_META[label]
  const Icon = meta?.icon
  const engine = deskModel(label)
  if (!active) return <div className="panel p-5"><h3 className="font-bold">{meta?.label ?? 'Agent'}</h3><p className="mt-3 text-sm text-muted-foreground">本轮未执行或未形成结果。流程已结束。</p></div>
  return (
    <div className="panel flex h-full flex-col gap-4 p-5" aria-label={`${meta?.label ?? 'Agent'} 分析中`}>
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/40">
          {Icon ? <Icon className="size-5 text-muted-foreground/70" aria-hidden /> : null}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-bold leading-tight text-foreground/85">{meta?.label ?? 'AGENT'}</p>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="num text-[9px] tracking-widest text-muted-foreground/60">SEAT {String(seatNo).padStart(2, '0')}</span>
            <ModelChip model={engine.model} tone={engine.tone} />
          </div>
        </div>
      </div>

      <TerminalWait label={`${(meta?.label ?? 'AGENT').toUpperCase()} · WORKING`} model={engine.model} tone={engine.tone} />

      {/* 流式占位：模拟逐步到达的段落 */}
      <div className="space-y-2" aria-hidden>
        <div className="shimmer h-2 w-full rounded bg-muted/70" />
        <div className="shimmer h-2 w-5/6 rounded bg-muted/70" />
        <div className="shimmer h-2 w-2/3 rounded bg-muted/70" />
      </div>

      <p className="num mt-auto flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
        STREAMING PARTIAL RESULTS
        <span className="caret-blink inline-block h-3 w-[7px] bg-primary/70" aria-hidden />
      </p>
    </div>
  )
}

function AgentCard({ agent, index, featured,canReview,revision,onUpdated }: { agent: AgentDTO; index: number; featured?: boolean;canReview?:boolean;revision:number;onUpdated:()=>void|Promise<unknown> }) {
  const executionStatus = agent.details?.executionStatus
  const technical = agent.details?.scoreKind === 'technical_momentum'
  const scoreBasis=agent.details?.scoreBasis
  const repaired=(agent.details?.semanticReview as {status?:string}|undefined)?.status==='model_repaired'
  const reviewed=(agent.details?.semanticReview as {status?:string}|undefined)?.status==='model_reviewed'
  const statusLabel = executionStatus === 'failed' ? '执行失败' : executionStatus === 'review_required' ? '解释待确认' : technical ? '技术指标已计算' : repaired ? 'AI已修正' : reviewed ? 'AI已复核' : executionStatus === 'limited' ? '已分析' : '已完成'
  const isRisk = agent.agentKey === 'risk'
  const meta = AGENT_META[agent.agentKey] ?? {
    label: agent.agentName,
    icon: ShieldAlert,
    accent: 'bg-primary/10 text-primary',
  }
  const Icon = meta.icon
  const engine = deskModel(agent.agentKey)
  if(technical)engine.model='代码计算 · 登记日线'
  const calls = Array.isArray(agent.details?.llmCalls) ? agent.details.llmCalls as {responseModel?:string;requestedModel?:string;status?:string}[] : []
  const lastCall = [...calls].reverse().find(c=>c.status==='ok') ?? calls.at(-1)
  if(lastCall) engine.model=lastCall.responseModel && lastCall.responseModel!=='unknown' ? lastCall.responseModel : `${lastCall.requestedModel}（请求）`
  const vTone = agent.vote ? voteTone(agent.vote) : null
  const riskPenalty = isRisk && agent.details && typeof agent.details.riskPenalty === 'number' ? agent.details.riskPenalty : null

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3) }}
      className={cn(featured && 'md:col-span-2 xl:col-span-3')}
    >
      <section
        className={cn(
          'panel flex h-full flex-col p-5 transition-[transform,border-color] duration-150 hover:-translate-y-0.5 hover:border-foreground/25',
          isRisk && 'border-risk/30 bg-risk/[0.03]',
        )}
        aria-label={meta.label}
      >
        {/* 头部：席位号 + 角色 + 模型 + 投票角标 */}
        <header className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg border border-border/60', meta.accent)}>
              <Icon className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <h3 className="flex items-center gap-2 text-[15px] font-bold leading-tight">
                {meta.label}
                {isRisk && <ShieldAlert className="size-3.5 shrink-0 text-risk" aria-label="风控官拥有否决权" />}
              </h3>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <span className="num text-[9px] tracking-widest text-muted-foreground/60">
                  SEAT {String(index + 1).padStart(2, '0')}
                </span>
                <ModelChip model={engine.model} tone={engine.tone} />
                {vTone && (
                  <Badge variant="outline" className={cn('px-1.5 py-0 text-[10px] font-bold', vTone.badge)}>
                    {agent.vote}
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span className="flex items-center gap-1.5" aria-label={statusLabel}>
              <span className={cn('size-1.5 rounded-full', executionStatus === 'failed' || executionStatus === 'limited' || executionStatus === 'review_required' ? 'bg-amber-500' : 'bg-bull')} aria-hidden />
              <span className="micro-label text-[9px]">{statusLabel}</span>
            </span>
            {agent.durationMs != null && (
              <span className="num text-[9px] text-muted-foreground/60">{(agent.durationMs / 1000).toFixed(1)}S</span>
            )}
          </div>
        </header>

        {/* 评分块：径向仪表 + 置信度 */}
        <div className="mt-4 flex items-center gap-5">
          {agent.score == null ? <div className="flex size-24 shrink-0 flex-col items-center justify-center rounded-full border border-dashed border-border text-muted-foreground"><span className="text-sm">未评分</span><span className="mt-1 text-[10px]">见资料边界</span></div> : <RadialGauge
            value={agent.score}
            size={104}
            stroke={8}
            label={technical ? '技术动量' : '/ 100'}
            valueClassName={agent.score == null ? 'text-2xl text-muted-foreground/40' : 'text-2xl'}
          />}
          <div className="min-w-0 flex-1 space-y-2.5">
            {agent.confidence != null && (
              <div>
                <div className="mb-1 flex items-baseline justify-between">
                  <span className="micro-label">判断置信度</span>
                  <span className="num text-xs font-bold">{agent.confidence}%</span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn('h-full rounded-full', agent.confidence >= 70 ? 'bg-bull' : agent.confidence >= 45 ? 'bg-hold' : 'bg-bear')}
                    style={{ width: `${Math.min(100, Math.max(0, agent.confidence))}%` }}
                  />
                </div>
              </div>
            )}
            {riskPenalty != null && riskPenalty > 0 && (
              <span className="num inline-flex items-center gap-1 rounded border border-bear/30 bg-bear/10 px-1.5 py-0.5 text-[10px] font-bold text-bear">
                RISK PENALTY −{riskPenalty}
              </span>
            )}
            {typeof scoreBasis==='string'&&<p className="text-xs font-medium text-foreground/80">{scoreBasis==='human_adjusted'?'人工调整分':scoreBasis==='baseline'?'信息不足 · 基准值':scoreBasis==='ai_estimate'?'AI条件性评分':technical?'技术动量分':'基于资料评分'}</p>}
            {agent.summary && <p className="text-[13px] leading-5 text-muted-foreground">{agent.summary}</p>}
            {typeof agent.details?.scoreReason==='string' && <details className="text-xs leading-5 text-muted-foreground"><summary className="cursor-pointer">评分说明</summary><p className="mt-1">{agent.details.scoreReason}</p>{repaired&&<p>模型已根据原始资料修正解释，并再次通过程序检查。</p>}{reviewed&&<p>AI已复核本段中的否定或风险提醒，原句和复核记录可在下方查看。</p>}</details>}
          </div>
        </div>

        {/* 多空要点 */}
        {((agent.highlights?.length ?? 0) > 0 || (agent.concerns?.length ?? 0) > 0) && (
          <div className="mt-4 grid gap-x-5 gap-y-1.5 border-t border-border/50 pt-3 sm:grid-cols-2">
            {agent.highlights && agent.highlights.length > 0 && (
              <ul className="space-y-1.5">
                {agent.highlights.slice(0, 2).map((h, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-5">
                    <span className="shrink-0 font-bold text-bull" aria-hidden>
                      +
                    </span>
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
            )}
            {agent.concerns && agent.concerns.length > 0 && (
              <ul className="space-y-1.5">
                {agent.concerns.slice(0, 1).map((c, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-5">
                    <span className="shrink-0 font-bold text-bear" aria-hidden>
                      −
                    </span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* 证据链脚注 */}
        {agent.evidence && agent.evidence.length > 0 && (
          <details className="mt-3 border-t border-border/50 pt-3"><summary className="cursor-pointer text-xs text-muted-foreground">来源与复核记录</summary>
            <div className="nice-scroll max-h-24 space-y-1.5 overflow-y-auto pr-1">
              {agent.evidence.slice(0, 3).map((e, i) => (
                <div key={i}>
                <EvidenceRow
                  claim={e.claim}
                  value={e.value}
                  source={e.source}
                  confidence={e.confidence}
                />
                <p className="mt-1 text-[10px] text-muted-foreground">{e.evidenceId ?? '无登记编号'} · {e.verification==='matched' ? '原值与口径已匹配' : e.verification==='rejected' ? '引用核验失败' : '未核验'}</p>
                </div>
              ))}
            </div>
          </details>
        )}
        {!!agent.details?.semanticReview&&<details className="mt-3 text-xs text-muted-foreground"><summary className="cursor-pointer">查看AI复核过程</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(agent.details.semanticReview,null,2)}</pre></details>}
        {canReview&&<ScoreReviewPanel agent={agent} revision={revision} onUpdated={onUpdated}/>}
      </section>
    </motion.div>
  )
}

/** 博弈仲裁席：Bull / Bear / 冲突调解员（由辩论记录驱动，勿臆造字段） */
function GameSeat({
  kind,
  title,
  msgs,
  analyzing,
  index,
}: {
  kind: 'bull' | 'bear' | 'conflict'
  title: string
  msgs: DebateDTO[]
  analyzing: boolean
  index: number
}) {
  const last = msgs.length > 0 ? msgs[msgs.length - 1] : null
  const waiting = msgs.length === 0
  const seatTone = kind === 'bull' ? 'text-bull' : kind === 'bear' ? 'text-bear' : 'text-gold'
  const seatBorder =
    kind === 'bull' ? 'border-bull/25' : kind === 'bear' ? 'border-bear/25' : 'border-gold/25'

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.15 + index * 0.05 }}
      className={cn('panel flex h-full flex-col p-4', waiting ? '' : seatBorder)}
      aria-label={title}
    >
      <header className="flex items-center gap-2.5">
        <GeoBadge kind={kind} className="size-9" />
        <div className="min-w-0 flex-1">
          <h3 className={cn('truncate text-[13px] font-bold leading-tight', !waiting && seatTone)}>{title}</h3>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="num text-[9px] tracking-widest text-muted-foreground/60">
              SEAT {String(index + 7).padStart(2, '0')}
            </span>
            <ModelChip model="角色模型（见调用记录）" tone="gold" />
          </div>
        </div>
        <span
          className={cn(
            'num shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold',
            waiting
              ? 'border-border/70 bg-muted/50 text-muted-foreground'
              : kind === 'bull'
                ? 'border-bull/30 bg-bull/10 text-bull'
                : kind === 'bear'
                  ? 'border-bear/30 bg-bear/10 text-bear'
                  : 'border-gold/30 bg-gold/10 text-gold',
          )}
        >
          {waiting ? '待上场' : `${msgs.length} 次发言`}
        </span>
      </header>

      <div className="mt-3 min-w-0 flex-1">
        {waiting ? (
          <TerminalWait
            label={analyzing ? 'AWAITING SESSION · 等待上场' : 'NOT SEATED · 本场未发言'}
            model="角色模型（见调用记录）"
            tone="gold"
          />
        ) : (
          <div className="space-y-2">
            <p className="line-clamp-3 text-xs leading-5 text-muted-foreground" title={last?.content}>
              {last?.content}
            </p>
            <p className="num text-[10px] text-muted-foreground/60">
              ROUND {String(last?.round ?? 0).padStart(2, '0')} · {last ? PHASE_SHORT[last.phase] : ''}
            </p>
          </div>
        )}
      </div>
    </motion.section>
  )
}

interface AgentTabProps {
  agents: AgentDTO[]
  debates: DebateDTO[]
  analyzing: boolean
  canReview?:boolean
  revision?:number
  onUpdated?:()=>void|Promise<unknown>
}

const ANALYST_KEYS = ['fundamental', 'industry', 'macro', 'quant', 'sentiment'] as const

export function AgentTab({ agents, debates, analyzing,canReview=false,revision=0,onUpdated=()=>{} }: AgentTabProps) {
  const analysts = ANALYST_KEYS.map((key) => agents.find((a) => a.agentKey === key) ?? null)
  const risk = agents.find((a) => a.agentKey === 'risk') ?? null
  const loadedCount = analysts.filter(Boolean).length + (risk ? 1 : 0)

  // 博弈席消息（按 speakerKey 聚合，来自 DebateDTO 真实数据）
  const bullMsgs = debates.filter((d) => d.speakerKey === 'bull')
  const bearMsgs = debates.filter((d) => d.speakerKey === 'bear')
  const conflictMsgs = debates.filter((d) => d.speakerKey === 'conflict')
  const gameSeats: { kind: 'bull' | 'bear' | 'conflict'; title: string; msgs: DebateDTO[] }[] = [
    { kind: 'bull', title: '多方辩护人', msgs: bullMsgs },
    { kind: 'bear', title: '空方辩护人', msgs: bearMsgs },
    { kind: 'conflict', title: '冲突调解员', msgs: conflictMsgs },
  ]
  const gameSeated = gameSeats.filter((s) => s.msgs.length > 0).length

  return (
    <div className="space-y-4">
      {/* 终端微标头 */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="micro-label text-foreground/80">AI Investment Committee — Analyst Desks</h2>
        <span className="num text-[10px] text-muted-foreground">
          SEATS 09 · DESKS {String(loadedCount).padStart(2, '0')}/06 · GAME {String(gameSeated).padStart(2, '0')}/03{' '}
          {analyzing ? '· STREAMING' : '· SETTLED'}
        </span>
      </div>

      {/* 6 分析席 */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {analysts.map((agent, i) =>
          agent ? (
            <AgentCard key={agent.id} agent={agent} index={i} canReview={canReview} revision={revision} onUpdated={onUpdated}/>
          ) : (
            <AgentSkeletonCard key={`${ANALYST_KEYS[i]}-skeleton`} label={ANALYST_KEYS[i]} seatNo={i + 1} active={analyzing} />
          ),
        )}

        {/* 风控官：全宽特色卡 */}
        {risk ? (
          <AgentCard agent={risk} index={analysts.length} featured canReview={canReview} revision={revision} onUpdated={onUpdated}/>
        ) : (
          <div className="md:col-span-2 xl:col-span-3">
            <AgentSkeletonCard label="risk" seatNo={6} active={analyzing} />
          </div>
        )}
      </div>

      {/* 博弈仲裁席分隔 */}
      <div className="flex items-center gap-3" aria-hidden>
        <span className="micro-label shrink-0">Game & Arbitration · 博弈仲裁席</span>
        <span className="h-px flex-1 bg-border/60" />
        <span className="num shrink-0 text-[10px] text-muted-foreground/60">ROLE ANALYSIS</span>
      </div>

      {/* 3 博弈席 */}
      <div className="grid gap-4 sm:grid-cols-3">
        {gameSeats.map((s, i) => (
          <GameSeat key={s.kind} kind={s.kind} title={s.title} msgs={s.msgs} analyzing={analyzing} index={i} />
        ))}
      </div>

      {agents.length === 0 && analyzing && (
        <p className="num flex items-center justify-center gap-2 py-2 text-xs text-muted-foreground">
          <span className="led text-primary" aria-hidden />
          AGENT 团队正在组建，分析即将开始…
        </p>
      )}
    </div>
  )
}
