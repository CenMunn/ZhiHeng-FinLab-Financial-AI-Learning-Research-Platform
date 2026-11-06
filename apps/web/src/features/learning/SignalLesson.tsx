import {useId,useRef,useState} from 'react';
import {gsap} from 'gsap';
import {useGSAP} from '@gsap/react';
import {ArrowUpRight,SlidersHorizontal} from 'lucide-react';
import {LESSON_SERIES,lessonSignal,movingAverage} from './signal-lesson';

gsap.registerPlugin(useGSAP);
const SIGNAL_TEXT={warmup:'等待完整窗口',equal:'价格等于均线',above:'价格在均线上方',below:'价格在均线下方'};

export function SignalLesson(){
  const [market,setMarket]=useState<'ashare'|'btc'>('ashare');
  const [windowSize,setWindowSize]=useState(8),[position,setPosition]=useState(31);
  const root=useRef<HTMLDivElement>(null),id=useId();
  const values=LESSON_SERIES[market],averages=movingAverage(values,windowSize),average=averages[position];
  const signal=lessonSignal(values[position],average);
  const x=(index:number)=>32+index/(values.length-1)*636;
  const low=Math.min(...values)-6,high=Math.max(...values)+6;
  const y=(value:number)=>190-(value-low)/(high-low)*155;
  const line=values.map((value,index)=>`${index?'L':'M'}${x(index).toFixed(2)},${y(value).toFixed(2)}`).join(' ');
  const averageLine=averages.map((value,index)=>value===null?'':`${index===windowSize-1?'M':'L'}${x(index).toFixed(2)},${y(value).toFixed(2)}`).join(' ');
  useGSAP(()=>{
    const media=gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)',()=>{
      gsap.timeline({defaults:{duration:.24,ease:'power2.out'}}).fromTo('[data-lesson-plot]',{x:6,opacity:.7},{x:0,opacity:1,clearProps:'transform,opacity'});
    },root);
    return()=>media.revert();
  },{scope:root,dependencies:[market],revertOnUpdate:true});
  return <div className="signal-lesson" ref={root}>
    <div className="lesson-heading"><div><h2>让信号变得看得见</h2><p>调一调均线，观察信号为什么改变。</p></div>
      <div className="market-switch" role="group" aria-label="教学样例市场"><button type="button" aria-pressed={market==='ashare'} onClick={()=>setMarket('ashare')}>A 股</button><button type="button" aria-pressed={market==='btc'} onClick={()=>setMarket('btc')}>BTC</button></div>
    </div>
    <div className="lesson-legend"><span><i className="price-key"/>合成价格</span><span><i className="average-key"/>{windowSize} 期均线</span><span>指数起点 = 100</span></div>
    <figure className="lesson-figure" aria-label={`${market==='ashare'?'A 股':'BTC'}合成序列与移动平均线`}>
      <svg data-lesson-plot viewBox="0 0 700 230" onPointerMove={event=>{if(event.pointerType!=='mouse')return;const box=event.currentTarget.getBoundingClientRect();const plotX=(event.clientX-box.left)/box.width*700;setPosition(Math.max(0,Math.min(values.length-1,Math.round((plotX-32)/636*(values.length-1)))));}} aria-hidden="true">
        {[0,1,2,3].map(n=><g key={n}><line className="lesson-grid" x1="32" x2="668" y1={35+n*52} y2={35+n*52}/><text className="lesson-axis" x="0" y={39+n*52}>{Math.round(high-n/3*(high-low))}</text></g>)}
        <path className="lesson-price" d={line}/><path className="lesson-average" d={averageLine}/><line className="lesson-crosshair" x1={x(position)} x2={x(position)} y1="25" y2="197"/><circle className="lesson-point" cx={x(position)} cy={y(values[position])} r="4.5"/>
        <text className="lesson-axis" x="32" y="223">第 1 期</text><text className="lesson-axis" x="624" y="223">第 48 期</text>
      </svg><figcaption>合成教学数据，非历史行情，不构成回测结果。</figcaption>
    </figure>
    <div className="lesson-controls"><label htmlFor={`${id}-window`}><SlidersHorizontal size={15}/>均线窗口 <output>{windowSize} 期</output></label><input id={`${id}-window`} type="range" min="4" max="16" value={windowSize} onChange={event=>setWindowSize(Number(event.target.value))}/></div>
    <div className="lesson-inspector"><div><label htmlFor={`${id}-point`}>观察位置 <output>第 {position+1} 期</output></label><input id={`${id}-point`} type="range" min="0" max="47" value={position} onChange={event=>setPosition(Number(event.target.value))}/></div><dl><div><dt>价格指数</dt><dd>{values[position].toFixed(2)}</dd></div><div><dt>移动平均</dt><dd>{average===null?'待形成':average.toFixed(2)}</dd></div><div className="signal-reading"><dt>当前观察</dt><dd>{SIGNAL_TEXT[signal]}</dd></div></dl></div>
    <details className="lesson-formula"><summary>这条均线怎么算？<ArrowUpRight size={14}/></summary><p>MA(t, n) = 最近 n 期价格之和 ÷ n。只使用当前及之前的观测；不足 n 期不产生信号。位于均线上方只是规则观察，交易还需定义下一期成交、仓位与成本。</p></details>
  </div>;
}
