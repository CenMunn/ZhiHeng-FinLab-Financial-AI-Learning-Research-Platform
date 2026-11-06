import {useId,useRef,useState,type KeyboardEvent} from 'react';
import {Check,Download,FileText,Table2,ShieldCheck} from 'lucide-react';
import {gsap} from 'gsap';
import {useGSAP} from '@gsap/react';
import type {FoundationRecord} from './foundation-api';

gsap.registerPlugin(useGSAP);
const markets={ashare:'A 股',btc:'BTC'};
const splitNames:Record<string,string>={train:'训练段',validation:'验证段',test:'测试段'};
const tabs=[{key:'summary',label:'结果概览',icon:FileText},{key:'features',label:'指标明细',icon:Table2},{key:'sources',label:'来源与口径',icon:ShieldCheck}] as const;
type Tab=typeof tabs[number]['key'];
function display(value:string|null){return value===null?'未形成':Number(value).toPrecision(6);}

export function FoundationResult({record,onExport}:{record:FoundationRecord;onExport:()=>void}){
  const result=record.result;
  const [tab,setTab]=useState<Tab>('summary');const root=useRef<HTMLElement>(null),buttons=useRef<(HTMLButtonElement|null)[]>([]),id=useId();
  useGSAP(()=>{
    const media=gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)',()=>{gsap.fromTo('.foundation-tab-content',{opacity:.84,y:4},{opacity:1,y:0,duration:.18,ease:'power2.out',clearProps:'transform,opacity'});},root);
    return()=>media.revert();
  },{scope:root,dependencies:[tab],revertOnUpdate:true});
  function navigate(event:KeyboardEvent<HTMLButtonElement>,index:number){
    const next=event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:event.key==='Home'?0:event.key==='End'?tabs.length-1:null;
    if(next===null)return;event.preventDefault();setTab(tabs[next].key);buttons.current[next]?.focus();
  }
  return <section className="foundation-result" aria-label="已保存的管线检查结果" ref={root}>
    <div className="foundation-result-heading"><h3><Check size={18}/>{markets[result.market]} 检查记录已保存</h3><button type="button" className="lab-button lab-secondary" onClick={onExport}><Download size={15}/>导出 JSON 记录</button></div>
    <div className="foundation-result-meta"><span>{result.engine_version}</span><code title={result.input_hash}>{result.input_hash.slice(0,12)}</code><span>合成日线管线检查</span></div>
    <div className="foundation-result-tabs" role="tablist" aria-label="检查结果内容">{tabs.map(({key,label,icon:Icon},index)=><button key={key} type="button" ref={element=>{buttons.current[index]=element;}} role="tab" id={`${id}-${key}-tab`} aria-controls={`${id}-${key}-panel`} aria-selected={tab===key} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={event=>navigate(event,index)}><Icon size={15}/>{label}</button>)}</div>
    {tabs.filter(item=>item.key!==tab).map(item=><div key={item.key} role="tabpanel" id={`${id}-${item.key}-panel`} aria-labelledby={`${id}-${item.key}-tab`} hidden/>)}
    <div className="foundation-tab-content" role="tabpanel" tabIndex={0} id={`${id}-${tab}-panel`} aria-labelledby={`${id}-${tab}-tab`}>
      {tab==='summary'?<><dl className="foundation-quality-strip"><div><dt>纳入观测</dt><dd>{result.quality.eligible_rows}<small> / {result.quality.total_rows}</small></dd></div><div><dt>完整指标</dt><dd>{result.quality.complete_feature_rows}<small> 条</small></dd></div><div><dt>截止时间外</dt><dd>{result.quality.excluded_as_of}<small> 条</small></dd></div><div><dt>停牌</dt><dd>{result.quality.halted_rows}<small> 条</small></dd></div></dl>
        <div className="foundation-table-scroll" tabIndex={0} role="region" aria-label="时间划分表"><table><thead><tr><th scope="col">时间段</th><th scope="col">样本</th><th scope="col">保留标签</th><th scope="col">清除/不可用</th><th scope="col">范围</th></tr></thead><tbody>{result.splits.map(split=><tr key={split.name}><th scope="row">{splitNames[split.name]}</th><td>{split.rows}</td><td>{split.label_count}</td><td>{split.purged_count}</td><td>{split.start} 至 {split.end}</td></tr>)}</tbody></table></div>
        <p className="foundation-fit-note">标准化只拟合训练段：{result.scaler.fit_start} 至 {result.scaler.fit_end}，{result.scaler.fit_count} 条有效收益。均线 {result.config.window} 期，种子 {result.config.seed}。</p>
        <div className="foundation-cost-summary"><span>假设成交额 {result.cost_example.notional} {result.cost_example.currency}</span><div><span>买入费用</span><b>{result.cost_example.buy.total}<small> {result.cost_example.currency}</small></b></div><div><span>卖出费用</span><b>{result.cost_example.sell.total}<small> {result.cost_example.currency}</small></b></div></div><p className="foundation-fit-note">费用包括教学滑点，不代表真实账户费率或可实现成交。</p>
      </>:null}
      {tab==='features'?<><p className="foundation-fit-note">只使用当时已知的历史观测；窗口不足显示“未形成”。数值为格式化读数，完整精度保留在 JSON 记录中。</p><div className="foundation-table-scroll" tabIndex={0} role="region" aria-label="历史特征表"><table><thead><tr><th scope="col">观测日</th><th scope="col">一期收益</th><th scope="col">尾随均线</th><th scope="col">样本波动</th></tr></thead><tbody>{result.features.map(row=><tr key={row.session}><th scope="row">{row.session}</th><td title={row.return_1d??''}>{display(row.return_1d)}</td><td title={row.sma??''}>{display(row.sma)}</td><td title={row.volatility??''}>{display(row.volatility)}</td></tr>)}</tbody></table></div></>:null}
      {tab==='sources'?<><dl className="foundation-version"><div><dt>保存的快照</dt><dd>{record.snapshot.snapshot_id}</dd></div><div><dt>快照 SHA-256</dt><dd>{result.snapshot_sha256}</dd></div><div><dt>输入指纹</dt><dd>{result.input_hash}</dd></div><div><dt>引擎源码 SHA-256</dt><dd>{result.engine_sha256}</dd></div><div><dt>时间与市场规则</dt><dd>{result.market_rules.timezone}；买入数量步长 {result.market_rules.buy_quantity_step}；最早可售相隔 {result.market_rules.sell_delay_sessions} 个交易日。</dd></div></dl><p className="foundation-fit-note">{result.market_rules.scope}</p><ul>{result.limitations.map(text=><li key={text}>{text}</li>)}</ul></>:null}
    </div>
  </section>;
}
