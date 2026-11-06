'use client'
import {useEffect,useState} from 'react'
import Link from 'next/link'
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,Tooltip,CartesianGrid} from 'recharts'
import {Header} from '@/components/home/header'
import {useAuth} from '@/components/auth/auth-provider'
import {Button} from '@/components/ui/button'
import type {ForecastSummary,PriceForecastResult} from '@/lib/forecast/types'
const pct=(n:number|null)=>n===null?'不适用':(n*100).toFixed(2)+'%'
export function ForecastWorkbench(){const {user}=useAuth();return <ForecastContent key={user?.id??'guest'}/>}
function ForecastContent(){
  const {user,setOpen}=useAuth(),[summary,setSummary]=useState<ForecastSummary|null>(null),[code,setCode]=useState('600519')
  const [result,setResult]=useState<PriceForecastResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{
    if(!user)return
    const controller=new AbortController()
    fetch('/api/forecast',{signal:controller.signal}).then(async r=>{const v=await r.json();if(!r.ok)throw Error(v.error);setSummary(v)})
      .catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return ()=>controller.abort()
  },[user])
  const run=async(mode:'snapshot'|'live')=>{
    if(!user){setOpen(true);return}setBusy(true);setError('');setResult(null)
    try{const r=await fetch('/api/forecast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stockCode:code,mode})});const v=await r.json();if(!r.ok)throw Error(v.error);setResult(v)}
    catch(e){setError(e instanceof Error?e.message:'预测失败')}finally{setBusy(false)}
  }
  const chart=result?[...result.history.map((p,i)=>({...p,observed:p.close,predicted:i===result.history.length-1?p.close:null})),{date:'下一交易日',close:result.predictedClose,observed:null,predicted:result.predictedClose}]:[]
  return <><Header view="home" onLogoClick={()=>{window.location.href='/'}}/><main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <section className="panel p-6 sm:p-8"><p className="text-xs font-semibold tracking-wider text-primary">量化研究 · 实验模块</p>
      <h1 className="mt-3 text-2xl font-semibold sm:text-3xl">股票价格变化预测</h1>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">使用官方LightGBM训练模型，研究下一交易日前复权收盘价变化。页面展示时间外误差与对照结果，输出独立于投委会评级和仓位。</p>
      <div className="mt-4 flex flex-wrap gap-3 text-sm"><Link className="underline underline-offset-4" href="/evidence">财报证据工作台</Link><a className="underline underline-offset-4" href="https://github.com/lightgbm-org/LightGBM" target="_blank" rel="noreferrer">官方模型仓库</a></div>
    </section>
    <section className="panel space-y-4 p-5"><h2 className="text-lg font-semibold">选择输入并实际推理</h2>
      <div className="flex flex-wrap items-center gap-3"><label htmlFor="forecast-stock" className="text-sm">实验股票</label>
        <select id="forecast-stock" disabled={busy} value={code} onChange={e=>{setCode(e.target.value);setResult(null)}} className="h-10 rounded-md border border-border bg-background px-3 text-sm">
          {(summary?.dataManifest??[{code:'600519',name:'贵州茅台'},{code:'000858',name:'五粮液'}]).map(s=><option key={s.code} value={s.code}>{s.name} {s.code}</option>)}</select>
        <Button disabled={busy||!!user&&!summary} onClick={()=>void run('snapshot')}>{busy?'推理中…':'冻结快照推理'}</Button>
        <Button disabled={busy||!!user&&!summary} variant="outline" onClick={()=>void run('live')}>采集当前日线并推理</Button></div>
      <p className="text-xs leading-6 text-muted-foreground">快照模式可离线重现；当前日线模式需要联网，来源失败会明确报错。模型不指定下一交易日的日历日期，也不保证上涨或盈利。</p>
      {!user&&<p className="text-sm">请登录后查看实验结果和运行模型。</p>}{error&&<p role="alert" className="text-sm text-red-500">{error}</p>}
    </section>
    {result&&<section className="panel space-y-4 p-5"><div className="flex flex-wrap justify-between gap-2"><h2 className="text-lg font-semibold">{result.stockName} · 实验输出</h2><span className="text-xs text-muted-foreground">输入截至 {result.inputDate}</span></div>
      <div className="grid gap-4 sm:grid-cols-3">{[['模型估计变化',`${result.predictedChangePct.toFixed(3)}%`],['模型估计收盘',`${result.predictedClose.toFixed(2)} 元`],['本次请求耗时',`${result.inferenceMs.toFixed(1)} ms`]].map(([label,value])=><div className="rounded-lg border border-border p-4" key={label}><p className="text-xs text-muted-foreground">{label}</p><p className="num mt-2 text-2xl">{value}</p></div>)}</div>
      <div className="h-64 w-full" aria-label="过去30日观察价格及下一交易日模型估计"><ResponsiveContainer width="100%" height="100%"><LineChart data={chart}><CartesianGrid strokeDasharray="3 3" opacity={.2}/><XAxis dataKey="date" minTickGap={55}/><YAxis domain={['auto','auto']} width={60}/><Tooltip/><Line dataKey="observed" name="观察收盘" stroke="#119b87" dot={false}/><Line dataKey="predicted" name="模型估计" stroke="#c99543" strokeDasharray="5 5" dot={{r:4}}/></LineChart></ResponsiveContainer></div>
      <p className="text-sm leading-6 text-muted-foreground">验证残差范围：{result.errorBandPct.map(n=>n.toFixed(2)+'%').join(' 至 ')}，来自验证段绝对误差90%分位，属于经验范围。{result.inputSource}；估计值不是合理目标价或投资收益承诺。</p>
    </section>}
    {summary&&<><section className="panel space-y-4 p-5"><h2 className="text-lg font-semibold">固定时间外测试 · 六只股票</h2>
      <p className="text-sm leading-6">{summary.benchmarkConclusion}</p>
      <div className="overflow-x-auto"><table className="w-full min-w-[580px] text-left text-sm"><thead><tr className="border-b border-border"><th className="p-3">方案</th><th>样本数</th><th>MAE（百分点）</th><th>RMSE（百分点）</th><th>方向准确率</th></tr></thead><tbody>{Object.entries(summary.comparisons).map(([name,m])=><tr key={name} className="border-b border-border"><td className="p-3">{{lightgbm:'LightGBM',zero_change:'零变动基线',one_day_momentum:'单日动量基线'}[name]??name}</td><td>{m.samples}</td><td>{m.maePercentagePoints.toFixed(3)}</td><td>{m.rmsePercentagePoints.toFixed(3)}</td><td>{pct(m.directionAccuracy)}</td></tr>)}</tbody></table></div>
      <p className="text-xs leading-6 text-muted-foreground">方向仅评价非零预测，零变动基线不输出方向。测试段始于{summary.segments.test.firstFeatureDate}；训练标签截至{summary.segments.train.lastLabelDate}。训练、验证和测试按日期切分，并剔除跨边界标签。</p>
      <div className="grid gap-4 sm:grid-cols-3">{Object.entries(summary.segments).map(([name,s])=><div className="rounded-lg border border-border p-3 text-xs" key={name}><p className="font-medium">{{train:'训练段',valid:'验证段',test:'测试段'}[name]??name} · {s.samples} 样本</p><p className="mt-2 text-muted-foreground">{s.firstFeatureDate} 至 {s.lastFeatureDate}</p></div>)}</div>
      <p className="text-xs leading-6 text-muted-foreground">本机CPU训练{summary.costs.trainingSeconds.toFixed(3)}秒；{summary.featureNames.length}个特征，{summary.numBoostRound}轮。无付费大模型调用；电费和硬件成本未计量。页面请求耗时包含读取、校验、推理；联网模式另包含采集时间。</p>
    </section><section className="panel space-y-3 p-5"><h2 className="text-lg font-semibold">证据与适用边界</h2><ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-muted-foreground">{summary.limitations.map(x=><li key={x}>{x}</li>)}</ul>
      <p className="text-sm leading-6"><strong>自研：</strong>{summary.selfDeveloped}。<strong>外部组件：</strong>{summary.externalComponents}。</p>
      <a href="/forecast/summary.json" download className="text-sm underline underline-offset-4">下载完整实验记录与来源索引</a>
    </section></>}
  </main></>
}
