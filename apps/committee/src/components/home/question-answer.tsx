'use client'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import type { QueryResolution } from '@/lib/research/query-intent'

export function QuestionAnswer({resolution,onClose,onSubmit}:{resolution:QueryResolution|null;onClose:()=>void;onSubmit:(query:string)=>void}) {
  return <Dialog open={!!resolution} onOpenChange={open=>{if(!open)onClose()}}>
    <DialogContent className="sm:max-w-xl">
      <DialogHeader><DialogTitle>{resolution?.kind==='explanation' ? '金融术语与常见问题':'明确研究问题'}</DialogTitle>
        <DialogDescription>{resolution?.query}</DialogDescription></DialogHeader>
      <p className="whitespace-pre-wrap text-sm leading-7 text-foreground/90">{resolution?.answer}</p>
      {resolution?.suggestedQuestions.length ? <div className="flex flex-wrap gap-2">{resolution.suggestedQuestions.map(q=><Button key={q} variant="outline" size="sm" className="h-auto whitespace-normal text-left" onClick={()=>{onClose();onSubmit(q)}}>{q}</Button>)}</div>:null}
      <p className="text-xs text-muted-foreground">解释来自本地金融词典与定义规则；当前问题尚未启动多智能体研究。</p>
    </DialogContent>
  </Dialog>
}
