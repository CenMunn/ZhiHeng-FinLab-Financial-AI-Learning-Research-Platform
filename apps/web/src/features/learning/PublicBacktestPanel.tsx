import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Database,LoaderCircle,RefreshCw} from 'lucide-react';
import {backtestApi,type PublicData,type BacktestConfig,type BacktestRecord,type BacktestHistory} from './backtest-api';
import {BacktestResult} from './BacktestResult';
import './public-backtest.css';

const costs=[['commission_bps','佣金（基点）'],['minimum_commission','最低佣金'],['sell_tax_bps','卖出税（基点）'],['transfer_bps','过户费（基点）'],['slippage_bps','滑点（基点）']] as const;
export function PublicBacktestPanel(){
  const [datasets,setDatasets]=useState<PublicData[]>([]),[selected,setSelected]=useState(''),[config,setConfig]=useState<BacktestConfig|null>(null),[record,setRecord]=useState<BacktestRecord|null>(null);
  const [history,setHistory]=useState<BacktestHistory[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[catalogError,setCatalogError]=useState(''),[historyError,setHistoryError]=useState(''),[retry,setRetry]=useState(0);
  const generation=useRef(0),request=useRef<AbortController|null>(null),historyRequest=useRef<AbortController|null>(null);
  const dataset=datasets.find(d=>d.dataset_id===selected);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setCatalogError('');
    void Promise.allSettled([backtestApi.datasets(controller.signal),backtestApi.runs(controller.signal)]).then(([data,runs])=>{
      if(controller.signal.aborted)return;
      if(data.status==='fulfilled'){
        setDatasets(data.value.datasets);setCatalogError(data.value.unavailable.map(d=>d.message).join(' '));
        setSelected(previous=>previous||data.value.datasets[0]?.dataset_id||'');
        setConfig(previous=>previous||data.value.datasets[0]?.default_config||null);
      }else{setDatasets([]);setCatalogError(data.reason instanceof Error?data.reason.message:'公开数据暂不可用。');}
      if(runs.status==='fulfilled'){setHistory(runs.value);setHistoryError('');}else setHistoryError('历史暂不可用；可以重试读取。');
      setLoading(false);
    });
    return()=>controller.abort();
  },[retry]);
  useEffect(()=>()=>{generation.current++;request.current?.abort();historyRequest.current?.abort();},[]);
  function invalidate(){generation.current++;request.current?.abort();setBusy(false);setRecord(null);setError('');}
  function choose(item:PublicData){invalidate();setSelected(item.dataset_id);setConfig(item.default_config);}
  function edit(next:BacktestConfig){invalidate();setConfig(next);}
  async function refreshHistory(){
    historyRequest.current?.abort();const controller=new AbortController();historyRequest.current=controller;
    try{const next=await backtestApi.runs(controller.signal);if(!controller.signal.aborted){setHistory(next);setHistoryError('');}}
    catch(e){if(!controller.signal.aborted)setHistoryError(e instanceof Error?e.message:'历史读取失败。');}
  }
  async function perform(runId?:string){
    if(!runId&&(!dataset||!config))return;
    request.current?.abort();const controller=new AbortController();request.current=controller;const token=++generation.current;
    setBusy(true);setError('');setRecord(null);
    try{
      const next=runId?await backtestApi.reopen(runId,controller.signal):await backtestApi.run(dataset!,config!,controller.signal);
      if(controller.signal.aborted||token!==generation.current)return;
      setRecord(next);setSelected(next.result.dataset_id);setConfig(next.result.config);void refreshHistory();
    }catch(e){if(!controller.signal.aborted&&token===generation.current)setError(e instanceof Error?e.message:'回测失败，请重试。');}
    finally{if(!controller.signal.aborted&&token===generation.current)setBusy(false);}
  }
  return <section className="public-backtest-panel" aria-labelledby="public-backtest-title">
    <div className="bt-heading"><div><span className="bt-eyebrow"><Database size={14}/>公开历史 · 双市场对照</span><h2 id="public-backtest-title">用真实历史，<br className="bt-mobile-break"/>检验一个想法。</h2><p>先看数据，再看收益。把趋势、持有和周期假设放在同一张实验桌上。</p></div><span className="bt-protocol-tag">2018–2025 数据快照<br/><b>2024–2025 首轮评估</b></span></div>
    {loading?<p role="status">正在校验公开数据目录与实验记录…</p>:null}
    {catalogError?<div className="bt-error" role="alert"><p>{catalogError}</p><button type="button" className="bt-text-button" onClick={()=>setRetry(n=>n+1)}><RefreshCw size={14}/>重新加载数据目录</button></div>:null}
    <div className="bt-markets" role="group" aria-label="公开行情市场">{datasets.map(item=><button type="button" key={item.dataset_id} aria-pressed={selected===item.dataset_id} onClick={()=>choose(item)}><span>{item.market==='ashare'?'A 股 · 贵州茅台':'BTC · USDT 现货'}</span><strong>{item.market==='ashare'?'趋势，还是持有？':'周期，还是趋势？'}<ArrowRight size={19}/></strong><small>{item.row_count.toLocaleString()} 根日线 · {item.market==='ashare'?'XSHG 休市表逐日核对':'96 份月度归档校验'}</small></button>)}</div>
    {config?<form className="bt-config" onSubmit={e=>{e.preventDefault();void perform();}}>
      <div className="bt-config-fields"><label>评估开始<input aria-label="公开回测评估开始" type="date" min="2024-01-01" max="2025-12-30" required value={config.start} onChange={e=>edit({...config,start:e.target.value})}/></label><label>评估结束<input aria-label="公开回测评估结束" type="date" min={config.start} max="2025-12-31" required value={config.end} onChange={e=>edit({...config,end:e.target.value})}/></label><label>均线窗口<input aria-label="公开回测均线窗口" type="number" min="2" max="120" step="1" required value={Number.isNaN(config.window)?'':config.window} onChange={e=>edit({...config,window:e.target.valueAsNumber})}/></label><label>起始现金（{dataset?.currency||record?.result.currency||'报价币'}）<input aria-label="公开回测起始现金" type="number" min="100" max="100000000" step="0.01" required value={config.initial_cash} onChange={e=>edit({...config,initial_cash:e.target.value})}/></label></div>
      <details className="bt-costs"><summary>费用与成交假设 · 全区间固定教学费率</summary><p>A 股按 100 股买入与 T+1；BTC 按 0.00001 步长。信号严格晚于数据可用时间成交，BTC额外延迟一根日线。日线无法保证开盘可成交。</p><div className="bt-config-fields">{costs.map(([key,label])=><label key={key}>{label}<input type="number" min="0" max={key==='minimum_commission'?'1000000':'1000'} step={key==='minimum_commission'?'.01':'.0001'} required value={config.costs[key]} disabled={selected.includes('btc')&&(key==='sell_tax_bps'||key==='transfer_bps')} onChange={e=>edit({...config,costs:{...config.costs,[key]:e.target.value}})}/></label>)}</div></details>
      <div className="bt-run-row"><p>{dataset?<><span className="bt-ready-dot"/>快照已校验 · {dataset.dataset_sha256.slice(0,12)}<br/><small>改参数即开始新实验；不会覆盖已有记录。</small></>:'当前快照未就绪，仍可重开下方历史。'}</p><button className="lab-button lab-primary" type="submit" disabled={loading||busy||!dataset}>{busy?<><LoaderCircle size={17}/>正在计算并保存…</>:<>运行并保存对照<ArrowRight size={17}/></>}</button></div>
    </form>:null}
    {error?<div className="bt-error" role="alert"><p>{error}</p><span>配置已保留，修正后可再次运行。</span></div>:null}
    <div aria-live="polite" aria-busy={busy}>{record?<BacktestResult key={record.run_id} record={record}/>:<div className="bt-empty"><span>{busy?'等待真实计算结果':'先确定比较方式，再查看结论。'}</span><p>{busy?'这里不会按时间播放虚构进度。离开页面会停止接收响应，服务端可能仍完成保存。':'A 股比较均线趋势与买入持有；BTC再加入区块周期上行持有。结果会保留逐日现金、持仓、费用和最差相对区间。'}</p></div>}</div>
    <div className="bt-history"><div><h3>公开数据实验记录</h3><button type="button" className="bt-text-button" onClick={()=>void refreshHistory()}><RefreshCw size={14}/>刷新历史</button></div>{historyError?<p role="alert">{historyError}</p>:null}{!history.length&&!historyError?<p>尚无公开回测记录。上方运行后会自动保存。</p>:null}<div className="bt-history-list">{history.map(row=><button type="button" key={row.run_id} aria-current={record?.run_id===row.run_id?'true':undefined} onClick={()=>void perform(row.run_id)}><b>{row.market==='ashare'?'A 股':'BTC'} · {row.window} 日均线</b><span>{row.start} — {row.end}</span><small>{new Date(row.created_at).toLocaleString('zh-CN',{hour12:false})} · 引擎 {row.engine_sha256.slice(0,8)}</small></button>)}</div></div>
  </section>;
}
