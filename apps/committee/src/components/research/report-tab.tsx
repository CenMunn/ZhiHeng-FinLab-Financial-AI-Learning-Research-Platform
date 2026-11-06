'use client'

// 研究报告 Tab — 文档阅读器美学：元信息头 + Markdown 渲染 + 复制 / 下载 / 打印工具栏
// 元信息头随 .print-report 一起打印（研究对象 / 生成时间 / 报告引擎 / 数据源）

import { useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy, Download, FileText, Printer } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { TerminalWait, fmtDateTime } from '@/components/research/bits'
import { cn } from '@/lib/utils'
import { fetchReportMarkdown } from '@/lib/research/report-download'

interface ReportTabProps {
  reportMd: string | null
  stockName: string | null
  generatedAt?: string | null
  audited?: boolean
  ended?: boolean
  downloadUrl?: string
  methodLabel?: string
  sourceLabel?: string
}

const reportMarkdownComponents: Components = {
  img: ({ alt }) => <span>［图片已禁用：{alt ?? '未命名'}］</span>,
  table: ({ children, ...props }) => (
    <div className="report-table max-w-full overflow-x-auto">
      <table {...props}>{children}</table>
    </div>
  ),
}

function ReportMarkdown({ children }: { children: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={reportMarkdownComponents}>{children}</ReactMarkdown>
}

function MetaCell({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <span className="micro-label">{label}</span>
      <p className={cn('mt-1 truncate text-[13px] font-semibold text-foreground/90', mono && 'num')} title={value}>
        {value}
      </p>
    </div>
  )
}

export function ReportTab({ reportMd, stockName, generatedAt, audited=false, ended=false, downloadUrl, methodLabel, sourceLabel }: ReportTabProps) {
  const [copied, setCopied] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const { toast } = useToast()
  const appendixAt=reportMd?.indexOf('## 五、评分说明与资料范围')??-1
  const mainReport=appendixAt>=0?reportMd!.slice(0,appendixAt):reportMd
  const appendix=appendixAt>=0?reportMd!.slice(appendixAt):null

  const copyReport = async () => {
    if (!reportMd) return
    try {
      await navigator.clipboard.writeText(reportMd)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
      toast({ title: '已复制 Markdown 到剪贴板' })
    } catch {
      toast({ title: '复制失败', description: '浏览器拒绝了剪贴板访问', variant: 'destructive' })
    }
  }

  const downloadReport = async () => {
    if (!reportMd || downloading) return
    setDownloading(true)
    try {
    const markdown = downloadUrl ? await fetchReportMarkdown(downloadUrl) : reportMd
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${stockName ?? 'research'}-投研报告.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    toast({ title: '已准备报告下载', description: `${stockName ?? 'research'}-投研报告.md` })
    } catch (error) {
      toast({ title: '下载失败', description: error instanceof Error ? error.message : '请稍后重试', variant: 'destructive' })
    } finally { setDownloading(false) }
  }

  return (
    <div className="space-y-4">
      {/* 工具栏 */}
      <div className="no-print panel-flat flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
        <p className="micro-label flex items-center gap-2">
          <FileText className="size-3.5 text-primary" aria-hidden />
          Research Report · 可解释投研报告
        </p>
        <div className="flex gap-1.5">
          <Button
            variant="outline"
            size="sm"
            className="min-h-8 gap-1.5 border-border/70 bg-transparent text-xs"
            onClick={() => void copyReport()}
            disabled={!reportMd}
            aria-label="复制 Markdown"
          >
            {copied ? <Check className="size-3.5 text-bull" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
            复制 Markdown
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="min-h-8 gap-1.5 border-border/70 bg-transparent text-xs"
            onClick={downloadReport}
            disabled={!reportMd || downloading}
            aria-label="下载 .md 文件"
          >
            <Download className="size-3.5" aria-hidden />
            {downloading ? '下载中…' : '下载 .md'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="min-h-8 gap-1.5 border-border/70 bg-transparent text-xs"
            onClick={() => window.print()}
            disabled={!reportMd}
            aria-label="打印或导出 PDF"
          >
            <Printer className="size-3.5" aria-hidden />
            打印 PDF
          </Button>
        </div>
      </div>

      {/* 文档正文 */}
      <div className="panel print-report mx-auto max-w-4xl px-6 py-8 sm:px-10 sm:py-10">
        {reportMd ? (
          <>
            {/* 报告元信息头 */}
            <div className="mb-7 grid gap-x-6 gap-y-3 border-b border-border/60 pb-5 sm:grid-cols-2 lg:grid-cols-4">
              <MetaCell label="Subject · 研究对象" value={stockName ?? '—'} mono={false} />
              <MetaCell label="Generated · 生成时间" value={fmtDateTime(generatedAt) ?? '—'} />
              <MetaCell label="Method · 报告方式" value={methodLabel ?? (audited ? '结构化证据汇编' : '初赛历史输出')} />
              <MetaCell label="Sources · 数据源" value={sourceLabel ?? (audited ? '见逐条来源及核验状态' : '原始快照与检索，未作本轮核验')} mono={false} />
            </div>
            <div className="report-md [overflow-wrap:anywhere]">
              <ReportMarkdown>{mainReport ?? ''}</ReportMarkdown>
              {appendix && (
                <>
                  <details className="no-print mt-6 border-t border-border pt-4">
                    <summary className="cursor-pointer text-sm font-medium">评分说明、资料范围与来源附录</summary>
                    <div className="mt-4"><ReportMarkdown>{appendix}</ReportMarkdown></div>
                  </details>
                  {/* A print-only copy includes the appendix even when details is closed, including Ctrl+P. */}
                  <div className="report-appendix-print"><ReportMarkdown>{appendix}</ReportMarkdown></div>
                </>
              )}
            </div>
          </>
        ) : ended ? (
          <p className="p-5 text-sm text-muted-foreground">流程已结束，本轮未生成报告。请查看失败原因或补充资料后重试。</p>
        ) : (
          <div className="space-y-4">
            <TerminalWait label="REPORT GENERATING · 报告生成中" model="报告模型" />
            <div className="space-y-3" aria-hidden>
              <div className="shimmer h-6 w-1/2 rounded bg-muted/70" />
              <div className="shimmer h-3.5 w-full rounded bg-muted/50" />
              <div className="shimmer h-3.5 w-11/12 rounded bg-muted/50" />
              <div className="shimmer h-3.5 w-full rounded bg-muted/50" />
              <div className="shimmer h-3.5 w-3/4 rounded bg-muted/50" />
            </div>
            <p className="num flex items-center gap-1.5 pt-1 text-[10px] text-muted-foreground/70">
              WRITING
              <span className="caret-blink inline-block h-3 w-[7px] bg-primary/70" aria-hidden />
            </p>
          </div>
        )}
      </div>

      <p className="micro-label no-print text-center">
        请按报告内的来源、报告期和核验状态复核数字与结论
      </p>
    </div>
  )
}
