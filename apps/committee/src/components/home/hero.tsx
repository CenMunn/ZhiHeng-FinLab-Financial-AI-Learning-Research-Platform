'use client'

import {useRef,useState} from 'react'
import {ArrowUpRight,BookOpenText,FileCheck2,Layers3,PieChart} from 'lucide-react'
import {SearchBox,type SearchBoxHandle} from './search-box'
import {SlangDialog} from './slang-dialog'
import {SLANG_TERMS_COUNT} from '@/lib/data/slang-dictionary'
import facts from '@/lib/data/verified-facts.json'
import type {IndicesState} from './market-monitor'
const EXAMPLES=['比较茅台与五粮液2025年度现金流','什么是市盈率','缩量横盘是什么意思','茅台的归母净利润与净利润有什么区别']
const companies=[{code:'600519',name:'贵州茅台'},{code:'000858',name:'五粮液'}]
const columns=[{key:'revenue',label:'营业收入'},{key:'netProfit',label:'归母净利润'},{key:'ocf',label:'经营现金流'}]
function SourceBrief(){
 return <aside className="panel min-w-0 overflow-hidden xl:w-[420px] xl:shrink-0" aria-label="已登记年报资料概览">
  <div className="flex items-center justify-between border-b border-border bg-muted/25 px-5 py-4"><div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-gold">Source brief / 资料简报</p><h2 className="mt-1.5 text-base font-semibold">白酒同行 · 2025年度</h2></div><FileCheck2 className="size-5 text-primary"/></div>
  <div className="overflow-x-auto p-5"><table className="w-full min-w-[310px] text-left text-xs"><caption className="mb-3 text-right text-[11px] text-muted-foreground">单位：亿元人民币 · 展示值四舍五入</caption><thead><tr className="border-b border-border"><th className="pb-3 font-medium text-muted-foreground">公司</th>{columns.map(c=><th key={c.key} className="pb-3 text-right font-medium text-muted-foreground">{c.label}</th>)}</tr></thead><tbody>{companies.map(company=><tr key={company.code} className="border-b border-border/60"><th className="py-4 font-medium">{company.name}<span className="num mt-1 block text-[10px] font-normal text-muted-foreground">{company.code}</span></th>{columns.map(c=>{const fact=facts.find(f=>f.stockCode===company.code&&f.metric===c.key);return <td key={c.key} className="num py-4 text-right">{fact?new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(fact.value/1e8):'待补充'}</td>})}</tr>)}</tbody></table>
  <p className="mt-4 text-xs leading-6 text-muted-foreground">归母利润是合并利润表中的归属指标。财务子公司与收入核算差异仍需结合附注解读，不能据此直接判断投资优劣。</p>
  <div className="mt-4 flex flex-wrap gap-3 text-xs">{companies.map(c=>{const f=facts.find(f=>f.stockCode===c.code&&f.metric==='revenue');return f?<a className="inline-flex items-center gap-1 text-primary underline underline-offset-4" href={f.sourceUrl} key={c.code} target="_blank" rel="noopener noreferrer">{c.name}年报 · 第{f.page}页<ArrowUpRight className="size-3"/></a>:null})}</div>
  </div><a href="/evidence" className="flex items-center justify-between border-t border-border bg-muted/20 px-5 py-3 text-xs font-medium text-primary">查看原值、公式与证据目录<ArrowUpRight className="size-4"/></a>
 </aside>
}
export function Hero({onSubmit,onOpenPortfolio,indices}:{onSubmit:(q:string)=>Promise<void>|void;onOpenPortfolio:()=>void;indices:IndicesState}) {
 const searchRef=useRef<SearchBoxHandle>(null),[slangOpen,setSlangOpen]=useState(false)
 const total=indices.data?Object.values(indices.data.groups).reduce((n,r)=>n+(r?.length??0),0):null
 return <section id="research-desk" className="relative border-b border-border/70">
  <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-14">
   <div className="flex flex-col gap-8 xl:flex-row xl:items-center xl:gap-12">
    <div className="min-w-0 flex-1">
     <p className="text-[11px] font-semibold tracking-[0.2em] text-gold">猫猫小分队 · 金融研究工作台</p>
     <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">从财报原文，<br className="hidden sm:block"/>到可复核的研究结论</h1>
     <p className="mt-5 max-w-xl text-sm leading-7 text-muted-foreground sm:text-[15px]">核对公司、年度和报表范围，比较同口径财务指标，整理正式研究报告。资料缺口与推断单独呈现，每项结论都保留来源和复核路径。</p>
     <div className="mt-6 flex flex-wrap gap-3"><a href="/evidence" className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground"><FileCheck2 className="size-4"/>开始财报核验与同行比较</a><button type="button" className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-3 text-sm" onClick={onOpenPortfolio}><PieChart className="size-4"/>组合体检</button></div>
     <div className="mt-7"><label className="mb-2 block text-xs font-medium text-muted-foreground">提出研究问题，或查询金融概念与市场黑话</label><SearchBox ref={searchRef} onSubmit={onSubmit}/></div>
     <div className="mt-3 flex flex-wrap gap-2">{EXAMPLES.map(q=><button key={q} type="button" onClick={()=>searchRef.current?.submitExternal(q)} className="rounded-md border border-border bg-card/60 px-2.5 py-2 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground">{q}</button>)}</div>
     <button className="mt-4 inline-flex items-center gap-1.5 text-xs text-primary" onClick={()=>setSlangOpen(true)}><BookOpenText className="size-3.5"/>黑话词典 · {SLANG_TERMS_COUNT}条解释</button>
    </div><SourceBrief/>
   </div>
   <div className="mt-8 grid gap-3 sm:grid-cols-3"><div className="rounded-md border border-border bg-card/60 p-4"><p className="flex items-center gap-2 text-xs font-medium"><FileCheck2 className="size-4 text-primary"/>已登记财报</p><p className="mt-2 text-sm">2家公司 · 6项年度金额</p><p className="mt-1 text-xs text-muted-foreground">原文、页码、口径与文件哈希</p></div><div className="rounded-md border border-border bg-card/60 p-4"><p className="flex items-center gap-2 text-xs font-medium"><Layers3 className="size-4 text-gold"/>研究流程</p><p className="mt-2 text-sm">资料核验 → 分析 → 复核报告</p><p className="mt-1 text-xs text-muted-foreground">依据不足时保留缺口，暂停投资决策</p></div><div className="rounded-md border border-border bg-card/60 p-4"><p className="text-xs font-medium">行情辅助</p><p className="mt-2 text-sm">{total===null?'指数数据获取中':`${total}项指数返回数据`}</p><p className="mt-1 text-xs text-muted-foreground">以采集时点为准，不等同交易所实时流</p></div></div>
  </div><SlangDialog open={slangOpen} onOpenChange={setSlangOpen}/>
 </section>
}
