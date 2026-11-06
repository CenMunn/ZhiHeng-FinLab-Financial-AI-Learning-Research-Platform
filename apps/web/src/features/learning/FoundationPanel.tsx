import {useEffect,useRef,useState} from 'react';
import {RefreshCw,Database,LoaderCircle} from 'lucide-react';
import {foundationApi,type FoundationConfig,type FoundationHistory,type FoundationRecord,type FoundationSnapshot} from './foundation-api';
import {FoundationResult} from './FoundationResult';
import {FoundationPreview} from './FoundationPreview';
import './foundation.css';
import './foundation-workbench.css';

const markets={ashare:'A 股',btc:'BTC'};
const costFields=[['commission_bps','佣金（基点）'],['minimum_commission','最低佣金（报价币）'],['sell_tax_bps','卖出税费（基点）'],['transfer_bps','双边过户费（基点）'],['slippage_bps','滑点（基点）']] as const;

export function FoundationPanel(){
  const [snapshots,setSnapshots]=useState<FoundationSnapshot[]>([]),[history,setHistory]=useState<FoundationHistory[]>([]);
  const [selected,setSelected]=useState(''),[config,setConfig]=useState<FoundationConfig|null>(null),[record,setRecord]=useState<FoundationRecord|null>(null);
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[historyError,setHistoryError]=useState(''),[historyLoading,setHistoryLoading]=useState(false),[retry,setRetry]=useState(0);
  const request=useRef<AbortController|null>(null),historyRequest=useRef<AbortController|null>(null),generation=useRef(0);
  const snapshot=snapshots.find(item=>item.snapshot_id===selected);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');
    void Promise.allSettled([foundationApi.snapshots(controller.signal),foundationApi.runs(controller.signal)]).then(([catalog,runs])=>{
      if(controller.signal.aborted)return;
      if(catalog.status==='fulfilled'){
        setSnapshots(catalog.value);
        if(catalog.value.length){setSelected(catalog.value[0].snapshot_id);setConfig(catalog.value[0].default_config);}
      }else setError(catalog.reason instanceof Error?catalog.reason.message:'样例暂时无法加载。');
      if(runs.status==='fulfilled'){setHistory(runs.value);setHistoryError('');}else setHistoryError('历史记录暂时无法读取，检查时仍可尝试保存新记录。');
      setLoading(false);
    });
    return()=>controller.abort();
  },[retry]);
  useEffect(()=>()=>{generation.current++;request.current?.abort();historyRequest.current?.abort();},[]);

  function choose(value:string){generation.current++;request.current?.abort();const next=snapshots.find(item=>item.snapshot_id===value);if(!next)return;setSelected(value);setConfig(next.default_config);setRecord(null);setError('');setBusy(false);}
  function edit(next:FoundationConfig){setConfig(next);setRecord(null);setError('');}
  async function perform(runId?:string){
    if(busy||(!runId&&(!snapshot||!config)))return;
    request.current?.abort();const controller=new AbortController();request.current=controller;const revision=++generation.current;setBusy(true);setError('');
    try{
      let result:FoundationRecord;
      if(runId)result=await foundationApi.reopen(runId,controller.signal);
      else if(snapshot&&config)result=await foundationApi.run({snapshot_id:snapshot.snapshot_id,expected_snapshot_sha256:snapshot.snapshot_sha256,config},controller.signal);
      else throw Error('请先加载要检查的数据快照。');
      if(controller.signal.aborted||revision!==generation.current)return;
      setRecord(result);
      const matching=snapshots.find(item=>item.snapshot_id===result.snapshot.snapshot_id&&item.snapshot_sha256===result.result.snapshot_sha256);
      if(runId&&matching){setSelected(matching.snapshot_id);setConfig(result.result.config);}
      try{const rows=await foundationApi.runs(controller.signal);if(!controller.signal.aborted&&revision===generation.current){setHistory(rows);setHistoryError('');}}
      catch{if(!controller.signal.aborted&&revision===generation.current)setHistoryError('记录已读取或保存，但历史列表刷新失败；可重新加载列表。');}
    }catch(reason){if(!controller.signal.aborted&&revision===generation.current)setError(reason instanceof Error?reason.message:'检查失败，请重试。');}
    finally{if(!controller.signal.aborted&&revision===generation.current)setBusy(false);}
  }
  async function reloadHistory(){
    historyRequest.current?.abort();const controller=new AbortController();historyRequest.current=controller;
    const revision=generation.current;setHistoryLoading(true);
    try{const rows=await foundationApi.runs(controller.signal);if(!controller.signal.aborted&&revision===generation.current){setHistory(rows);setHistoryError('');}}
    catch{if(!controller.signal.aborted&&revision===generation.current)setHistoryError('历史记录仍无法读取，请检查服务后重试。');}
    finally{if(!controller.signal.aborted)setHistoryLoading(false);}
  }
  function exportRecord(){if(!record)return;const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const anchor=document.createElement('a');anchor.href=url;anchor.download=`${record.run_id}.json`;anchor.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return <section className="foundation-panel" aria-labelledby="foundation-title">
    <div className="foundation-title"><Database size={22}/><div><h2 id="foundation-title">共同实验底座</h2><p>先核对数据与口径，再讨论策略表现。</p></div><span className="foundation-data-tag">合成样例</span></div>
    <div className="foundation-workbench"><div className="foundation-config">
    {loading?<p role="status">正在读取样例与本地记录…</p>:null}
    {!loading&&!snapshots.length?<div><p role="alert">{error||'没有可用的数据快照。'}</p><button type="button" className="lab-button lab-secondary" onClick={()=>setRetry(value=>value+1)}>重新加载样例</button></div>:null}
    {snapshot&&config?<><form onSubmit={event=>{event.preventDefault();void perform();}}>
      <fieldset disabled={busy||loading}><legend className="sr-only">实验检查配置</legend><div className="foundation-form-grid">
        <label>数据快照<select value={selected} onChange={event=>choose(event.target.value)}>{snapshots.map(item=><option key={item.snapshot_id} value={item.snapshot_id}>{markets[item.market]} / {item.row_count} 条合成日线</option>)}</select></label>
        <label>指标窗口（期）<input type="number" min="2" max="120" required value={config.window} onChange={event=>edit({...config,window:Number(event.target.value)})}/></label>
        <label>训练段样本数<input type="number" min="3" max={snapshot.row_count-2} required value={config.train_count} onChange={event=>edit({...config,train_count:Number(event.target.value)})}/></label>
        <label>验证段样本数<input type="number" min="1" max={snapshot.row_count-4} required value={config.validation_count} onChange={event=>edit({...config,validation_count:Number(event.target.value)})}/></label>
      </div><p className="foundation-helper">测试段保留剩余样本；标签为后 {config.horizon} 期收益，跨段标签会清除。1 基点 = 0.01%。</p>
      <details className="foundation-cost-settings"><summary>费用设置：全部为教学假设</summary><div className="foundation-cost-grid">{costFields.map(([key,label])=><label key={key}>{label}<input type="text" inputMode="decimal" required value={config.costs[key]} onChange={event=>edit({...config,costs:{...config.costs,[key]:event.target.value}})}/></label>)}</div></details>
      <button type="submit" className="lab-button lab-primary" aria-busy={busy}>{busy?<LoaderCircle className="foundation-spinner" size={16}/>:null}{busy?'正在检查并记录…':'检查并记录实验'}</button></fieldset>
      <p className="foundation-helper">这是管线检查，不执行收益回测或模型训练。记录保存于本机，相同输入重试不会重复创建。</p>
    </form><details className="foundation-provenance"><summary>查看当前快照来源与时间口径</summary><dl><div><dt>样本期间</dt><dd>{snapshot.start} 至 {snapshot.end}</dd></div><div><dt>来源</dt><dd>{snapshot.source_uri}</dd></div><div><dt>日历</dt><dd>{snapshot.calendar_source}</dd></div><div><dt>可用数据截止</dt><dd>{config.as_of}</dd></div><div><dt>快照 SHA-256</dt><dd>{snapshot.snapshot_sha256}</dd></div></dl><ul>{snapshot.limitations.map(text=><li key={text}>{text}</li>)}</ul></details></>:null}
    {error&&snapshots.length?<p className="error-text" role="alert">{error}</p>:null}

    </div><div className="foundation-main" aria-busy={busy}>
      {busy?<p className="foundation-running" role="status">正在读取或检查这次配置，请稍候。</p>:null}
      {record?<FoundationResult key={record.run_id} record={record} onExport={exportRecord}/>:snapshot&&config?<FoundationPreview snapshot={snapshot} config={config}/>:<section className="foundation-preview"><h3>{loading?'正在准备实验快照':'从一份实验记录继续'}</h3><p>{loading?'数据与本地记录就绪后，即可开始配置。':'当前样例目录尚不可用；仍可从左侧重开已有记录，或重新加载样例。'}</p></section>}
    </div>
    <section className="foundation-history" aria-label="本地实验记录"><h3>本地实验记录</h3>{!loading&&!historyError&&!history.length?<p>尚无记录。完成一次检查后，会在这里留下快照与配置。</p>:null}{historyError?<p role="alert">{historyError}</p>:null}<button type="button" className="lab-button lab-secondary" disabled={busy||loading||historyLoading} onClick={()=>void reloadHistory()}>{historyLoading?'正在读取历史…':'重新加载历史'}</button><ul>{history.map(row=><li key={row.run_id}><button type="button" disabled={busy||loading} aria-current={row.run_id===record?.run_id?'true':undefined} onClick={()=>void perform(row.run_id)}><RefreshCw size={14}/><span>{markets[row.market]} / 均线 {row.window} 期</span><small>{row.created_at.slice(5,19).replace('T',' ')} UTC <code title={row.input_hash}>{row.input_hash.slice(0,6)}</code></small><span>重开</span></button></li>)}</ul></section>
    </div>
  </section>;
}
