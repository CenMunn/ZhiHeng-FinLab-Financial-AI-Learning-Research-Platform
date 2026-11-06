import { ArrowRight, Calculator, Info, RotateCcw, SlidersHorizontal } from 'lucide-react';
import type { Dispatch } from 'react';
import { validDelay, type State, type Action } from './risk-state';
import { TactileButton } from '../../shared/ui/TactileButton';

export function AssumptionPanel({state,dispatch,valid,share,registered,fresh,calculate}:{state:State;dispatch:Dispatch<Action>;valid:boolean;share:string|null;registered:boolean;fresh:boolean;calculate:()=>void}){
  return <section id="assumption-panel" className="assumption-panel work-panel" aria-labelledby="assumption-heading">
    <div className="panel-heading"><SlidersHorizontal size={18}/><h2 id="assumption-heading">设置回款假设</h2></div>
    <div className="input-field">
      <label htmlFor="credit-share">赊销收入占比 <span>0–100%</span></label>
      <div className={`number-input ${state.draft.creditPercent && share===null?'invalid':''}`}>
        <input id="credit-share" inputMode="decimal" placeholder="待设置" value={state.draft.creditPercent} aria-describedby="credit-help" aria-invalid={!!state.draft.creditPercent && share===null}
          onChange={e=>dispatch({type:'edit',field:'creditPercent',value:e.target.value})}/><span>%</span>
      </div><p id="credit-help" className="field-help">假设比例，非企业披露值。</p>
    </div>
    <div className="input-field delay-field">
      <label htmlFor="delay-days">新增回款延迟 <span>0–90天</span></label>
      <div className={`number-input ${!validDelay(state.draft.delayDays)?'invalid':''}`}>
        <input id="delay-days" inputMode="decimal" value={state.draft.delayDays} aria-invalid={!validDelay(state.draft.delayDays)}
          onChange={e=>dispatch({type:'edit',field:'delayDays',value:e.target.value})}/><span>天</span>
      </div>
      <input className="delay-slider" type="range" min="0" max="90" step="1" aria-label="调整新增回款延迟天数" value={validDelay(state.draft.delayDays)?state.draft.delayDays:0}
        onChange={e=>dispatch({type:'edit',field:'delayDays',value:e.target.value})}/>
      <div className="slider-labels"><span>0</span><span>90</span></div>
      <div className="delay-presets" aria-label="延迟天数快捷设置">{[0,15,30,60,90].map(day=><TactileButton key={day} className="preset compact" aria-pressed={Number(state.draft.delayDays)===day && validDelay(state.draft.delayDays)}
        onClick={()=>dispatch({type:'edit',field:'delayDays',value:String(day)})}>{day}天</TactileButton>)}</div>
    </div>
    {!valid && state.draft.creditPercent && <p className="error-text" role="alert">请输入0–100%的比例和0–90天的延迟。</p>}
    {!registered && <p className="warning-text">当前资料不可重算，原情景仍可查看。</p>}
    <TactileButton className="primary calculate-button" disabled={!valid||!!state.calculating||!registered} onClick={calculate}><Calculator size={19}/>{state.calculating?'正在计算…':'计算情景'}<ArrowRight size={17}/></TactileButton>
    {state.result && !fresh && <TactileButton className="text-button compact" onClick={()=>dispatch({type:'restore'})}><RotateCcw size={15}/>恢复上次计算参数</TactileButton>}
    {state.error && <p className="error-text" role="alert">{state.error}</p>}
    <div className="seasonal-note"><Info size={18}/><p>供暖业务季节性明显。<br/>年均估算不代表实际逐周回款。</p></div>
    <p className="inspector-footnote">更改参数后，点击计算更新结果。<br/>曲线节点也可用于设置延迟。</p>
  </section>;
}
