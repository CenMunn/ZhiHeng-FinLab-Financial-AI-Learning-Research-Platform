import { useState } from 'react';
import { ChevronDown, FileText } from 'lucide-react';
import type { CalculationResult, ComparisonResult, SavedScenario } from './api';
import { money } from './format';
import { ratioToPercent } from './risk-state';
import { TactileButton } from '../../shared/ui/TactileButton';

export function ComparisonPanel({result,fresh,comparison,error,history,reference,onReference,onEvidence}:{result?:CalculationResult;fresh:boolean;comparison?:ComparisonResult;error:string;history:SavedScenario[];reference:string;onReference:(id:string)=>void;onEvidence:()=>void}){
  const [whyOpen,setWhyOpen]=useState(false);
  return <div className="comparison-content" role="tabpanel" id="comparison-view" aria-labelledby="comparison-tab">
    <div className="comparison-toolbar"><div><h3>同一资料基础下的对照</h3><p>比较假设变化，保留计算依据。</p></div><select aria-label="选择对照情景" value={reference} onChange={e=>onReference(e.target.value)}>
      <option value="">同一赊销假设，无新增延迟</option>{history.map(item=><option key={item.scenario_id} value={item.scenario_id} disabled={!!result && (item.result.snapshot.snapshot_sha256!==result.snapshot.snapshot_sha256 || item.result.formula_version!==result.formula_version || item.result.engine_version!==result.engine_version)}>{item.title}</option>)}</select></div>
    {comparison && fresh ? <><div className="table-scroll"><table><thead><tr><th>参数与结果</th><th>{comparison.reference_title}</th><th>当前情景</th></tr></thead><tbody>
      <tr><td>假设赊销比例</td><td>{ratioToPercent(comparison.reference.assumptions.credit_share)}%</td><td>{ratioToPercent(comparison.current.assumptions.credit_share)}%</td></tr>
      <tr><td>新增延迟</td><td>{comparison.reference.assumptions.delay_days}天</td><td>{comparison.current.assumptions.delay_days}天</td></tr>
      <tr><td>稳态占款增量 / 元</td><td>{money(comparison.reference.occupancy_change)}</td><td className="mint-text">{money(comparison.current.occupancy_change)}</td></tr>
    </tbody></table></div><div className="comparison-difference"><span>相对参照的占款差额</span><strong>{money(comparison.difference)}<small>元</small></strong></div>
      <TactileButton className="disclosure-button compact" aria-expanded={whyOpen} onClick={()=>setWhyOpen(!whyOpen)}>为什么变了？<ChevronDown size={16}/></TactileButton>
      {whyOpen && <div className="why-details"><p>假设赊销比例：{ratioToPercent(comparison.reference.assumptions.credit_share)}% → {ratioToPercent(comparison.current.assumptions.credit_share)}%；新增延迟：{comparison.reference.assumptions.delay_days} → {comparison.current.assumptions.delay_days}天。</p><p>固定事实：{money(comparison.current.snapshot.revenue)}元年度营业收入，{comparison.current.snapshot.days}天。</p><p>{comparison.current.formula}。</p><p>多个假设同时改变时，展示联合差额，不分摊因果贡献。</p><TactileButton className="text-button compact" onClick={onEvidence}><FileText size={15}/>查看原文</TactileButton></div>}</>
      :<div className="comparison-empty"><h3>{error?'暂时无法比较':fresh?'正在核对比较基础':'先完成一次推演'}</h3><p>{error || (fresh?'同口径的参数和差值即将显示。':'设置假设并计算后，可与基准或已保存情景比较。')}</p></div>}
  </div>;
}
