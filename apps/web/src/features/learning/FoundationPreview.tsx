import {Database,ScanLine,GitCompareArrows,FileCheck2} from 'lucide-react';
import type {FoundationConfig,FoundationSnapshot} from './foundation-api';
import {splitPreview} from './foundation-presentation';

const labels=['训练段','验证段','测试段'];
export function FoundationPreview({snapshot,config}:{snapshot:FoundationSnapshot;config:FoundationConfig}){
  const preview=splitPreview(snapshot.row_count,config.train_count,config.validation_count);
  return <section className="foundation-preview" aria-label="配置预览">
    <div className="foundation-preview-title"><ScanLine size={22}/><span>尚未检查</span></div>
    <h3>先配置，再留下<br/>一份可复核的记录。</h3>
    <p>左侧调整参数，右侧查看检查结果。快照、时间划分和费用会随配置一起保存。</p>
    <div className="foundation-allocation"><div><strong>配置预览</strong><span>{snapshot.row_count} 条合成日线</span></div>
      {preview.valid?<><div className="foundation-allocation-bar" aria-hidden="true">{preview.fractions.map((fraction,index)=><span key={index} className={`allocation-${index}`} style={{flexGrow:fraction}}/>)}</div><ul>{preview.counts.map((count,index)=><li key={labels[index]}><i className={`allocation-${index}`}/>{labels[index]} {count}</li>)}</ul></>:<p className="foundation-draft-warning">剩余样本不足或划分无效，请调整训练与验证段。</p>}
      <small>仅显示当前参数，最终以服务端检查为准。</small>
    </div>
    <ol className="foundation-check-list"><li><Database size={18}/><div><b>确认数据</b><span>保留来源、时间和快照版本。</span></div></li><li><GitCompareArrows size={18}/><div><b>检查边界</b><span>只看过去，训练与评测分别处理。</span></div></li><li><FileCheck2 size={18}/><div><b>保存依据</b><span>结果可重开，也可导出完整 JSON。</span></div></li></ol>
  </section>;
}
