'use client'

// Home 视图编排：Hero（终端指令中心）→ 全球指数监控墙 → 自选池 → 最近研究 → 核心流程
// useIndices 在此持有全局唯一轮询实例（10s），向下传递给 Hero / MarketMonitor 共享
// 市场数据统一收敛在 Global Market Monitor（顶部跑马灯已按导航极简原则移除）

import { useAuth } from '@/components/auth/auth-provider'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { useIndices } from '@/hooks/use-indices'
import { Hero } from '@/components/home/hero'
import { MarketMonitor } from '@/components/home/market-monitor'
import { PipelineFlow } from '@/components/home/pipeline-flow'
import { PortfolioDialog } from '@/components/home/portfolio-dialog'
import { RecentSessions } from '@/components/home/recent-sessions'
import { WatchlistSection } from '@/components/home/watchlist-section'
import type { OpenSessionFn } from '@/lib/client-utils'

interface HomeViewProps {
  /** 变化时重新拉取自选池与最近研究（从研究视图返回时 +1） */
  refreshKey: number
  onSubmit: (query: string) => Promise<void> | void
  onOpenSession: OpenSessionFn
}

export function HomeView({ refreshKey, onSubmit, onOpenSession }: HomeViewProps) {
  const {user,setOpen:openAuth,loading}=useAuth()
  const [portfolioOpen, setPortfolioOpen] = useState(false)
  const indices = useIndices(10_000)

  return (
    <div className="w-full">
      <Hero onSubmit={onSubmit} onOpenPortfolio={() => user?setPortfolioOpen(true):openAuth(true)} indices={indices} />

      <div className="mx-auto w-full max-w-7xl space-y-14 px-4 pb-16 sm:space-y-16 sm:px-6 sm:pb-20">
        <a href="/evidence" className="panel block p-5 transition-colors hover:border-primary/50">
          <h2 className="font-semibold">财报核验与同行比较</h2>
          <p className="mt-2 text-sm text-muted-foreground">茅台、五粮液2025年度资料已登记；其余8只公司的原始资料待补充。核对原文、查看公式，导出证据与报告。</p>
        </a>
        <MarketMonitor indices={indices} onResearch={onSubmit} />
        {user ? <>
        <WatchlistSection refreshKey={refreshKey} onOpenSession={onOpenSession} onQuickResearch={onSubmit} />
        <RecentSessions refreshKey={refreshKey} onOpenSession={onOpenSession} />
        </> : <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><h2 className="font-semibold">个人研究档案</h2><p className="mt-1 text-sm text-muted-foreground">登录后保存财报核验、研究记录、自选与组合体检。概念和黑话问答可直接使用。</p></div><Button disabled={loading} onClick={()=>openAuth(true)}>登录研究工作台</Button></section>}
        <PipelineFlow />
      </div>

      {user&&<PortfolioDialog key={user.id} open={portfolioOpen} onOpenChange={setPortfolioOpen} />}
    </div>
  )
}
