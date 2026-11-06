import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {Activity,Download,RefreshCw} from 'lucide-react';
import {volatilityApi,volatilityPercent,metricNumber,volatilityReport,type VolatilityEnvelope,type VolatilitySummary,type VolatilityRecord,type VolatilityObservation,type VolatilityModel} from './volatility-api';
import './public-backtest.css';
import './volatility.css';
import {VolatilityDiagnostics} from './VolatilityDiagnostics';

function download(name:string,text:string,type:string){const url=URL.createObjectURL(new Blob([text],{type})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
const marketName=(market:string)=>market==='ashare'?'A 股':'BTC';
const formatTime=(value:string)=>new Date(value).toLocaleString('zh-CN',{hour12:false});

function VolatilityCurve({record,method,quarter,regime}:{record:VolatilityRecord;method:string;quarter:string;regime:string}){
  const [point,setPoint]=useState(0),id=useId();
  const rows=useMemo(()=>record.observations.filter(row=>(quarter==='all'||row.fold===quarter)),[record,quarter]);
  const visible=rows.filter(row=>regime==='all'||row.regime===regime),current=visible[Math.min(point,visible.length-1)];
  const first=Date.parse(rows[0]?.session||''),last=Date.parse(rows.at(-1)?.session||'');
  const x=(row:VolatilityObservation)=>58+(Date.parse(row.session)-first)/Math.max(1,last-first)*780;
  const amplitude=(variance:number)=>Math.sqrt(variance*record.annualization)*100;
  const max=Math.max(1,...visible.flatMap(row=>[amplitude(row.realized_variance),amplitude(row.predictions[method])]))*1.08;
  const y=(value:number)=>205-value/max*175;
  function path(actual:boolean){let started=false;return rows.map(row=>{if(regime!=='all'&&row.regime!==regime){started=false;return '';}const command=started?'L':'M';started=true;return `${command}${x(row)},${y(amplitude(actual?row.realized_variance:row.predictions[method]))}`;}).join(' ');}
  function selectAt(clientX:number,svg:SVGSVGElement){const box=svg.getBoundingClientRect(),position=(clientX-box.left)/box.width*880;let index=0;for(let i=1;i<visible.length;i++)if(Math.abs(x(visible[i])-position)<Math.abs(x(visible[index])-position))index=i;setPoint(index);}
  return <section className="vol-curve" aria-label="真实波动代理与预测曲线"><div className="vol-section-heading"><h4>预测的是起伏幅度</h4><span>{visible.length} 条 · 年化幅度 % · 全部极端日保留</span></div>
    {current?<><figure><svg viewBox="0 0 880 245" role="img" aria-label={`${record.overall[method].name}与事后波动代理，年化百分比曲线`} onPointerMove={event=>{if(event.pointerType==='mouse')selectAt(event.clientX,event.currentTarget);}} onPointerDown={event=>selectAt(event.clientX,event.currentTarget)}>
      {[0,1,2,3].map(i=><g key={i}><line className="vol-grid" x1="58" x2="838" y1={y(max*i/3)} y2={y(max*i/3)}/><text x="0" y={y(max*i/3)+4}>{(max*i/3).toFixed(1)}%</text></g>)}
      <path className="vol-realized" d={path(true)}/><path className="vol-predicted" d={path(false)}/>
      {regime!=='all'?visible.map(row=><g key={row.session}><circle fill="var(--lab-gold)" r="2" cx={x(row)} cy={y(amplitude(row.realized_variance))}/><circle fill="var(--lab-accent)" r="2" cx={x(row)} cy={y(amplitude(row.predictions[method]))}/></g>):null}
      <line className="vol-cursor" x1={x(current)} x2={x(current)} y1="25" y2="205"/><circle className="vol-dot" r="4" cx={x(current)} cy={y(amplitude(current.predictions[method]))}/>
      <text x="58" y="235">{rows[0].session}</text><text x="838" y="235" textAnchor="end">{rows.at(-1)!.session}</text>
    </svg><figcaption><span className="vol-legend-realized">金：事后观测代理</span><span className="vol-legend-predicted">绿：当时预测</span> {regime!=='all'?'市况间断保留空隙，不连接不连续日期。':'鼠标、触屏或下方日期滑块查看同一预测。'}</figcaption></figure>
    <label className="vol-point-control" htmlFor={id}>查看预测日期 <input id={id} aria-label="查看波动预测日期" type="range" min={0} max={visible.length-1} value={Math.min(point,visible.length-1)} onChange={event=>setPoint(Number(event.target.value))}/></label>
    <dl className="vol-point-detail"><div><dt>预测时点</dt><dd>{current.session}</dd></div><div><dt>预测幅度</dt><dd>{volatilityPercent(current.predictions[method],record.annualization)}</dd></div><div><dt>事后代理幅度</dt><dd>{volatilityPercent(current.realized_variance,record.annualization)}</dd></div><div><dt>标签窗口结束</dt><dd>{current.label_end}</dd></div></dl></>:<p className="vol-empty" role="status">该季度与市况没有共同样本。保留空白，请更换季度或市况。</p>}
  </section>;
}

function MetricTable({models,method,onMethod,caption,overall}:{models:Record<string,VolatilityModel>;method:string;onMethod:(method:string)=>void;caption:string;overall:VolatilityRecord['overall']}){
  return <div className="bt-table-scroll"><table className="vol-metrics"><caption>{caption} · 点击方法联动曲线，损失差小于 0 表示优于 EWMA</caption><thead><tr><th scope="col">预测方法</th><th scope="col">QLIKE ↓</th><th scope="col">相对EWMA ↓</th><th scope="col">95%探索性区间</th><th scope="col">方差RMSE / MAE</th><th scope="col">年化幅度RMSE</th><th scope="col">预测/实际均值</th><th scope="col">样本 / 触底</th><th scope="col">总体胜出季度</th></tr></thead><tbody>{Object.entries(models).map(([key,model])=>{const metric=model.metrics,comparison=model.comparison;return <tr key={key} data-selected={method===key}><th scope="row"><button type="button" aria-pressed={method===key} onClick={()=>onMethod(key)}>{model.name}</button></th><td>{metricNumber(metric?.qlike)}</td><td>{metricNumber(comparison?.delta_qlike)}</td><td>{comparison?.ci_low==null?'—':`${metricNumber(comparison.ci_low)} 至 ${metricNumber(comparison.ci_high)}`}</td><td>{metricNumber(metric?.variance_rmse,6)} / {metricNumber(metric?.variance_mae,6)}</td><td>{metric==null?'—':`${(metric.volatility_rmse_ann*100).toFixed(2)}%`}</td><td>{metricNumber(metric?.calibration_ratio,2)}</td><td>{metric?.rows??0} / {metric?.prediction_floor_count??'—'}</td><td>{overall[key].wins_vs_ewma}/{overall[key].folds}</td></tr>;})}</tbody></table></div>;
}

function VolatilityResult({body}:{body:VolatilityEnvelope}){
  const r=body.record,[method,setMethod]=useState(r.overall.dlinear?'dlinear':'ewma'),[quarter,setQuarter]=useState('all'),[regime,setRegime]=useState('all'),id=useId();
  const fold=r.folds.find(item=>item.fold===quarter),group=regime==='all'?null:r.regimes[regime];
  const scope=group?`${group.name} · 全部八季市况指标`:fold?`${fold.fold} · 全部市况季度指标`:'全部八季度 · 全部市况总体指标';
  const models=group?.models||fold?.models||r.overall,main=Object.fromEntries(Object.entries(models).filter(([key])=>!key.startsWith('dlinear_seed_'))),seeds=Object.fromEntries(Object.entries(models).filter(([key])=>key.startsWith('dlinear_seed_')));
  const selected=models[method],comparison=selected.comparison;
  return <div className="volatility-result"><div className="bt-result-heading"><div><span className="bt-eyebrow">{r.instrument} · 未来 {r.horizon} 个市场日 · {r.observations.length} 条冻结预测</span><h3>能提前判断，下一段会有多颠簸吗？</h3><p>涨跌方向暂时放下。比较简单规则、经典模型与 AI 对波动幅度的预测。</p></div><div className="bt-export"><button type="button" className="lab-button lab-secondary" onClick={()=>download(`${r.instrument}-h${r.horizon}-volatility.md`,volatilityReport(body),'text/markdown;charset=utf-8')}><Download size={14}/>导出波动报告</button><button type="button" className="bt-text-button" onClick={()=>download(`${r.run_id}.json`,JSON.stringify(body,null,2),'application/json')}>波动完整 JSON</button></div></div>
    {body.artifact_status==='missing'?<div className="bt-error" role="alert">原始产物缺失 {body.missing_artifacts.length} 项；这里只展示原版本保存的结果快照，当前无法完整复核。<details><summary>查看缺失文件</summary><ul>{body.missing_artifacts.map(name=><li key={name}>{name}</li>)}</ul></details></div>:null}
    <div className="vol-lesson"><div><b>01 · 学什么</b><p>收益平方越大，起伏越强。目标是未来 {r.horizon} 日收益平方的日均值；这是日线波动代理。</p></div><div><b>02 · 怎样比</b><p>用过去训练、此前一年验证、下一季度评估。完整保留 2024–2025 八季。</p></div><div><b>03 · 怎样读</b><p>QLIKE 越低越好，可为负值；相对 EWMA 的差值更容易理解。不同市场不直接排名。</p></div></div>
    <div className="vol-controls"><label htmlFor={`${id}-quarter`}>查看波动季度<select id={`${id}-quarter`} value={quarter} onChange={event=>setQuarter(event.target.value)}><option value="all">全部八季度</option>{r.folds.map(item=><option key={item.fold}>{item.fold}</option>)}</select></label><label htmlFor={`${id}-regime`}>查看历史市况<select id={`${id}-regime`} value={regime} onChange={event=>setRegime(event.target.value)}><option value="all">全部市况</option>{Object.entries(r.regimes).map(([key,value])=><option key={key} value={key}>{value.name} · {value.rows} 条{value.sufficient?'':' · 样本不足'}</option>)}</select></label><label htmlFor={`${id}-method`}>查看波动模型<select id={`${id}-method`} value={method} onChange={event=>setMethod(event.target.value)}>{Object.entries(r.overall).map(([key,value])=><option key={key} value={key}>{value.name}</option>)}</select></label></div>
    <p className="vol-scope">指标范围：{scope}。{group&&fold?`曲线另筛至 ${fold.fold}；表格保持该市况全部八季的已评分指标。`:null}市况只由当时已知的历史波动与趋势划分。</p>
    {group&&!group.sufficient?<p className="vol-caution" role="status">该市况共 {group.rows} 条样本，少于 30 条，结论不稳定；没有样本的指标保留为空。</p>:null}
    <MetricTable models={main} method={method} onMethod={setMethod} caption={scope} overall={r.overall}/>
    {Object.keys(seeds).length?<details className="bt-details vol-seeds"><summary>查看 DLinear 三个固定种子（不按评估成绩挑选）</summary><MetricTable models={seeds} method={method} onMethod={setMethod} caption={scope} overall={r.overall}/></details>:null}
    <div className="vol-interpretation"><h4>{selected.name} · 与简单平滑规则相比</h4><p>{comparison?`QLIKE 差值 ${metricNumber(comparison.delta_qlike)}。${comparison.ci_low==null?'本组未提供可用置信区间。':comparison.ci_high!<0?'本组探索性区间整体低于零；仍需其他时期验证。':comparison.ci_low>0?'本组探索性区间整体高于零，表现弱于 EWMA。':'区间跨越或接触零，没有清晰的优势证据。'}`:'当前市况没有可比较样本。'}</p><p>均值比接近 1 只表示平均收益平方水平接近，并不保证每天都准。{comparison?`区间采用 ${comparison.block} 行块、${comparison.repeats} 次配对重采样。`:null}不将逐比较区间当作多模型确认检验。</p></div>
    <VolatilityCurve key={`${quarter}-${regime}-${method}`} record={r} method={method} quarter={quarter} regime={regime}/>
    {fold?<section className="vol-fold-evidence"><h4>{fold.fold} · 当时能知道什么</h4><div>{(['train','validation','evaluation'] as const).map((key,i)=><p key={key}><b>{['训练','验证','评估'][i]}</b><span>{fold.bounds[key]?.join(' → ')||'见完整记录'} · {fold.counts[key]??'—'} 条</span></p>)}</div><p>跨段标签清除：{Object.entries(fold.purged).map(([key,value])=>`${key} ${value}`).join(' · ')||'见完整记录'}。市况阈值只在本折训练段拟合。</p><details className="bt-details"><summary>本季度阈值与真实训练收据</summary><pre>{JSON.stringify({regime_thresholds:fold.regime_thresholds,training:fold.training},null,2)}</pre></details></section>:null}
    <VolatilityDiagnostics source_record={body} selectedmethod={method}/>
    <details className="bt-details vol-provenance"><summary>口径、完整来源与可复核版本</summary><p>图中幅度 = √（日均收益平方 × {r.annualization}）。5 日标签已为日均值，不额外除以 5。正预测下限 1e-10，所有触底数量保留。HAR 为日线多尺度近似，不等同原版高频 HAR-RV。</p><ul>{r.limitations.map(text=><li key={text}>{text}</li>)}</ul><dl className="bt-hashes"><dt>实验 ID</dt><dd>{r.run_id}</dd><dt>数据 SHA-256</dt><dd>{r.dataset_sha256}</dd><dt>记录 SHA-256</dt><dd>{body.record_sha256}</dd><dt>发布日期</dt><dd>{formatTime(r.created_at)}</dd></dl><p>{Object.keys(r.artifacts).length} 项原始产物已登记；状态：{body.artifact_status==='verified'?'当前文件摘要一致':'原文件有缺失'}。完整 JSON 包含自足数据、逐行预测、全部季度与市况、模型指纹和阶段收据。</p><pre>{JSON.stringify({identity:r.identity,protocol:r.protocol,phase_receipts:r.phase_receipts},null,2)}</pre></details>
  </div>;
}

export function VolatilityPanel(){
  const [runs,setRuns]=useState<VolatilitySummary[]>([]),[market,setMarket]=useState<'ashare'|'btc'>('ashare'),[horizon,setHorizon]=useState<1|5>(1),[selected,setSelected]=useState('');
  const [body,setBody]=useState<VolatilityEnvelope|null>(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[catalogError,setCatalogError]=useState(''),[reload,setReload]=useState(0),[retry,setRetry]=useState(0),generation=useRef(0),id=useId();
  const selection=useRef({market,horizon});selection.current={market,horizon};
  const matching=runs.filter(run=>run.market===market&&run.horizon===horizon),older=Boolean(selected&&matching[0]?.run_id!==selected);
  useEffect(()=>{const c=new AbortController();setLoading(true);setCatalogError('');void volatilityApi.runs(c.signal).then(next=>{if(c.signal.aborted)return;setRuns(next);setSelected(previous=>next.some(run=>run.run_id===previous)?previous:next.find(run=>run.market===selection.current.market&&run.horizon===selection.current.horizon)?.run_id||'');}).catch(e=>{if(!c.signal.aborted)setCatalogError(e instanceof Error?e.message:'波动目录读取失败。');}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[reload]);
  useEffect(()=>{if(!selected){setBody(null);setBusy(false);setError('');return;}const c=new AbortController(),token=++generation.current;setBody(null);setBusy(true);setError('');void volatilityApi.reopen(selected,c.signal).then(next=>{if(!c.signal.aborted&&generation.current===token)setBody(next);}).catch(e=>{if(!c.signal.aborted&&generation.current===token)setError(e instanceof Error?e.message:'波动记录读取失败。');}).finally(()=>{if(!c.signal.aborted&&generation.current===token)setBusy(false);});return()=>{c.abort();generation.current++;};},[selected,retry]);
  function choose(nextMarket:typeof market,nextHorizon:typeof horizon){generation.current++;setBody(null);setMarket(nextMarket);setHorizon(nextHorizon);setSelected(runs.find(run=>run.market===nextMarket&&run.horizon===nextHorizon)?.run_id||'');}
  function version(value:string){generation.current++;setBody(null);setSelected(value);}
  return <section className="public-backtest-panel volatility-panel" aria-labelledby="volatility-title"><div className="bt-heading"><div><span className="bt-eyebrow"><Activity size={14}/>波动预测 · 市况稳定性</span><h2 id="volatility-title">先学风险幅度，再谈收益方向。</h2><p>同一套协议，观察 A 股与 BTC 在不同阶段的起伏。只展示已完成的真实离线结果。</p></div><button type="button" className="bt-text-button" disabled={loading} onClick={()=>setReload(value=>value+1)}><RefreshCw size={14}/>重新加载波动实验</button></div>
    <div className="vol-selection"><div role="group" aria-label="波动实验市场">{(['ashare','btc'] as const).map(value=><button type="button" key={value} aria-pressed={market===value} disabled={market===value} onClick={()=>choose(value,horizon)}>{marketName(value)}</button>)}</div><div role="group" aria-label="波动预测期限">{([1,5] as const).map(value=><button type="button" key={value} aria-pressed={horizon===value} disabled={horizon===value} onClick={()=>choose(market,value)}>未来 {value} 个市场日</button>)}</div></div>
    {loading?<p role="status">正在读取波动实验目录…</p>:null}{catalogError?<div className="bt-error" role="alert"><p>{catalogError}</p>{runs.length?<p>目前保留上次成功读取的目录，尚未确认最新发布状态。</p>:null}</div>:null}
    {!loading&&!selected&&!catalogError?<p className="vol-empty" role="status">尚无{marketName(market)}未来 {horizon} 日的已发布波动实验。完成离线评分后才显示真实结果。</p>:null}
    {matching.length?<div className="vol-version"><label htmlFor={`${id}-version`}>波动结果版本<select id={`${id}-version`} value={selected} onChange={event=>version(event.target.value)}>{matching.map((run,i)=><option key={run.run_id} value={run.run_id}>{i===0?'最新发布':'历史版本'} · {formatTime(run.created_at)} · {run.run_id.slice(-8)}</option>)}</select></label><span className={older?'vol-old-version':''}>{older?'正在查看历史版本，未替换成最新成绩':'当前目录最新版本'} · {matching.find(run=>run.run_id===selected)?.rows} 条预测</span>{older?<button type="button" className="bt-text-button" onClick={()=>version(matching[0].run_id)}>回到最新波动版本</button>:null}</div>:null}
    {busy?<p role="status">正在校验波动结果、原始模型与数据版本…</p>:null}{error?<div className="bt-error" role="alert"><p>{error}</p><button type="button" className="bt-text-button" onClick={()=>setRetry(value=>value+1)}>重试读取波动记录</button></div>:null}
    <div aria-busy={busy}>{body&&body.record.run_id===selected?<VolatilityResult key={selected} body={body}/>:null}</div><p className="vol-boundary">网页只读已完成的离线实验，不启动训练。这是历史研究与风险幅度学习，不是买卖建议；现有日线不支持高频实现波动率。</p>
  </section>;
}

