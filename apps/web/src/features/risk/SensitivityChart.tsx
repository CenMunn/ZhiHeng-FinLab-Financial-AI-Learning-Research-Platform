import { useId, useState } from 'react';
import { MousePointer2 } from 'lucide-react';
import type { CalculationResult } from './api';
import { money } from './format';

export function SensitivityChart({result,onPick}:{result?:CalculationResult;onPick:(day:string)=>void}) {
  const [hovered,setHovered]=useState<string>();
  const gradient=useId().replaceAll(':','');
  const width=760,height=238,left=66,right=22,top=24,bottom=32;
  const points=result?.sensitivity_curve || [];
  const actualMax=Math.max(0,...points.map(point=>Number(point.occupancy_change)));
  const max=actualMax || 1,unit=actualMax>=10000?10000:1;
  const x=(day:number)=>left+day/90*(width-left-right);
  const y=(amount:number)=>height-bottom-amount/max*(height-top-bottom);
  const path=points.map(point=>`${x(Number(point.delay_days))},${y(Number(point.occupancy_change))}`).join(' ');
  const highlight=points.find(point=>point.delay_days===(hovered || result?.assumptions.delay_days));
  const tooltipX=highlight?Math.min(width-192,Math.max(left,x(Number(highlight.delay_days))-30)):0;
  const tooltipY=highlight?Math.max(6,y(Number(highlight.occupancy_change))-66):0;
  return <div className={`chart-wrap ${result?'':'is-empty'}`}>
    <div className="chart-label"><span>占款 / {unit===10000?'万元':'元'}</span><span>新增回款延迟</span></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label="回款延迟天数与稳态资金占用曲线">
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#72d4b0" stopOpacity=".18"/><stop offset="100%" stopColor="#72d4b0" stopOpacity=".015"/></linearGradient></defs>
      {[0,.25,.5,.75,1].map(fraction=><g key={fraction}><line x1={left} x2={width-right} y1={y(max*fraction)} y2={y(max*fraction)} className="chart-grid"/>
        <text x={left-12} y={y(max*fraction)+4} textAnchor="end" className="chart-axis">{result?(max*fraction/unit).toLocaleString('zh-CN',{maximumFractionDigits:actualMax<10?2:0}):'—'}</text></g>)}
      {[0,15,30,45,60,75,90].map(day=><g key={day}><line x1={x(day)} x2={x(day)} y1={top} y2={height-bottom} className="chart-grid vertical"/><text x={x(day)} y={height-12} textAnchor="middle" className="chart-axis">{day}</text></g>)}
      {points.length>0 && <><polygon points={`${x(0)},${y(0)} ${path} ${x(90)},${y(0)}`} fill={`url(#${gradient})`}/>
        <polyline points={path} className="chart-line"/>
        {highlight && <line x1={x(Number(highlight.delay_days))} x2={x(Number(highlight.delay_days))} y1={top} y2={height-bottom} className="chart-crosshair"/>}
        {points.map(point=>{
          const selected=point.delay_days===highlight?.delay_days;
          return <g key={point.delay_days} role="button" tabIndex={0} className={`chart-point ${selected?'selected-point':''}`} aria-label={`将回款延迟设为${point.delay_days}天`}
            onMouseEnter={()=>setHovered(point.delay_days)} onMouseLeave={()=>setHovered(undefined)} onFocus={()=>setHovered(point.delay_days)} onBlur={()=>setHovered(undefined)}
            onClick={()=>onPick(point.delay_days)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onPick(point.delay_days);}}}>
            <circle cx={x(Number(point.delay_days))} cy={y(Number(point.occupancy_change))} r="16" fill="transparent" className="point-hit-area"/>
            {selected && <circle cx={x(Number(point.delay_days))} cy={y(Number(point.occupancy_change))} r="11" className="point-halo"/>}
            <circle cx={x(Number(point.delay_days))} cy={y(Number(point.occupancy_change))} r={selected?5:3.5} className="point-dot"/>
            <title>{point.delay_days}天 · 占款{point.occupancy_change}元</title></g>;
        })}
        {highlight && <g className="chart-tooltip" transform={`translate(${tooltipX},${tooltipY})`} pointerEvents="none"><rect width="178" height="52" rx="7"/><text x="12" y="20">新增延迟 {highlight.delay_days}天</text><text x="12" y="39" className="tooltip-amount">{money(highlight.occupancy_change)}元</text></g>}
      </>}
    </svg>
    {highlight && <div className="chart-mobile-reading"><span>{highlight.delay_days}天延迟</span><strong>{money(highlight.occupancy_change)}元</strong></div>}
    {!result && <div className="chart-empty"><span className="empty-chart-symbol"><MousePointer2 size={22}/></span><h3>从一个回款假设开始</h3><p>填写右侧赊销比例，计算不同延迟下的资金占用。</p></div>}
    <div className="chart-caption"><span><MousePointer2 size={12}/>悬停查看金额，点击节点设置延迟</span><span>延迟天数 / 天</span></div>
  </div>;
}
