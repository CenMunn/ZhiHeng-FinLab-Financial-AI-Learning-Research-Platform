import {useEffect,useRef,useState} from 'react';
import {Download,FlaskConical,RefreshCw} from 'lucide-react';
import {forecastApi,type ForecastSummary,type ForecastEnvelope,FORECAST_METHODS,errorBps,ratio,forecastReport} from './forecast-api';
import {ForecastPlot} from './ForecastPlot';
import {money,decimalDisplay} from './backtest-api';
import './public-backtest.css';
import './forecast.css';

function download(name:string,body:string,type:string){const url=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function LossTrace({rows,best}:{rows:{epoch:number;train_mse_standardized:number;validation_mse_standardized:number}[];best:number}){
  const max=Math.max(...rows.flatMap(r=>[r.train_mse_standardized,r.validation_mse_standardized]))*1.1;
  const x=(i:number)=>40+i/(rows.length-1)*620,y=(v:number)=>145-v/max*120;
  return <figure className="forecast-loss"><svg viewBox="0 0 700 175" role="img" aria-label="DLinear种子42真实训练和验证损失曲线">
    <path className="bt-line bt-series-1" style={{strokeWidth:2}} d={rows.map((r,i)=>`${i?'L':'M'}${x(i)},${y(r.train_mse_standardized)}`).join(' ')}/><path className="bt-line bt-series-2" style={{strokeWidth:2}} d={rows.map((r,i)=>`${i?'L':'M'}${x(i)},${y(r.validation_mse_standardized)}`).join(' ')}/><line className="bt-crosshair" x1={x(best-1)} x2={x(best-1)} y1="10" y2="145"/><text x="40" y="165">第1轮</text><text x="560" y="165">第{rows.length}轮</text><text x="40" y="12">规范化MSE：0—{max.toFixed(2)}</text>
  </svg><figcaption>种子42：绿为训练损失、金为验证损失；虚线为验证选择的第{best}轮，非按评估成绩选择。</figcaption></figure>;
}
function ModelResult({body}:{body:ForecastEnvelope}){
  const r=body.record,[method,setMethod]=useState('lightgbm'),model=r.models[method],m=model.evaluation,policy=model.policy!,ci=model.mse_difference_interval;
  const seeds=['dlinear_42','dlinear_43','dlinear_44'];
  return <div className="forecast-result"><div className="bt-result-heading"><div><span className="bt-eyebrow">已完成 · {r.instrument} · {r.evaluation.rows} 次冻结预测</span><h3>模型更复杂，证据也要更充分。</h3><p>信号：{r.evaluation.first_signal} — {r.evaluation.last_signal} · 实际可交易：{r.evaluation.first_entry} — {r.evaluation.last_exit}</p></div><div className="bt-export"><button type="button" className="lab-button lab-secondary" onClick={()=>download(`${r.instrument}-forecast-report.md`,forecastReport(r),'text/markdown;charset=utf-8')}><Download size={14}/>导出预测报告</button><button type="button" className="bt-text-button" onClick={()=>download(`${r.run_id}.json`,JSON.stringify(body,null,2),'application/json')}>预测完整 JSON</button></div></div>
    {body.artifact_status!=='verified'?<p role="alert" className="bt-error">部分原模型产物缺失，已保存的结果快照仍可读取。缺失：{body.missing_artifacts.join('、')}</p>:null}
    <div className="forecast-protocol"><span><b>2018–2021</b>训练 {r.counts.train}</span><span><b>2022–2023</b>验证 {r.counts.validation}</span><span><b>2024–2025</b>评估 {r.counts.evaluation}</span><p>同一 60 期已知收益输入 · 跨段标签清除 · 训练期拟合标准化 · 验证早停 · 评估不调参</p></div>
    <div className="bt-table-scroll"><table className="forecast-metrics"><caption>预测任务：下一可执行开盘到再下一开盘的税前总收益；1 bp = 0.01%</caption><thead><tr><th scope="col">方法</th><th scope="col">RMSE ↓</th><th scope="col">MAE ↓</th><th scope="col">方向命中</th><th scope="col">MSE 较零基线改善</th><th scope="col">仓位净收益</th><th scope="col">最大回撤</th></tr></thead><tbody>{FORECAST_METHODS.map(key=>{const model=r.models[key],m=model.evaluation;return <tr key={key} data-selected={method===key}><th scope="row"><button type="button" aria-pressed={method===key} onClick={()=>setMethod(key)}>{model.name}</button></th><td>{errorBps(m.rmse)}</td><td>{errorBps(m.mae)}</td><td>{ratio(m.direction_accuracy)}</td><td data-negative={(m.mse_skill_vs_zero||0)<0}>{ratio(m.mse_skill_vs_zero)}</td><td>{ratio(Number(model.policy!.metrics.return))}</td><td>{ratio(Number(model.policy!.metrics.max_drawdown))}</td></tr>;})}</tbody></table></div>
    <p className="bt-note">MSE 改善为负，表示误差大于零收益基线。方向命中只评价实际非零的日子，零预测为中性。仓位收益另扣教学费用，含期末估值及 A 股税前分红应收，不等于预测准确率。</p>
    <ForecastPlot key={method} record={r} method={method}/>
    <div className="forecast-diagnostics"><section><h4>先看误差，再看交易。</h4><p>{model.name}：验证 RMSE {errorBps(model.validation.rmse)}，评估 RMSE {errorBps(m.rmse)}。时序相关 {m.temporal_correlation===null?'未定义':m.temporal_correlation.toFixed(3)}。</p><p>策略成本 {money(policy.metrics.costs)} {r.currency} · 双边换手 {decimalDisplay(policy.metrics.turnover)} 倍 · 成交 {policy.metrics.trade_count} 次。</p></section><section><h4>改善有多确定？</h4><p>MSE 差（模型减零基线）的 95% 移动块区间：[{ci.low.toExponential(3)}, {ci.high.toExponential(3)}]，收益²单位。</p><p>块长 {ci.block_length}、{ci.resamples} 次配对重采样。区间跨 0 时，不能明确区分误差；这也不是收益显著性检验。</p></section></div>
    <details className="bt-details"><summary>年度误差、三个种子与仓位日志</summary><div className="bt-table-scroll"><table><thead><tr><th>年份</th><th>次数</th><th>RMSE</th><th>MAE</th><th>方向命中</th></tr></thead><tbody>{model.annual.map(y=><tr key={y.year}><th>{y.year}</th><td>{y.rows}</td><td>{errorBps(y.rmse)}</td><td>{errorBps(y.mae)}</td><td>{ratio(y.direction_accuracy)}</td></tr>)}</tbody></table></div><p>DLinear 集成是以下三个种子的预测均值，未挑选评估最好种子：</p><ul>{seeds.map(key=><li key={key}>{r.models[key].name}：RMSE {errorBps(r.models[key].evaluation.rmse)}</li>)}</ul><p>同区间买入持有净收益 {ratio(Number(r.benchmark.metrics.return))}；模型期末持仓 {policy.metrics.final_quantity}，分红应收 {policy.metrics.dividend_receivable} {r.currency}。完整逐日、成交和拒单日志在 JSON。</p><pre>{JSON.stringify(policy.trades.slice(0,6),null,2)}</pre></details>
    <details className="bt-details forecast-training"><summary>真实训练证据与模型结构</summary><p>LightGBM：CPU 2 线程，验证选择第 {r.training.models.lightgbm.best_iteration} 棵树。DLinear：122 个参数，25 点移动均值分解，趋势/残差两个线性头；GPU FP32。</p><div className="bt-table-scroll"><table><thead><tr><th>种子</th><th>最佳轮</th><th>实际轮</th><th>参数更新</th><th>训练秒数</th></tr></thead><tbody>{seeds.map(key=>{const t=r.training.models[key];return <tr key={key}><th>{key}</th><td>{t.best_epoch}</td><td>{t.epochs}</td><td>{t.updates}</td><td>{t.elapsed_seconds.toFixed(2)}</td></tr>;})}</tbody></table></div><p>{r.training.models.dlinear_42.device}；训练代码记录未读取评估标签：{r.training.evaluation_labels_read?'否':'是'}。三个种子的完整训练/验证损失曲线与权重指纹在 JSON。</p><LossTrace rows={r.training.models.dlinear_42.history!} best={r.training.models.dlinear_42.best_epoch!}/><details><summary>查看种子42逐轮损失与固定超参数</summary><pre>{JSON.stringify({hyperparameters:r.config,history:r.training.models.dlinear_42.history},null,2)}</pre></details><p>DLinear 是原结构的收益任务适配，不是论文基准的原样复现。</p></details>
    <details className="bt-details"><summary>来源、版本与实验限制</summary><ul>{r.limitations.map(x=><li key={x}>{x}</li>)}</ul><dl className="bt-hashes"><dt>行情 SHA-256</dt><dd>{r.dataset_sha256}</dd><dt>准备 / 训练 / 预测 SHA-256</dt><dd>{r.preparation_sha256}<br/>{r.training_sha256}<br/>{r.prediction_sha256}</dd><dt>记录 SHA-256</dt><dd>{body.record_sha256}</dd><dt>运行 ID</dt><dd>{r.run_id}</dd><dt>来源</dt><dd>{r.dataset.snapshot.source_uri}<br/>{r.dataset.snapshot.calendar_source}</dd></dl><pre>{JSON.stringify({environment:r.environment,scaler:r.training.scaler,purged:r.purged,artifacts:r.artifacts,code:r.code_sources},null,2)}</pre></details>
  </div>;
}

export function ForecastPanel(){
  const [runs,setRuns]=useState<ForecastSummary[]>([]),[selected,setSelected]=useState(''),[body,setBody]=useState<ForecastEnvelope|null>(null),[error,setError]=useState(''),[catalogError,setCatalogError]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[reload,setReload]=useState(0),[reopen,setReopen]=useState(0);
  const generation=useRef(0);
  const latest=runs.filter((run,index)=>runs.findIndex(other=>other.market===run.market)===index);
  const latestIds=new Set(latest.map(run=>run.run_id)),older=runs.filter(run=>!latestIds.has(run.run_id));
  function runCard(run:ForecastSummary){return <button type="button" key={run.run_id} aria-pressed={selected===run.run_id} onClick={()=>{if(selected!==run.run_id){generation.current++;setBody(null);setSelected(run.run_id);}}}><b>{run.market==='ashare'?'A 股 · 茅台':'BTC · USDT'}</b><span>{run.evaluation.rows} 次评估 · {new Date(run.created_at).toLocaleString('zh-CN',{hour12:false})}</span><small>预测版本 {run.prediction_sha256.slice(0,10)}</small></button>;}

  useEffect(()=>{
    const c=new AbortController();setLoading(true);setCatalogError('');
    void forecastApi.runs(c.signal).then(next=>{if(c.signal.aborted)return;setRuns(next);setSelected(old=>next.some(x=>x.run_id===old)?old:next.find(x=>x.market==='ashare')?.run_id||next[0]?.run_id||'');}).catch(e=>{if(!c.signal.aborted)setCatalogError(e instanceof Error?e.message:'离线目录读取失败。');}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  },[reload]);
  useEffect(()=>{
    if(!selected){setBody(null);setBusy(false);setError('');return;}const c=new AbortController(),token=++generation.current;setBusy(true);setError('');setBody(null);
    void forecastApi.reopen(selected,c.signal).then(next=>{if(!c.signal.aborted&&token===generation.current)setBody(next);}).catch(e=>{if(!c.signal.aborted&&token===generation.current)setError(e instanceof Error?e.message:'实验读取失败。');}).finally(()=>{if(!c.signal.aborted&&token===generation.current)setBusy(false);});
    return()=>{c.abort();generation.current++;};
  },[selected,reopen]);
  return <section className="public-backtest-panel forecast-panel" aria-labelledby="forecast-title"><div className="bt-heading"><div><span className="bt-eyebrow"><FlaskConical size={14}/>真实模型 · 离线训练记录</span><h2 id="forecast-title">从简单基线，走到模型。</h2><p>同样的数据、同样的预测目标。先比较误差，再检查交易能否承受成本。</p></div><button type="button" className="bt-text-button" onClick={()=>setReload(n=>n+1)}><RefreshCw size={14}/>重新加载预测实验</button></div>
    {loading?<p role="status">正在读取已发布的离线实验…</p>:null}
    {catalogError?<div role="alert" className="bt-error">{catalogError}</div>:null}
    {!loading&&!runs.length&&!catalogError?<p className="bt-empty">尚无已发布预测实验。完成离线训练与独立评分后，真实结果会在这里显示。</p>:null}
    <div className="forecast-runs" role="group" aria-label="预测实验市场">{latest.map(runCard)}</div>
    {older.length?<details className="bt-details forecast-history"><summary>以前发布的模型版本（{older.length}）</summary><div className="forecast-runs" role="group" aria-label="以前的预测实验">{older.map(runCard)}</div></details>:null}
    {busy?<p role="status">正在校验并读取模型、预测和来源记录…</p>:null}
    {error?<div role="alert" className="bt-error"><p>{error}</p><button type="button" className="bt-text-button" onClick={()=>setReopen(n=>n+1)}>重试读取预测记录</button></div>:null}
    <div aria-busy={busy} aria-live="polite">{body?<ModelResult key={body.record.run_id} body={body}/>:null}</div>
    <p className="forecast-boundary">这里展示已完成的离线运行，不在网页请求中启动训练。一步收益预测已实现；波动预测、滚动再训练和预训练模型将分别开展。FinQA 证据排序结果独立保留。</p>
  </section>;
}
