'use client'

// 顶部全球指数带：LIVE 状态块 + 24 指数跑马灯（CN → HK → US 分组，微妙分隔）+ 价格闪烁
// 数据来自 HomeView 唯一 useIndices 实例（与监控墙 / Hero 共享，10s 轮询）

import { useMemo } from 'react'
import type { IndexRow } from '@/hooks/use-indices'
import { formatPct } from '@/lib/client-utils'
import { cn } from '@/lib/utils'
import { usePriceFlash, type IndicesState } from '@/components/home/market-monitor'

const GROUP_ORDER: { key: 'cn' | 'hk' | 'us'; tag: string }[] = [
  { key: 'cn', tag: 'CN' },
  { key: 'hk', tag: 'HK' },
  { key: 'us', tag: 'US' },
]

function fmtIdx(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

interface FlatRow extends IndexRow {
  tag: string
}

interface GroupSeg {
  tag: string
  items: FlatRow[]
}

function TickerItem({ row, flash }: { row: FlatRow; flash: string }) {
  const up = (row.changePct ?? 0) >= 0
  return (
    <span className="inline-flex items-center gap-2 px-3.5">
      <span className="whitespace-nowrap text-xs text-foreground/85">{row.name}</span>
      {row.price != null && row.price > 0 ? (
        <>
          {/* key=price：价格变化时重挂载以重触发闪烁动画 */}
          <span key={row.price} className={cn('num text-xs font-medium', flash)}>
            {fmtIdx(row.price)}
          </span>
          <span
            className={cn(
              'num inline-flex items-center gap-0.5 text-xs font-semibold',
              up ? 'text-bull' : 'text-bear',
            )}
          >
            <span aria-hidden className="text-[8px] leading-none">
              {up ? '▲' : '▼'}
            </span>
            {row.changePct != null ? formatPct(row.changePct) : '—'}
          </span>
        </>
      ) : (
        <span className="num text-xs text-muted-foreground">—</span>
      )}
      <span aria-hidden className="ml-2 h-3 w-px bg-border/50" />
    </span>
  )
}

/** 跑马灯单拷贝：CN/HK/US 市场标签 + 指数项 + 市场间金色发丝分隔 */
function TickerCopy({ groups, flashMap, dup }: { groups: GroupSeg[]; flashMap: Record<string, string>; dup?: boolean }) {
  return (
    <div className="inline-flex h-9 items-center" aria-hidden={dup || undefined}>
      {groups.map((group, gi) => (
        <span key={group.tag} className="inline-flex items-center">
          <span className="micro-label ml-3 inline-flex items-center rounded-sm border border-border/70 px-1.5 py-px text-[9px]">
            {group.tag}
          </span>
          {group.items.map((row) => (
            <TickerItem key={`${dup ? 'b' : 'a'}-${row.code}`} row={row} flash={flashMap[row.code] ?? ''} />
          ))}
          {gi < groups.length - 1 && <span aria-hidden className="mx-1.5 h-4 w-px bg-gold/40" />}
        </span>
      ))}
    </div>
  )
}

export function TickerBar({ indices }: { indices: IndicesState }) {
  const { data } = indices

  // 价格闪烁（effect 对比上次拉取，与监控墙共用同一 hook）
  const flashMap = usePriceFlash(data)

  const groups = useMemo<GroupSeg[]>(() => {
    if (!data) return []
    return GROUP_ORDER.map((g) => ({
      tag: g.tag,
      items: (data.groups[g.key] ?? [])
        .filter((r) => r.name)
        .map((r): FlatRow => ({ ...r, tag: g.tag })),
    })).filter((seg) => seg.items.length > 0)
  }, [data])

  const hasData = groups.length > 0

  return (
    <div
      className="flex h-9 w-full items-stretch border-b border-border bg-[var(--panel)] text-xs"
      role="marquee"
      aria-label="全球指数实时行情带"
    >
      {/* 左侧固定 LIVE 状态块 */}
      <div className="flex shrink-0 items-center gap-2 border-r border-border/60 px-3 sm:px-4">
        <span className="led text-bull" aria-hidden />
        <span className="micro-label text-[9px] sm:text-[10px]">Live · 全球指数</span>
      </div>

      {/* 跑马灯：右缘渐隐遮罩；24 指数内容更长，放慢至 90s 保持原有速率感 */}
      <div className="relative min-w-0 flex-1 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_16px,black_calc(100%-40px),transparent)]">
        {hasData ? (
          <div className="ticker-track h-9" style={{ animationDuration: '90s' }}>
            <TickerCopy groups={groups} flashMap={flashMap} />
            <TickerCopy groups={groups} flashMap={flashMap} dup />
          </div>
        ) : (
          <div className="flex h-full items-center gap-4 px-4" aria-label="行情加载中">
            {Array.from({ length: 10 }).map((_, i) => (
              <span
                key={i}
                className="shimmer relative h-2.5 overflow-hidden rounded-sm bg-muted/80"
                style={{ width: `${72 + (i % 4) * 26}px` }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
