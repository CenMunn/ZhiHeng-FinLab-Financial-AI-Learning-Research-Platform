import {useId,useState} from 'react';
import {type ForecastRecord,errorBps,ratio} from './forecast-api';
import {money} from './backtest-api';

export function ForecastPlot({record:r,method}:{record:ForecastRecord;method:string}){
  const [mode,setMode]=useState<'forecast'|'policy'>('forecast'),[position,setPosition]=useState(0),id=useId();
  const model=r.models[method],policy=model.policy!,forecast=mode==='forecast',n=forecast?r.observations.length:policy.curve.length,index=Math.min(position,n-1);
  const dates=forecast?r.observations.map(p=>p.signal_session):policy.curve.map(p=>p.session);
  const a=forecast?r.observations.map(p=>p.actual_return*10000):r.benchmark.curve.map(p=>Number(p.wealth));
  const b=forecast?r.observations.map(p=>p.predictions[method]*10000):policy.curve.map(p=>Number(p.wealth));
  const minimum=Math.min(forecast?0:1,...a,...b),maximum=Math.max(forecast?0:1,...a,...b),padding=(maximum-minimum||1)*.08,low=minimum-padding,high=maximum+padding;
  const x=(i:number)=>52+i/(n-1)*800,y=(v:number)=>235-(v-low)/(high-low)*210;
  return <div className="forecast-plot"><div className="forecast-plot-heading"><div role="group" aria-label="预测结果视图"><button type="button" aria-pressed={forecast} onClick={()=>setMode('forecast')}>预测误差</button><button type="button" aria-pressed={!forecast} onClick={()=>setMode('policy')}>仓位回放</button></div><span>{model.name} · {forecast?'收益单位 bp':'账户净值起点 = 1'}</span></div>
    <div className="bt-plot-legend"><span><i className="bt-series-0"/>{forecast?'实际窗口收益':'同区间买入持有'}</span><span><i className="bt-series-1"/>{forecast?'冻结预测':'模型仓位策略'}</span></div>
    <figure className="bt-figure"><svg viewBox="0 0 900 270" aria-hidden="true" onPointerMove={e=>{if(e.pointerType!=='mouse')return;const box=e.currentTarget.getBoundingClientRect();setPosition(Math.max(0,Math.min(n-1,Math.round(((e.clientX-box.left)/box.width*900-52)/800*(n-1)))));}}>
      {[0,1,2,3].map(i=>{const v=low+(high-low)*i/3;return <g key={i}><line className="bt-grid" x1="52" x2="852" y1={y(v)} y2={y(v)}/><text x="0" y={y(v)+4}>{forecast?v.toFixed(0):v.toFixed(2)}</text></g>;})}
      <path className="bt-line bt-series-0" style={{strokeWidth:1.4,opacity:.65}} d={a.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}/>
      <path className="bt-line bt-series-1" style={{strokeWidth:2}} d={b.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}/>
      <line className="bt-crosshair" x1={x(index)} x2={x(index)} y1="20" y2="235"/><circle className="bt-dot" cx={x(index)} cy={y(b[index])} r="4"/>
      <text x="52" y="263">{dates[0]}</text><text x="852" y="263" textAnchor="end">{dates[n-1]}</text>
    </svg><figcaption>{forecast?'实际值来自后续可执行持有窗口，决策时不可知；鼠标或滑块检查每次冻结预测。':'预测大于0持仓，否则现金；固定阈值、教学费用及最后可评分退出日开盘目标清仓。'}</figcaption></figure>
    <div className="bt-replay"><label htmlFor={`${id}-position`}>{forecast?'预测观察位置':'仓位观察位置'}<output>{dates[index]}</output></label><input id={`${id}-position`} type="range" min="0" max={n-1} aria-valuetext={dates[index]} value={index} onChange={e=>setPosition(Number(e.target.value))}/>
      {forecast?<dl><div><dt>预测 / 后续实际收益</dt><dd>{errorBps(b[index]/10000)} / {errorBps(a[index]/10000)}</dd></div><div><dt>可交易窗口</dt><dd>{r.observations[index].entry_session} → {r.observations[index].exit_session}</dd></div><div><dt>固定仓位规则</dt><dd>{b[index]>0?'持仓':'现金'}</dd></div><div><dt>决策时点（UTC）</dt><dd>{r.observations[index].decision_at}</dd></div></dl>:<dl><div><dt>账户权益（{r.currency}）</dt><dd>{money(policy.curve[index].equity)}</dd></div><div><dt>现金 / 持仓数量</dt><dd>{money(policy.curve[index].cash)} / {policy.curve[index].quantity}</dd></div><div><dt>当日回撤</dt><dd>{ratio(Number(policy.curve[index].drawdown))}</dd></div><div><dt>本日成交前的信号日</dt><dd>{policy.curve[index].signal_session}</dd></div></dl>}
    </div>
  </div>;
}
