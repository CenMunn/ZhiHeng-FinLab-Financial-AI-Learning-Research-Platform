import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Columns2, ArrowRight, BadgeCheck, Building2, CalendarDays, ChartNoAxesCombined, Check, ChevronDown, FileText, FunctionSquare, Save } from 'lucide-react';
import { ratioToPercent } from './risk-state';
import { money, savedTime } from './format';
import { useRiskScenario, type WorkspaceProps } from './useRiskScenario';
import { ResearchWheel, type ResearchStage } from './ResearchWheel';
import { AssumptionPanel } from './AssumptionPanel';
import { ComparisonPanel } from './ComparisonPanel';
import { SensitivityChart } from './SensitivityChart';
import { TactileButton } from '../../shared/ui/TactileButton';
import { EvidenceDrawer } from '../../shared/ui/EvidenceDrawer';
import { ModalFrame } from '../../shared/ui/ModalFrame';

export function RiskWorkspace(props:WorkspaceProps) {
  const model=useRiskScenario(props);
  const {state,dispatch,valid,share,fresh,registered,result,reference,setReference,comparison,comparisonError,calculate,save}=model;
  const [evidenceOpen,setEvidenceOpen]=useState(false),[pointsOpen,setPointsOpen]=useState(false);
  const [view,setView]=useState<'curve'|'comparison'>('curve');
  const [active,setActive]=useState<ResearchStage>('assumptions');
  const resultsRef=useRef<HTMLElement>(null);
  useEffect(()=>{if(model.openVersion){setActive('projection');setView('curve');}},[model.openVersion]);
  const status=state.calculating?'正在计算':state.saved?'已保存':fresh?'结果已计算':result?'参数已修改':'等待设置假设';
  function focusRegion(element:HTMLElement|null){element?.focus({preventScroll:true});element?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'nearest'});}
  function pickStage(stage:ResearchStage){
    setActive(stage);
    if(stage==='source')setEvidenceOpen(true);
    if(stage==='assumptions')focusRegion(document.getElementById('credit-share'));
    if(stage==='projection'){setView('curve');focusRegion(resultsRef.current);}
    if(stage==='archive')focusRegion(document.getElementById('scenario-title'));
  }
  function changeView(next:'curve'|'comparison'){setView(next);setActive('projection');}
  function tabKeys(e:KeyboardEvent<HTMLButtonElement>,next:'curve'|'comparison'){
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'||e.key==='Home'||e.key==='End'){e.preventDefault();const selected=e.key==='Home'?'curve':e.key==='End'?'comparison':next;changeView(selected);document.getElementById(selected==='curve'?'curve-tab':'comparison-tab')?.focus();}
  }
  async function run(){setActive('projection');setView('curve');await calculate();}
  return <>
    <div className="page-heading"><h1>回款压力推演</h1><p>从财报证据出发，探索回款延迟的资金影响。</p></div>
    <div className="workbench-grid">
      <aside className="evidence-rail work-panel" aria-label="案例与研究路径">
        <div className="rail-label">研究标的</div>
        <div className="company-identity"><div className="company-symbol"><Building2 size={24}/></div><div><h2>{state.snapshot.company_name}</h2><p>{state.snapshot.company_id} <span/>2025年度 <span/>合并口径</p></div></div>
        <ResearchWheel state={state} valid={valid} fresh={fresh} registered={registered} active={active} onPick={pickStage}/>
        <div className="source-observation"><h3>来源与观察</h3><div className="revenue-fact"><span>营业收入</span><strong>{money(state.snapshot.revenue)}<small>元</small></strong></div>
          <TactileButton className="source-link secondary compact" onClick={()=>pickStage('source')}><FileText size={18}/><span>来源依据</span><b>P{state.snapshot.evidence.value_page}</b><ArrowRight size={14}/></TactileButton>
          <div className="source-meta"><span><CalendarDays size={16}/>{state.snapshot.days}天</span><span><BadgeCheck size={16}/>待独立复核</span></div>
        </div>
      </aside>
      <div className="analysis-column">
        <section className={`analysis-panel work-panel ${state.calculating?'is-calculating':''}`} ref={resultsRef} tabIndex={-1} aria-label="推演结果">
          <div className="analysis-toolbar"><div className="view-tabs" role="tablist" aria-label="结果视图">
            <button id="curve-tab" role="tab" aria-selected={view==='curve'} aria-controls="curve-view" tabIndex={view==='curve'?0:-1} onClick={()=>changeView('curve')} onKeyDown={e=>tabKeys(e,'comparison')}><ChartNoAxesCombined size={17}/>敏感性曲线</button>
            <button id="comparison-tab" role="tab" aria-selected={view==='comparison'} aria-controls="comparison-view" tabIndex={view==='comparison'?0:-1} onClick={()=>changeView('comparison')} onKeyDown={e=>tabKeys(e,'curve')}><Columns2 size={17}/>情景对比</button>
          </div><span className={`result-status ${fresh?'ready':''}`} role="status"><i/>{status}</span></div>
          {view==='curve'?<div id="curve-view" role="tabpanel" aria-labelledby="curve-tab">
            <div className="result-topline"><span className="result-label">稳态应收占款增量 <small>/ 元</small></span><div className={`result-amount ${fresh?'is-current':''}`}>{result?money(result.occupancy_change):'—'}</div>
              <p className="assumption-summary">{result?<>假设赊销{ratioToPercent(result.assumptions.credit_share)}% <span/>新增延迟{result.assumptions.delay_days}天</>:'右侧设置赊销比例，开始一次推演。'}</p>
            </div>
            {result && !fresh && <div className="stale-note" role="status">参数已修改。当前曲线属于上次结果，重新计算后才能保存。</div>}
            <SensitivityChart result={result} onPick={day=>{dispatch({type:'edit',field:'delayDays',value:day});setActive('assumptions');}}/>
          </div>:<ComparisonPanel result={result} fresh={fresh} comparison={comparison} error={comparisonError} history={props.history} reference={reference} onReference={setReference} onEvidence={()=>pickStage('source')}/>}
          <button className="formula-strip" onClick={()=>pickStage('source')}><FunctionSquare size={21}/><span><strong>计算公式</strong><span>营业收入 × 赊销比例 × 延迟天数 ÷ {state.snapshot.days}</span></span><small>2025年报 P{state.snapshot.evidence.value_page}</small><ArrowRight size={14}/></button>
          {result && <><TactileButton className="table-disclosure compact" aria-expanded={pointsOpen} onClick={()=>setPointsOpen(!pointsOpen)}>查看曲线数值表<ChevronDown size={16}/></TactileButton>
            {pointsOpen && <div className="table-scroll curve-table"><table><thead><tr><th>新增延迟</th><th>稳态占款增量 / 元</th></tr></thead><tbody>{result.sensitivity_curve.map(point=><tr key={point.delay_days}><td><button className="table-day" onClick={()=>{dispatch({type:'edit',field:'delayDays',value:point.delay_days});setActive('assumptions');}}>{point.delay_days}天<ArrowRight size={12}/></button></td><td>{money(point.occupancy_change)}</td></tr>)}</tbody></table></div>}</>}
        </section>
        <section className={`save-panel work-panel ${active==='archive'?'is-highlighted':''}`} aria-labelledby="save-heading">
          <div className="save-controls"><h2 id="save-heading"><Save size={20}/>保存这次推演</h2><label htmlFor="scenario-title" className="sr-only">情景名称</label><input id="scenario-title" value={state.title} maxLength={80} onChange={e=>dispatch({type:'title',value:e.target.value})}/>
            <TactileButton className="secondary save-button" disabled={!registered||!fresh||!state.title.trim()||!!state.saving||!!state.saved} onClick={()=>{setActive('archive');void save();}}><Save size={18}/>{state.saving?'正在保存…':state.saved?'已保存':'保存情景'}</TactileButton></div>
          {state.saveError && <p className="error-text" role="alert">{state.saveError}</p>}
          {state.saved && <p className="saved-confirmation" role="status"><Check size={14}/>已保存「{state.saved.title}」 · {savedTime(state.saved.created_at)}，可从历史情景重新打开。</p>}
        </section>
      </div>
      <AssumptionPanel state={state} dispatch={dispatch} valid={valid} share={share} registered={registered} fresh={fresh} calculate={()=>void run()}/>
    </div>
    <footer className="workspace-footer"><span>事实有来源，假设可调整，结果可追溯。</span><span>确定性敏感性估算，非现金余额预测。金融证据排序模型尚未训练。</span></footer>
    {evidenceOpen && <EvidenceDrawer snapshot={state.snapshot} onClose={()=>setEvidenceOpen(false)}/>}
    {model.pendingOpen && <ModalFrame titleId="replace-title" className="confirm-dialog" onClose={model.cancelOpen}><h2 id="replace-title">打开已保存情景？</h2><p>当前修改尚未保存。打开「{model.pendingOpen.title}」将替换当前草稿。</p><div className="dialog-actions"><TactileButton className="secondary" autoFocus onClick={model.cancelOpen}>保留当前草稿</TactileButton><TactileButton className="primary" onClick={model.confirmOpen}>打开已保存情景</TactileButton></div></ModalFrame>}
  </>;
}
